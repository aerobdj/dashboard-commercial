from datetime import datetime, timezone, date
from collections import OrderedDict
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import app
from app.models.pjp2u_model import Pjp2uModel
from app.utils.decorators import airport_required, menu_required

pjp2u_bp = Blueprint('pjp2u', __name__, url_prefix='/aeronautika/operasional/pjp2u')


def _get_role(user):
    if not isinstance(user, dict):
        user = {}
    raw_role = user.get('role') or user.get('user_role') or session.get('role') or ''
    return str(raw_role).strip().lower()


def _get_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _get_accessible_cabangs(user):
    """
    Hierarki akses cabang:
    - None          : HO / Superadmin -> semua cabang + filter cabang
    - List > 1 item : Regional -> hanya cabang di bawah regional tsb + filter cabang
    - List 1 item   : Cabang tunggal -> otomatis cabang tsb (tanpa filter cabang)
    """
    role = _get_role(user)
    query = (
        app.supabase.table('cabang')
        .select('kode_cabang, nama_cabang, tipe_unit, parent_kode, kota')
        .is_('deleted_at', 'null')
    )

    if role == 'superadmin':
        res = query.order('kode_cabang', desc=False).execute()
        return None, (res.data or [])

    if 'allowed_cabang' in user:
        allowed_cabang = user.get('allowed_cabang')
        if allowed_cabang is None:
            res = query.order('kode_cabang', desc=False).execute()
            return None, (res.data or [])
        if not allowed_cabang:
            return [], []
        clean_allowed = [c.strip().upper() for c in allowed_cabang if c and c.strip()]
        res = query.in_('kode_cabang', clean_allowed).order('kode_cabang', desc=False).execute()
        return clean_allowed, (res.data or [])

    user_cabang = (user.get('kode_cabang') or '').strip().upper()
    if not user_cabang:
        return [], []
    if user_cabang in ('HO', 'KANTOR PUSAT'):
        res = query.order('kode_cabang', desc=False).execute()
        return None, (res.data or [])

    all_cabs = (query.order('kode_cabang', desc=False).execute()).data or []
    reg_cabs = [c for c in all_cabs if (c.get('parent_kode') or '').strip().upper() == user_cabang]
    if reg_cabs:
        return [c['kode_cabang'] for c in reg_cabs], reg_cabs

    single = [c for c in all_cabs if (c.get('kode_cabang') or '').strip().upper() == user_cabang]
    return [user_cabang], single


def _parse_iso_dt(dt_str):
    if not dt_str:
        return None
    try:
        clean = str(dt_str).replace('Z', '+00:00')
        parsed = datetime.fromisoformat(clean)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _compute_row_permissions(row, role):
    """
    Aturan hak tombol internal:
    - NORMAL:
      - Edit hilang jika: sudah diverifikasi airline ATAU role 'user'/'users' > 1.5 hari (36 jam)
        ATAU role 'admin' > 2.5 hari (60 jam). Pengawas & Superadmin bisa edit selama belum diverifikasi.
      - Hapus hilang jika: sudah diverifikasi airline ATAU lewat 3 hari (72 jam) untuk role user/admin.
        Untuk 'pengawas' & 'superadmin', tombol hapus TETAP TAMPIL (meski > 3 hari atau sudah diverifikasi).
      - Adjustment: hanya 'pengawas' & 'superadmin'.
    - ADJUSTMENT:
      - Edit: hanya 'pengawas' & 'superadmin' selama belum diverifikasi adjustment.
      - Hapus: hanya 'pengawas' & 'superadmin' (tetap ada meski sudah diverifikasi).
    """
    now = datetime.now(timezone.utc)
    created_dt = _parse_iso_dt(row.get('created_at')) or now
    age_hours = (now - created_dt).total_seconds() / 3600.0
    status = (row.get('status') or 'NORMAL').upper()

    is_privileged = role in ('superadmin', 'pengawas')
    is_admin = role == 'admin'

    if status == 'NORMAL':
        is_verified = bool(row.get('verification_at'))
        is_offload_verified = bool(row.get('verification_offload_at'))

        if is_verified:
            can_edit = False
        elif is_privileged:
            can_edit = True
        elif is_admin:
            can_edit = age_hours <= 60.0  # 2.5 hari
        else:
            can_edit = age_hours <= 36.0  # 1.5 hari

        if is_privileged:
            can_delete = True
        else:
            can_delete = (not is_verified) and (age_hours <= 72.0)  # 3 hari

        can_adjust = is_privileged
        can_ba_normal = is_verified
        can_ba_offload = (int(row.get('offload') or 0) > 0) and is_offload_verified
        can_ba_adjustment = False
    else:
        is_adj_verified = bool(row.get('verification_adjustment_at'))
        can_edit = is_privileged and (not is_adj_verified)
        can_delete = is_privileged
        can_adjust = False
        can_ba_normal = False
        can_ba_offload = False
        can_ba_adjustment = is_adj_verified

    row['perm'] = {
        'can_edit': can_edit,
        'can_delete': can_delete,
        'can_adjust': can_adjust,
        'can_ba_normal': can_ba_normal,
        'can_ba_offload': can_ba_offload,
        'can_ba_adjustment': can_ba_adjustment,
    }
    return row


def _group_by_airline(rows):
    """Mengelompokkan list data PJP2U per maskapai (operator) beserta subtotal."""
    groups_map = {}
    for r in rows:
        op_id = r.get('operator') or 0
        if op_id not in groups_map:
            groups_map[op_id] = {
                'operator_id': op_id,
                'airline_name': r.get('airline_name') or 'Unknown Airline',
                'airline_code_2': r.get('airline_code_2') or '-',
                'airline_logo': r.get('airline_logo'),
                'rows': [],
                'sum_pax': 0,
                'sum_psc': 0,
                'sum_pend_psc': 0.0,
                'sum_pend_counter_idr': 0.0,
                'sum_pend_counter_usd': 0.0,
                'sum_pend_cucs': 0.0,
                'sum_pend_counter_cucs': 0.0,
            }
        g = groups_map[op_id]
        g['rows'].append(r)
        g['sum_pax'] += int(r.get('jumlah_pax') or 0)
        g['sum_psc'] += int(r.get('total_prod_psc') or 0)
        g['sum_pend_psc'] += float(r.get('pend_psc') or 0)
        cnt_val = float(r.get('pend_counter') or 0)
        cucs_val = float(r.get('pend_cucs') or 0)
        if (r.get('mata_uang_counter') or 'IDR').upper() == 'USD':
            g['sum_pend_counter_usd'] += cnt_val
        else:
            g['sum_pend_counter_idr'] += cnt_val
        g['sum_pend_cucs'] += cucs_val
        g['sum_pend_counter_cucs'] += (cnt_val if (r.get('mata_uang_counter') or 'IDR').upper() != 'USD' else 0.0) + cucs_val

    return sorted(groups_map.values(), key=lambda x: x['airline_name'])


def _build_payload_from_form(form, master_bundle, allowed_codes, is_adjustment=False, parent_row=None):
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)
    cabang = (
        allowed_codes[0] if is_single_cabang
        else (form.get('cabang') or (parent_row.get('cabang') if parent_row else '') or '').strip().upper()
    )
    if not cabang:
        raise ValueError("Cabang wajib dipilih.")
    if allowed_codes is not None and cabang not in allowed_codes:
        raise ValueError(f"Anda tidak memiliki akses untuk cabang {cabang}.")

    tanggal_str = (form.get('tanggal') or (parent_row.get('tanggal') if parent_row else '') or '').strip()
    if not tanggal_str:
        raise ValueError("Tanggal penerbangan wajib diisi.")
    tgl_obj = date.fromisoformat(tanggal_str[:10])

    boarding_time = (form.get('boarding_time') or '').strip() or None
    flight_number = (form.get('flight_number') or '').strip().upper()
    if not flight_number:
        raise ValueError("Nomor penerbangan (Flight Number) wajib diisi.")

    # Pada mode Adjustment, pastikan akhiran "J" terpasang
    if is_adjustment and not flight_number.endswith('J'):
        flight_number = f"{flight_number}J"

    id_flightnumber = Pjp2uModel._to_int(form.get('id_flightnumber'), 0) or None
    id_registration = Pjp2uModel._to_int(form.get('id_registration'), 0) or None
    registration = (form.get('registration') or '').strip().upper() or None

    # Wajib cocok dengan master airline_registration (tidak boleh input registrasi baru dari menu PJP2U)
    reg_obj = next(
        (r for r in master_bundle['registrations']
         if (id_registration and r['id_registration'] == id_registration)
         or (registration and (r.get('registration') or '').upper() == registration)),
        None
    )
    if not reg_obj:
        raise ValueError("Registrasi belum terdaftar! Silakan tambahkan terlebih dahulu pada menu Airline Registration.")

    id_registration = reg_obj['id_registration']
    registration = (reg_obj.get('registration') or registration or '').upper()
    operator_id = reg_obj.get('id_airline')
    scope_registration = reg_obj.get('scope') or 'Domestik'
    seat = int(reg_obj.get('seat') or 0)

    # Auto-resolve flight_number jika cocok dengan master
    fn_clean = flight_number[:-1] if (is_adjustment and flight_number.endswith('J')) else flight_number
    fn_obj = next(
        (f for f in master_bundle['flight_numbers']
         if (id_flightnumber and f['id_flightnumber'] == id_flightnumber)
         or ((f.get('flight_number') or '').upper() == fn_clean and (f.get('kode_cabang') or '').upper() == cabang)),
        None
    )
    if fn_obj:
        id_flightnumber = fn_obj['id_flightnumber']
        if not operator_id:
            operator_id = fn_obj.get('id_airline')

    # Origin otomatis sama dengan cabang untuk user cabang; untuk HO/Regional mengikuti input origin (default cabang)
    origin = cabang if is_single_cabang else ((form.get('origin') or cabang).strip().upper())
    destination = (form.get('destination') or '').strip().upper()
    if not destination:
        raise ValueError("Bandara tujuan (Destination) wajib diisi.")

    dest_ap = master_bundle['airport_by_iata'].get(destination)
    # Prioritaskan pilihan scope_route dari form (mis. Haji / Internasional / Domestik), fallback ke master bandara/flight
    scope_route = (
        (form.get('scope_route') or '').strip()
        or (dest_ap.get('scope') if dest_ap else None)
        or (fn_obj.get('destination_scope') if fn_obj else None)
        or 'Domestik'
    )

    pricing = Pjp2uModel.resolve_pricing_snapshot(
        master_bundle=master_bundle,
        cabang=cabang,
        scope_route=scope_route,
        tanggal_str=tanggal_str,
        id_airline=operator_id,
        scope_registration=scope_registration,
    )

    form_with_seat = dict(form)
    form_with_seat['seat'] = seat
    metrics = Pjp2uModel.compute_metrics(form_with_seat, pricing, is_adjustment=is_adjustment)

    payload = {
        'parent_id_pjp2u': parent_row['id_pjp2u'] if parent_row else None,
        'tahun': tgl_obj.year,
        'bulan': tgl_obj.month,
        'tanggal': tanggal_str[:10],
        'cabang': cabang,
        'status': 'ADJUSTMENT' if is_adjustment else 'NORMAL',
        'boarding_time': boarding_time,
        'operator': operator_id,
        'registration': registration,
        'id_registration': id_registration,
        'flight_number': flight_number,
        'id_flightnumber': id_flightnumber,
        'origin': origin,
        'destination': destination,
        'scope_registration': scope_registration,
        'scope_route': scope_route,
        'id_tarif_baru': pricing['id_tarif_baru'],
        'id_tarif_lama': pricing['id_tarif_lama'],
        'id_promo': pricing['id_promo'],
        'persentase_diskon': pricing['persentase_diskon'],
        'persentase_ppn': pricing['persentase_ppn'],
        'tarif_psc_dpp_baru': pricing['tarif_psc_dpp_baru'],
        'tarif_psc_dpp_lama': pricing['tarif_psc_dpp_lama'],
        'tarif_counter_dpp': pricing['tarif_counter_dpp'],
        'tarif_cucs_dpp': pricing['tarif_cucs_dpp'],
        **metrics,
    }

    if is_adjustment:
        payload['justifikasi_adjustment'] = (form.get('justifikasi_adjustment') or '').strip() or None
        payload['detail_justifikasi_adjustment'] = (form.get('detail_justifikasi_adjustment') or '').strip() or None
        payload['date_adjustment'] = (form.get('date_adjustment') or date.today().isoformat()).strip()[:10]

    return payload


@pjp2u_bp.route('/')
@airport_required
@menu_required('aeronautika_pjp2u')
def index():
    user = session.get('user', {})
    role = _get_role(user)
    is_superadmin = (role == 'superadmin')
    is_privileged = role in ('superadmin', 'pengawas')

    allowed_codes, cabang_list = _get_accessible_cabangs(user)
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)

    # Filter query params (tanggal & cabang)
    today_str = date.today().isoformat()
    first_day_str = date.today().replace(day=1).isoformat()
    date_from = (request.args.get('date_from') or first_day_str).strip()
    date_to = (request.args.get('date_to') or today_str).strip()
    filter_cabang = '' if is_single_cabang else (request.args.get('cabang') or '').strip().upper()

    if filter_cabang and allowed_codes is not None and filter_cabang not in allowed_codes:
        filter_cabang = ''

    all_rows = Pjp2uModel.get_list(
        allowed_cabangs=allowed_codes,
        filter_cabang=filter_cabang or None,
        date_from=date_from or None,
        date_to=date_to or None,
        include_deleted=is_superadmin,
    )

    active_rows = [r for r in all_rows if not r.get('deleted_at')]
    deleted_rows = [r for r in all_rows if r.get('deleted_at')] if is_superadmin else []

    normal_rows = [_compute_row_permissions(r, role) for r in active_rows if (r.get('status') or 'NORMAL').upper() == 'NORMAL']
    adjustment_rows = [_compute_row_permissions(r, role) for r in active_rows if (r.get('status') or '').upper() == 'ADJUSTMENT']
    deleted_normal_rows = [r for r in deleted_rows if (r.get('status') or 'NORMAL').upper() == 'NORMAL']
    deleted_adjustment_rows = [r for r in deleted_rows if (r.get('status') or '').upper() == 'ADJUSTMENT']

    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    return render_template(
        'aeronautika/operasional/pjp2u.html',
        normal_groups=_group_by_airline(normal_rows),
        adjustment_groups=_group_by_airline(adjustment_rows),
        deleted_normal_groups=_group_by_airline(deleted_normal_rows),
        deleted_adjustment_groups=_group_by_airline(deleted_adjustment_rows),
        normal_count=len(normal_rows),
        adjustment_count=len(adjustment_rows),
        deleted_normal_count=len(deleted_normal_rows),
        deleted_adjustment_count=len(deleted_adjustment_rows),
        cabang_list=cabang_list,
        master_bundle=master_bundle,
        is_superadmin=is_superadmin,
        is_privileged=is_privileged,
        is_single_cabang=is_single_cabang,
        default_cabang=(allowed_codes[0] if is_single_cabang else (cabang_list[0]['kode_cabang'] if cabang_list else '')),
        filter_cabang=filter_cabang,
        date_from=date_from,
        date_to=date_to,
    )


@pjp2u_bp.route('/create', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def create():
    user = session.get('user', {})
    allowed_codes, _ = _get_accessible_cabangs(user)
    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload = _build_payload_from_form(request.form, master_bundle, allowed_codes, is_adjustment=False)
        Pjp2uModel.create(payload, created_by=_get_actor(user))
        flash('Data operasional PJP2U berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menyimpan data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/update/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def update(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    existing = Pjp2uModel.get_by_id(id_pjp2u)
    if not existing:
        flash('Data PJP2U tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang mengubah data cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    _compute_row_permissions(existing, role)
    if not existing['perm']['can_edit']:
        flash('Batas waktu edit telah habis atau data sudah diverifikasi oleh Airline.', 'danger')
        return redirect(url_for('pjp2u.index'))

    is_adj = (existing.get('status') or '').upper() == 'ADJUSTMENT'
    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload = _build_payload_from_form(request.form, master_bundle, allowed_codes, is_adjustment=is_adj)
        payload['parent_id_pjp2u'] = existing.get('parent_id_pjp2u')
        Pjp2uModel.update(id_pjp2u, payload, updated_by=_get_actor(user))
        flash('Data PJP2U berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/adjust/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def adjust(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ('superadmin', 'pengawas'):
        flash('Hanya Pengawas dan Superadmin yang dapat membuat Adjustment PJP2U.', 'danger')
        return redirect(url_for('pjp2u.index'))

    parent_row = Pjp2uModel.get_by_id(id_pjp2u)
    if not parent_row:
        flash('Data referensi PJP2U Normal tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and parent_row['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang membuat adjustment cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload = _build_payload_from_form(
            request.form, master_bundle, allowed_codes, is_adjustment=True, parent_row=parent_row
        )
        Pjp2uModel.create(payload, created_by=_get_actor(user))
        flash(f"Adjustment {payload['flight_number']} berhasil disimpan ke tab Adjustment!", 'success')
    except Exception as e:
        flash(f'Gagal menyimpan Adjustment PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/delete/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def delete(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    existing = Pjp2uModel.get_by_id(id_pjp2u)
    if not existing:
        flash('Data PJP2U tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang menghapus data cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    _compute_row_permissions(existing, role)
    if not existing['perm']['can_delete']:
        flash('Batas waktu hapus (3 hari) telah terlewati atau data sudah diverifikasi Airline.', 'danger')
        return redirect(url_for('pjp2u.index'))

    try:
        Pjp2uModel.delete(id_pjp2u, deleted_by=_get_actor(user))
        flash('Data PJP2U berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/restore/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def restore(id_pjp2u):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengembalikan data terhapus.', 'danger')
        return redirect(url_for('pjp2u.index'))

    try:
        Pjp2uModel.restore(id_pjp2u, restored_by=_get_actor(user))
        flash('Data PJP2U berhasil dipulihkan!', 'success')
    except Exception as e:
        flash(f'Gagal memulihkan data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))