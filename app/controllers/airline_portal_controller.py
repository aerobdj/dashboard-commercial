from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.decorators import airline_required, menu_required
from app.models.airline_user_model import AirlineUserModel
from app.controllers.auth_controller import sync_airline_session

airline_portal_bp = Blueprint('airline_portal', __name__, url_prefix='/airline')

def _get_airline_actor():
    current_user = session.get('user') or {}
    nama = current_user.get('nama_lengkap')
    email = current_user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'Airline User'

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

    authorized_airlines = session.get('user', {}).get('airlines', [])
    return render_template(
        'airline_portal/account_profile.html',
        user=airline_user,
        authorized_airlines=authorized_airlines
    )