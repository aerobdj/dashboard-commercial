from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.user_model import UserModel
from app.models.cabang_model import CabangModel
from app.models.role_model import RoleModel

auth_bp = Blueprint('auth', __name__)

DEFAULT_ROLE_MENUS = {
    'superadmin': ['dashboard', 'commercial', 'mitra_usaha', 'users', 'cabang', 'coa_pendapatan', 'role_access', 'airlines'],
    'admin': ['dashboard', 'commercial', 'mitra_usaha', 'airlines'],
    'pengawas': ['dashboard', 'commercial', 'mitra_usaha', 'users', 'airlines'],
    'user': ['dashboard', 'commercial', 'mitra_usaha']
}

def sync_user_session(user):
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
        'kd_user': user['kd_user'],
        'email': user['email'],
        'nama_lengkap': user['nama_lengkap'],
        'tgl_lahir': str(user['tgl_lahir']) if user.get('tgl_lahir') else '',
        'phone': user.get('phone') or '',
        'gender': user.get('gender') or '',
        'imageprofil': user.get('imageprofil') or '',  # Path pendek: 'static/images/faces/user_1_xxx.jpg'
        'jabatan': user['jabatan'],
        'role': user_role,
        'kode_cabang': user.get('kode_cabang'),
        'nama_cabang': unit_cabang['nama_cabang'] if unit_cabang else '-',
        'tipe_unit': unit_cabang['tipe_unit'] if unit_cabang else None,
        'allowed_cabang': allowed_cabang,
        'allowed_menus': allowed_menus,
        'is_profile_incomplete': is_profile_incomplete
    }

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' in session:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = UserModel.verify_login(email, password)
        if user:
            sync_user_session(user)
            return redirect(url_for('dashboard.index'))
        else:
            flash('Email atau password salah!', 'danger')

    return render_template('auth/login.html')

@auth_bp.route('/logout')
def logout():
    session.pop('user', None)
    flash('Anda telah keluar dari sistem.', 'info')
    return redirect(url_for('auth.login'))