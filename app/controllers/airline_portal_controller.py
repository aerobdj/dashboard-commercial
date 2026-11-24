from datetime import date
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import app
from app.utils.decorators import airline_required, menu_required
from app.models.airline_user_model import AirlineUserModel
from app.models.pjp2u_model import Pjp2uModel
from app.controllers.auth_controller import sync_airline_session
from app.controllers.pjp2u_controller import _group_by_airline

airline_portal_bp = Blueprint('airline_portal', __name__, url_prefix='/airline')


def _get_airline_actor():
    current_user = session.get('user') or {}
    nama = current_user.get('nama_lengkap')
    email = current_user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'Airline User'


def _get_airline_pjp2u_context():
    """
    Mengambil konteks user airline terbaru (id_airlineusers, daftar id_airline,
    cabang/allowed_cabang, dan role: 'admin' / 'user') selaras dengan Account Profile.
    """
    sess_user = session.get('user') or {}
    id_airlineusers = sess_user.get('id_airlineusers')
    fresh_user = AirlineUserModel.get_by_id(id_airlineusers) if id_airlineusers else None
    active_user = fresh_user or sess_user

    allowed_cabang = sess_user.get('allowed_cabang')
    if allowed_cabang is None:
        cabang_single = (active_user.get('kode_cabang') or '').strip().upper()
        allowed_cabangs = [cabang_single] if cabang_single and cabang_single not in ('HO', 'ALL') else None
    else:
        allowed_cabangs = [c.strip().upper() for c in allowed_cabang if c and c.strip()]

    raw_airlines = active_user.get('airlines') or []
    airline_id_set = set()

    # 1. Gunakan resolver resmi yang sama dengan Account Profile & Dashboard
    try:
        auth_airlines = AirlineUserModel.get_authorized_airlines(
            raw_airlines,
            allowed_cabang_codes=allowed_cabangs
        ) or []
        for al in auth_airlines:
            if isinstance(al, dict) and str(al.get('id_airline') or '').isdigit():
                airline_id_set.add(int(al['id_airline']))
    except Exception:
        pass

    # 2. Fallback parsing langsung dari kolom airlines (list/string/dict)
    if isinstance(raw_airlines, str):
        for x in raw_airlines.strip('[]{}').replace('"', '').split(','):
            if x.strip().isdigit():
                airline_id_set.add(int(x.strip()))
    elif isinstance(raw_airlines, list):
        for item in raw_airlines:
            if isinstance(item, dict) and str(item.get('id_airline') or '').isdigit():
                airline_id_set.add(int(item['id_airline']))
            elif str(item).isdigit():
                airline_id_set.add(int(item))

    airline_ids = sorted(airline_id_set)
    role = (active_user.get('role') or sess_user.get('role') or '').strip().lower()
    return active_user, airline_ids, allowed_cabangs, role


def _is_row_authorized_for_airline(row, airline_ids, allowed_cabangs):
    if not row:
        return False
    try:
        op_id = int(row.get('operator'))
    except (TypeError, ValueError):
        return False
    if op_id not in airline_ids:
        return False
    if allowed_cabangs is not None and (row.get('cabang') or '').strip().upper() not in allowed_cabangs:
        return False
    return True


@airline_portal_bp.route('/dashboard')
@airline_required
@menu_required('airline_dashboard')
def dashboard():
    user = session.get('user', {})
    allowed_cabang = user.get('allowed_cabang')  # None berarti HO (Semua Cabang)
    fresh_user = AirlineUserModel.get_by_id(user.get('id_airlineusers'))
    raw_airlines = fresh_user.get('airlines') if fresh_user else user.get('airlines', [])
    authorized_airlines = AirlineUserModel.get_authorized_airlines(
        raw_airlines,
        allowed_cabang_codes=allowed_cabang
    )

    sample_summary = {
        'total_flights_today': 14,
        'verified_manifests': 12,
        'pending_reconciliation': 2,
        'total_pjp2u_pax': 2148
    }

    return render_template(
        'airline_portal/dashboard.html',
        user=user,
        allowed_cabang=allowed_cabang,
        authorized_airlines=authorized_airlines,
        summary=sample_summary
    )


@airline_portal_bp.route('/profile', methods=['GET', 'POST'])
@airline_required
def profile():
    sess_user = session.get('user') or {}
    id_airlineusers = sess_user.get('id_airlineusers')
    airline_user = AirlineUserModel.get_by_id(id_airlineusers)

    if not airline_user:
        flash('Data akun maskapai tidak ditemukan.', 'danger')
        return redirect(url_for('auth.logout'))

    if request.method == 'POST':
        nama_lengkap = (request.form.get('nama_lengkap') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        jabatan = (request.form.get('jabatan') or '').strip()
        password = request.form.get('password')

        if not nama_lengkap or not email or not jabatan:
            flash('Nama lengkap, email, dan jabatan wajib diisi.', 'warning')
            return redirect(url_for('airline_portal.profile'))

        if AirlineUserModel.email_exists(email, exclude_id=id_airlineusers):
            flash(f'Email {email} sudah digunakan oleh akun lain.', 'danger')
            return redirect(url_for('airline_portal.profile'))

        try:
            AirlineUserModel.update_profile(
                id_airlineusers=id_airlineusers,
                nama_lengkap=nama_lengkap,
                email=email,
                jabatan=jabatan,
                password=password,
                updated_by=_get_airline_actor()
            )
            fresh_user = AirlineUserModel.get_by_id(id_airlineusers)
            if fresh_user:
                sync_airline_session(fresh_user)
            flash('Profil akun maskapai berhasil diperbarui!', 'success')
        except Exception as e:
            flash(f'Gagal menyimpan profil: {str(e)}', 'danger')

        return redirect(url_for('airline_portal.profile'))

    authorized_airlines = AirlineUserModel.get_authorized_airlines(
        airline_user.get('airlines'),
        allowed_cabang_codes=sess_user.get('allowed_cabang')
    )

    return render_template(
        'airline_portal/account_profile.html',
        user=airline_user,
        authorized_airlines=authorized_airlines
    )


# =========================================================================
# PJP2U RECONCILIATION & VERIFICATION (AIRLINE PORTAL)
# =========================================================================
@airline_portal_bp.route('/pjp2u')
@airline_required
def pjp2u():
    _, airline_ids, allowed_cabangs, role = _get_airline_pjp2u_context()

    first_day_str = date.today().replace(day=1).isoformat()
    date_from = (request.args.get('date_from') or first_day_str).strip()
    date_to = (request.args.get('date_to') or '').strip()
    filter_cabang = (request.args.get('cabang') or '').strip().upper()

    if filter_cabang and allowed_cabangs is not None and filter_cabang not in allowed_cabangs:
        filter_cabang = ''

    # Daftar cabang untuk filter jika akun maskapai punya akses > 1 cabang / HO
    cabang_query = (
        app.supabase.table('cabang')
        .select('kode_cabang, nama_cabang')
        .is_('deleted_at', 'null')
        .order('kode_cabang', desc=False)
    )
    if allowed_cabangs is not None:
        cabang_list = cabang_query.in_('kode_cabang', allowed_cabangs).execute().data or [] if allowed_cabangs else []
    else:
        cabang_list = cabang_query.execute().data or []

    is_single_cabang = (allowed_cabangs is not None and len(allowed_cabangs) == 1)

    rows = Pjp2uModel.get_list(
        allowed_cabangs=allowed_cabangs,
        filter_cabang=filter_cabang or None,
        airline_ids=airline_ids,
        date_from=date_from or None,
        date_to=date_to or None,
        include_deleted=False,
    )

    normal_rows = [r for r in rows if (r.get('status') or 'NORMAL').upper() == 'NORMAL']
    adj_rows = [r for r in rows if (r.get('status') or '').upper() == 'ADJUSTMENT']

    return render_template(
        'airline_portal/pjp2u.html',
        normal_groups=_group_by_airline(normal_rows),
        adjustment_groups=_group_by_airline(adj_rows),
        normal_count=len(normal_rows),
        adjustment_count=len(adj_rows),
        is_airline_admin=(role == 'admin'),
        is_single_cabang=is_single_cabang,
        cabang_list=cabang_list,
        filter_cabang=filter_cabang,
        date_from=date_from,
        date_to=date_to,
    )


@airline_portal_bp.route('/pjp2u/verify/<int:id_pjp2u>', methods=['POST'])
@airline_required
def verify_pjp2u(id_pjp2u):
    active_user, airline_ids, allowed_cabangs, _ = _get_airline_pjp2u_context()
    row = Pjp2uModel.get_by_id(id_pjp2u)

    if not _is_row_authorized_for_airline(row, airline_ids, allowed_cabangs):
        flash('Data penerbangan tidak ditemukan atau bukan wewenang maskapai Anda.', 'danger')
        return redirect(url_for('airline_portal.pjp2u'))

    try:
        Pjp2uModel.verify_normal(
            id_pjp2u,
            verifier_name=active_user.get('nama_lengkap') or active_user.get('email'),
            verifier_jabatan=active_user.get('jabatan') or 'Airline Representative',
        )
        flash(f"Penerbangan {row['flight_number']} berhasil diverifikasi!", 'success')
    except Exception as e:
        flash(f'Gagal memverifikasi penerbangan: {str(e)}', 'danger')

    return redirect(url_for('airline_portal.pjp2u'))


@airline_portal_bp.route('/pjp2u/verify-offload/<int:id_pjp2u>', methods=['POST'])
@airline_required
def verify_offload(id_pjp2u):
    active_user, airline_ids, allowed_cabangs, _ = _get_airline_pjp2u_context()
    row = Pjp2uModel.get_by_id(id_pjp2u)

    if not _is_row_authorized_for_airline(row, airline_ids, allowed_cabangs):
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('airline_portal.pjp2u'))

    if int(row.get('offload') or 0) <= 0:
        flash('Penerbangan ini tidak memiliki penumpang offload.', 'warning')
        return redirect(url_for('airline_portal.pjp2u'))

    try:
        Pjp2uModel.verify_offload(
            id_pjp2u,
            verifier_name=active_user.get('nama_lengkap') or active_user.get('email'),
            verifier_jabatan=active_user.get('jabatan') or 'Airline Representative',
        )
        flash(f"Data Offload {row['flight_number']} berhasil diverifikasi!", 'success')
    except Exception as e:
        flash(f'Gagal memverifikasi offload: {str(e)}', 'danger')

    return redirect(url_for('airline_portal.pjp2u'))


@airline_portal_bp.route('/pjp2u/verify-adjustment/<int:id_pjp2u>', methods=['POST'])
@airline_required
def verify_adjustment(id_pjp2u):
    active_user, airline_ids, allowed_cabangs, role = _get_airline_pjp2u_context()
    if role != 'admin':
        flash('Hanya Station Manager / Admin Maskapai yang berwenang memverifikasi Adjustment.', 'danger')
        return redirect(url_for('airline_portal.pjp2u'))

    row = Pjp2uModel.get_by_id(id_pjp2u)
    if not _is_row_authorized_for_airline(row, airline_ids, allowed_cabangs):
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('airline_portal.pjp2u'))

    doc_mode = (request.form.get('doc_mode') or 'AUTO').upper()
    nomor_surat = (request.form.get('nomor_surat') or '').strip() or None
    file_url = None

    try:
        if doc_mode == 'UPLOAD':
            uploaded = request.files.get('surat_file')
            if not uploaded or not uploaded.filename:
                flash('Silakan pilih file surat persetujuan adjustment untuk diunggah.', 'warning')
                return redirect(url_for('airline_portal.pjp2u'))
            cab_folder = (row.get('cabang') or 'GENERAL').upper()
            storage_path = f"adjustment/{cab_folder}/{id_pjp2u}_{uploaded.filename}"
            file_bytes = uploaded.read()
            app.supabase.storage.from_('pjp2u-documents').upload(
                storage_path, file_bytes, {"content-type": uploaded.content_type or "application/pdf"}
            )
            file_url = app.supabase.storage.from_('pjp2u-documents').get_public_url(storage_path)
        else:
            if not nomor_surat:
                flash('Nomor surat wajib diisi untuk pembuatan surat otomatis.', 'warning')
                return redirect(url_for('airline_portal.pjp2u'))

        Pjp2uModel.verify_adjustment(
            id_pjp2u,
            verifier_name=active_user.get('nama_lengkap') or active_user.get('email'),
            verifier_jabatan=active_user.get('jabatan') or 'Station Manager',
            doc_mode=doc_mode,
            nomor_surat=nomor_surat,
            file_url=file_url,
        )
        flash(f"Adjustment {row['flight_number']} berhasil diverifikasi!", 'success')
    except Exception as e:
        flash(f'Gagal memverifikasi adjustment: {str(e)}', 'danger')

    return redirect(url_for('airline_portal.pjp2u'))