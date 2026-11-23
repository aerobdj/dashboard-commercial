import time
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.user_model import UserModel
from app.models.airline_user_model import AirlineUserModel
from app.models.cabang_model import CabangModel
from app.models.role_model import RoleModel

auth_bp = Blueprint('auth', __name__)

MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION_SECONDS = 300  # 5 menit

# Penyimpanan server-side per email (tidak mengunci IP/perangkat lain)
_LOGIN_ATTEMPT_STORE = {}

DEFAULT_ROLE_MENUS = {
    'superadmin': ['dashboard', 'commercial', 'mitra_usaha', 'users', 'cabang', 'coa_pendapatan', 'master_ppn', 'role_access', 'airlines', 'routes', 'flight_numbers', 'airline_registrations', 'tarif_aeronautika'],
    'admin': ['dashboard', 'commercial', 'mitra_usaha', 'airlines', 'flight_numbers', 'airline_registrations'],
    'pengawas': ['dashboard', 'commercial', 'mitra_usaha', 'users', 'airlines', 'routes', 'flight_numbers', 'airline_registrations', 'tarif_aeronautika'],
    'user': ['dashboard', 'commercial', 'mitra_usaha']
}

AIRLINE_ROLE_MENUS = {
    'admin': ['airline_dashboard', 'manifest_upload', 'reconciliation', 'airline_users_pic'],
    'user': ['airline_dashboard', 'manifest_upload', 'reconciliation']
}


def _normalize_email(email):
    return (email or '').strip().lower()


def _get_lockout_state(email):
    norm_email = _normalize_email(email)
    if not norm_email:
        return {
            'is_locked': False,
            'remaining_seconds': 0,
            'locked_until': 0,
            'attempts': 0,
            'has_ever_locked': False
        }

    now = time.time()
    sess_map = session.get('login_lock_map') or {}
    sess_rec = sess_map.get(norm_email) or {}
    mem_rec = _LOGIN_ATTEMPT_STORE.get(norm_email) or {}

    locked_until = max(sess_rec.get('locked_until', 0), mem_rec.get('locked_until', 0))
    attempts = max(sess_rec.get('attempts', 0), mem_rec.get('attempts', 0))
    has_ever_locked = bool(sess_rec.get('has_ever_locked', False) or mem_rec.get('has_ever_locked', False))

    remaining_seconds = max(0, int(round(locked_until - now)))
    return {
        'is_locked': remaining_seconds > 0,
        'remaining_seconds': remaining_seconds,
        'locked_until': locked_until,
        'attempts': attempts,
        'has_ever_locked': has_ever_locked
    }


def _record_failed_attempt(email):
    norm_email = _normalize_email(email)
    now = time.time()
    state = _get_lockout_state(norm_email)

    if state['has_ever_locked'] and not state['is_locked']:
        new_attempts = MAX_LOGIN_ATTEMPTS
    else:
        new_attempts = state['attempts'] + 1

    if new_attempts >= MAX_LOGIN_ATTEMPTS:
        record = {
            'attempts': new_attempts,
            'locked_until': now + LOCKOUT_DURATION_SECONDS,
            'has_ever_locked': True
        }
    else:
        record = {
            'attempts': new_attempts,
            'locked_until': 0,
            'has_ever_locked': state['has_ever_locked']
        }

    if norm_email:
        sess_map = session.get('login_lock_map') or {}
        sess_map[norm_email] = record.copy()
        session['login_lock_map'] = sess_map
        _LOGIN_ATTEMPT_STORE[norm_email] = record.copy()

    return record


def _clear_failed_attempts(email):
    norm_email = _normalize_email(email)
    if not norm_email:
        return
    sess_map = session.get('login_lock_map') or {}
    if norm_email in sess_map:
        sess_map.pop(norm_email, None)
        session['login_lock_map'] = sess_map
    _LOGIN_ATTEMPT_STORE.pop(norm_email, None)


def _format_countdown(seconds):
    mins, secs = divmod(max(0, int(seconds)), 60)
    return f"{mins:02d}:{secs:02d}"


def sync_airport_session(user):
    unit_cabang = CabangModel.get_by_kode(user.get('kode_cabang'))
    allowed_cabang = CabangModel.get_allowed_cabang_codes(user.get('kode_cabang'))

    user_role = (user.get('role') or 'user').strip().lower()
    role_data = None
    try:
        role_data = RoleModel.get_by_name(user_role)
    except Exception as e:
        print(f"[WARNING] Gagal mengambil data role '{user_role}': {e}")

    if role_data and role_data.get('allowed_menus') is not None:
        allowed_menus = role_data.get('allowed_menus')
    else:
        allowed_menus = DEFAULT_ROLE_MENUS.get(user_role, ['dashboard'])

    is_profile_incomplete = not all([
        user.get('phone'),
        user.get('tgl_lahir'),
        user.get('gender')
    ])

    session['user'] = {
        'user_type': 'airport',
        'kd_user': user['kd_user'],
        'email': user['email'],
        'nama_lengkap': user['nama_lengkap'],
        'tgl_lahir': str(user['tgl_lahir']) if user.get('tgl_lahir') else '',
        'phone': user.get('phone') or '',
        'gender': user.get('gender') or '',
        'imageprofil': user.get('imageprofil') or '',
        'jabatan': user['jabatan'],
        'role': user_role,
        'kode_cabang': user.get('kode_cabang'),
        'nama_cabang': unit_cabang['nama_cabang'] if unit_cabang else '-',
        'tipe_unit': unit_cabang['tipe_unit'] if unit_cabang else None,
        'allowed_cabang': allowed_cabang,
        'allowed_menus': allowed_menus,
        'is_profile_incomplete': is_profile_incomplete
    }


sync_user_session = sync_airport_session


def sync_airline_session(airline_user):
    kode_cabang = airline_user.get('kode_cabang')
    unit_cabang = CabangModel.get_by_kode(kode_cabang)
    allowed_cabang = CabangModel.get_allowed_cabang_codes(kode_cabang)

    user_role = (airline_user.get('role') or 'user').strip().lower()
    if user_role not in ('admin', 'user'):
        user_role = 'user'

    authorized_airlines = AirlineUserModel.get_authorized_airlines(
        airline_user.get('airlines'),
        allowed_cabang_codes=allowed_cabang
    )

    session['user'] = {
        'user_type': 'airline',
        'id_airlineusers': airline_user['id_airlineusers'],
        'email': airline_user['email'],
        'nama_lengkap': airline_user['nama_lengkap'],
        'jabatan': airline_user.get('jabatan') or 'Airline Representative',
        'role': user_role,
        'kode_cabang': kode_cabang,
        'nama_cabang': unit_cabang['nama_cabang'] if unit_cabang else (kode_cabang or 'ALL CABANG'),
        'tipe_unit': unit_cabang['tipe_unit'] if unit_cabang else None,
        'allowed_cabang': allowed_cabang,
        'airlines': authorized_airlines,
        'airline_ids': [a['id_airline'] for a in authorized_airlines if 'id_airline' in a],
        'allowed_menus': AIRLINE_ROLE_MENUS.get(user_role, ['airline_dashboard'])
    }


def redirect_by_user_type():
    user = session.get('user')
    if not user:
        return redirect(url_for('auth.login'))
    if user.get('user_type') == 'airline':
        return redirect(url_for('airline_portal.dashboard'))
    return redirect(url_for('dashboard.index'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect_by_user_type()

    if request.method == 'POST':
        email_input = (request.form.get('email') or '').strip()
        lock_state = _get_lockout_state(email_input)

        # Cek blokir HANYA untuk email yang sedang disubmit
        if lock_state['is_locked']:
            sisa_waktu = _format_countdown(lock_state['remaining_seconds'])
            flash(
                f"Akun {email_input} sementara diblokir karena 3x percobaan gagal. Silakan tunggu {sisa_waktu} sebelum mencoba kembali.",
                "danger"
            )
            return render_template(
                'auth/login.html',
                lockout_remaining=lock_state['remaining_seconds'],
                locked_email=email_input,
                last_email=email_input
            )

        password = request.form.get('password')
        remember_me = request.form.get('remember') is not None

        # 1. Cek ke database Internal Airport (users)
        airport_user = UserModel.verify_login(email_input, password)
        if airport_user:
            _clear_failed_attempts(email_input)
            session.permanent = remember_me
            sync_airport_session(airport_user)
            return redirect(url_for('dashboard.index'))

        # 2. Jika tidak ada di internal, cek ke database Airline (airline_users)
        airline_user, airline_err = AirlineUserModel.verify_login(email_input, password)
        if airline_user:
            _clear_failed_attempts(email_input)
            session.permanent = remember_me
            sync_airline_session(airline_user)
            return redirect(url_for('airline_portal.dashboard'))

        # 3. Gagal login -> Catat percobaan gagal khusus untuk email ini saja
        updated_record = _record_failed_attempt(email_input)
        attempts = updated_record['attempts']
        remaining_attempts = max(0, MAX_LOGIN_ATTEMPTS - attempts)

        if updated_record['locked_until'] > time.time():
            sisa_detik = int(round(updated_record['locked_until'] - time.time()))
            sisa_waktu = _format_countdown(sisa_detik)
            base_msg = airline_err or "Email atau password salah!"
            flash(
                f"{base_msg} Batas 3x percobaan untuk {email_input} terlampaui. Silakan tunggu {sisa_waktu} untuk login berikutnya.",
                "danger"
            )
            return render_template(
                'auth/login.html',
                lockout_remaining=sisa_detik,
                locked_email=email_input,
                last_email=email_input
            )
        else:
            base_msg = airline_err or "Email atau password salah!"
            flash(
                f"{base_msg} Sisa percobaan login: {remaining_attempts} kali lagi.",
                "warning"
            )
            return render_template(
                'auth/login.html',
                lockout_remaining=0,
                locked_email='',
                remaining_attempts=remaining_attempts,
                last_email=email_input
            )

    return render_template(
        'auth/login.html',
        lockout_remaining=0,
        locked_email='',
        last_email=''
    )


@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('auth.login'))