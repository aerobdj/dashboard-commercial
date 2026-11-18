from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import app
from app.models.airline_user_model import AirlineUserModel
from app.models.airline_model import AirlineModel
from app.utils.decorators import menu_required

airline_user_bp = Blueprint('airline_user', __name__, url_prefix='/aeronautika/setting/airlines-users')

ALLOWED_ROLES = {'superadmin', 'pengawas'}


def _get_role(user):
    return (user.get('role') or '').strip().lower()


def _get_current_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _get_all_cabang():
    res = app.supabase.table("cabang").select("*").order("kode_cabang", desc=False).execute()
    rows = res.data or []
    # Filter soft-deleted jika tabel cabang memiliki kolom delete_at
    return [c for c in rows if c.get("delete_at") is None]


def _get_accessible_cabang_list(user):
    """
    Hierarki cabang:
    - Superadmin / HO: semua cabang
    - Region: cabang induk + cabang anak di bawah region tsb
    - Cabang: hanya cabang user itu sendiri
    """
    all_cabang = _get_all_cabang()
    role = _get_role(user)
    user_kode = (user.get("kode_cabang") or "").strip().upper()

    if role == "superadmin" or user_kode == "HO":
        return all_cabang

    user_cab_obj = next(
        (c for c in all_cabang if (c.get("kode_cabang") or "").strip().upper() == user_kode),
        None,
    )
    tipe = (user_cab_obj.get("tipe") or user_cab_obj.get("level") or "").strip().lower() if user_cab_obj else ""

    if tipe == "region" or user_kode.startswith("REG"):
        allowed = []
        for c in all_cabang:
            kode = (c.get("kode_cabang") or "").strip().upper()
            parent = (
                c.get("parent_kode")
                or c.get("induk_cabang")
                or c.get("kode_region")
                or c.get("region")
                or ""
            ).strip().upper()
            if kode == user_kode or parent == user_kode:
                allowed.append(c)
        return allowed

    return [c for c in all_cabang if (c.get("kode_cabang") or "").strip().upper() == user_kode]


@airline_user_bp.route('/')
@menu_required('airlines_users')
def index():
    user = session.get('user', {})
    role = _get_role(user)

    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses ke menu Airlines Users.', 'danger')
        return redirect(url_for('dashboard.index'))

    is_superadmin = (role == 'superadmin')
    cabang_list = _get_accessible_cabang_list(user)
    allowed_codes = [(c.get('kode_cabang') or '').strip().upper() for c in cabang_list]

    # HO / Superadmin tidak perlu filter in_ agar data tetap tampil meskipun ada kode historis
    filter_codes = None if (is_superadmin or (user.get('kode_cabang') or '').strip().upper() == 'HO') else allowed_codes

    airline_users = AirlineUserModel.get_all(
        include_deleted=is_superadmin,
        allowed_cabang_codes=filter_codes
    )
    airline_list = AirlineModel.get_all(include_deleted=False)
    airline_map = {a['id_airline']: a for a in airline_list}
    cabang_map = {(c.get('kode_cabang') or '').strip().upper(): c for c in _get_all_cabang()}

    return render_template(
        'aeronautika/airlines_users.html',
        airline_users=airline_users,
        airline_list=airline_list,
        airline_map=airline_map,
        cabang_list=cabang_list,
        cabang_map=cabang_map,
        is_superadmin=is_superadmin,
    )


@airline_user_bp.route('/create', methods=['POST'])
@menu_required('airlines_users')
def create():
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses untuk menambah Airlines User.', 'danger')
        return redirect(url_for('airline_user.index'))

    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    nama_lengkap = (request.form.get('nama_lengkap') or '').strip()
    jabatan = (request.form.get('jabatan') or '').strip()
    target_role = (request.form.get('role') or 'user').strip().lower()
    status_val = (request.form.get('status') or '1').strip().lower() in ('1', 'true', 'active', 'on')
    kode_cabang = (request.form.get('kode_cabang') or '').strip().upper()
    selected_airlines = request.form.getlist('airlines')

    if not email or not password or not nama_lengkap or not jabatan or not kode_cabang:
        flash('Email, Password, Nama Lengkap, Jabatan, dan Cabang wajib diisi.', 'warning')
        return redirect(url_for('airline_user.index'))

    if target_role not in ('user', 'admin'):
        flash('Role hanya diperbolehkan User atau Admin.', 'warning')
        return redirect(url_for('airline_user.index'))

    if not selected_airlines:
        flash('Pilih minimal 1 Airline untuk akun pengguna ini.', 'warning')
        return redirect(url_for('airline_user.index'))

    cabang_list = _get_accessible_cabang_list(user)
    allowed_codes = {(c.get('kode_cabang') or '').strip().upper() for c in cabang_list}
    if role != 'superadmin' and (user.get('kode_cabang') or '').strip().upper() != 'HO' and kode_cabang not in allowed_codes:
        flash('Anda tidak memiliki wewenang membuat akun pada cabang tersebut.', 'danger')
        return redirect(url_for('airline_user.index'))

    if AirlineUserModel.email_exists(email):
        flash(f'Email {email} sudah terdaftar pada Airlines Users.', 'warning')
        return redirect(url_for('airline_user.index'))

    try:
        AirlineUserModel.create(
            {
                "email": email,
                "password": password,
                "nama_lengkap": nama_lengkap,
                "jabatan": jabatan,
                "role": target_role,
                "status": status_val,
                "kode_cabang": kode_cabang,
                "airlines": selected_airlines,
            },
            created_by=_get_current_actor(user),
        )
        flash('Akun Airlines User berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan Airlines User: {str(e)}', 'danger')
    return redirect(url_for('airline_user.index'))


@airline_user_bp.route('/update/<int:id_airlineusers>', methods=['POST'])
@menu_required('airlines_users')
def update(id_airlineusers):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses untuk mengubah Airlines User.', 'danger')
        return redirect(url_for('airline_user.index'))

    existing = AirlineUserModel.get_by_id(id_airlineusers)
    if not existing:
        flash('Data Airlines User tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('airline_user.index'))

    cabang_list = _get_accessible_cabang_list(user)
    allowed_codes = {(c.get('kode_cabang') or '').strip().upper() for c in cabang_list}
    is_ho_or_sa = (role == 'superadmin' or (user.get('kode_cabang') or '').strip().upper() == 'HO')

    if not is_ho_or_sa and (existing.get('kode_cabang') or '').strip().upper() not in allowed_codes:
        flash('Anda tidak memiliki wewenang mengubah akun di luar hierarki cabang Anda.', 'danger')
        return redirect(url_for('airline_user.index'))

    email = (request.form.get('email') or '').strip().lower()
    password = request.form.get('password') or ''
    nama_lengkap = (request.form.get('nama_lengkap') or '').strip()
    jabatan = (request.form.get('jabatan') or '').strip()
    target_role = (request.form.get('role') or 'user').strip().lower()
    status_val = (request.form.get('status') or '1').strip().lower() in ('1', 'true', 'active', 'on')
    kode_cabang = (request.form.get('kode_cabang') or '').strip().upper()
    selected_airlines = request.form.getlist('airlines')

    if not email or not nama_lengkap or not jabatan or not kode_cabang:
        flash('Email, Nama Lengkap, Jabatan, dan Cabang wajib diisi.', 'warning')
        return redirect(url_for('airline_user.index'))

    if target_role not in ('user', 'admin'):
        flash('Role hanya diperbolehkan User atau Admin.', 'warning')
        return redirect(url_for('airline_user.index'))

    if not selected_airlines:
        flash('Pilih minimal 1 Airline untuk akun pengguna ini.', 'warning')
        return redirect(url_for('airline_user.index'))

    if not is_ho_or_sa and kode_cabang not in allowed_codes:
        flash('Cabang tujuan berada di luar hierarki Anda.', 'danger')
        return redirect(url_for('airline_user.index'))

    if AirlineUserModel.email_exists(email, exclude_id=id_airlineusers):
        flash(f'Email {email} sudah digunakan oleh akun Airlines User lain.', 'warning')
        return redirect(url_for('airline_user.index'))

    try:
        AirlineUserModel.update(
            id_airlineusers,
            {
                "email": email,
                "password": password,
                "nama_lengkap": nama_lengkap,
                "jabatan": jabatan,
                "role": target_role,
                "status": status_val,
                "kode_cabang": kode_cabang,
                "airlines": selected_airlines,
            },
            updated_by=_get_current_actor(user),
        )
        flash('Data Airlines User berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui Airlines User: {str(e)}', 'danger')
    return redirect(url_for('airline_user.index'))


@airline_user_bp.route('/toggle-status/<int:id_airlineusers>', methods=['POST'])
@menu_required('airlines_users')
def toggle_status(id_airlineusers):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses untuk mengubah status Airlines User.', 'danger')
        return redirect(url_for('airline_user.index'))

    existing = AirlineUserModel.get_by_id(id_airlineusers)
    if not existing:
        flash('Data Airlines User tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('airline_user.index'))

    cabang_list = _get_accessible_cabang_list(user)
    allowed_codes = {(c.get('kode_cabang') or '').strip().upper() for c in cabang_list}
    is_ho_or_sa = (role == 'superadmin' or (user.get('kode_cabang') or '').strip().upper() == 'HO')

    if not is_ho_or_sa and (existing.get('kode_cabang') or '').strip().upper() not in allowed_codes:
        flash('Anda tidak memiliki wewenang mengubah status akun di luar hierarki cabang Anda.', 'danger')
        return redirect(url_for('airline_user.index'))

    current_status = bool(existing.get('status', True))
    new_status = not current_status

    try:
        AirlineUserModel.toggle_status(
            id_airlineusers,
            new_status=new_status,
            updated_by=_get_current_actor(user),
        )
        label = 'diaktifkan' if new_status else 'dinonaktifkan'
        flash(f"Akun {existing.get('nama_lengkap')} berhasil {label}!", 'success')
    except Exception as e:
        flash(f'Gagal mengubah status akun: {str(e)}', 'danger')
    return redirect(url_for('airline_user.index'))


@airline_user_bp.route('/delete/<int:id_airlineusers>', methods=['POST'])
@menu_required('airlines_users')
def delete(id_airlineusers):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses untuk menghapus Airlines User.', 'danger')
        return redirect(url_for('airline_user.index'))

    existing = AirlineUserModel.get_by_id(id_airlineusers)
    if not existing:
        flash('Data Airlines User tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('airline_user.index'))

    cabang_list = _get_accessible_cabang_list(user)
    allowed_codes = {(c.get('kode_cabang') or '').strip().upper() for c in cabang_list}
    is_ho_or_sa = (role == 'superadmin' or (user.get('kode_cabang') or '').strip().upper() == 'HO')

    if not is_ho_or_sa and (existing.get('kode_cabang') or '').strip().upper() not in allowed_codes:
        flash('Anda tidak memiliki wewenang menghapus akun di luar hierarki cabang Anda.', 'danger')
        return redirect(url_for('airline_user.index'))

    try:
        AirlineUserModel.delete(id_airlineusers, deleted_by=_get_current_actor(user))
        flash('Akun Airlines User berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus Airlines User: {str(e)}', 'danger')
    return redirect(url_for('airline_user.index'))


@airline_user_bp.route('/restore/<int:id_airlineusers>', methods=['POST'])
@menu_required('airlines_users')
def restore(id_airlineusers):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali akun terhapus.', 'danger')
        return redirect(url_for('airline_user.index'))

    try:
        AirlineUserModel.restore(id_airlineusers, restored_by=_get_current_actor(user))
        flash('Akun Airlines User berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali Airlines User: {str(e)}', 'danger')
    return redirect(url_for('airline_user.index'))