import os
import time
import base64
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from app.models.user_model import UserModel
from app.models.cabang_model import CabangModel
from app.models.role_model import RoleModel
from app.controllers.auth_controller import sync_user_session
from app.utils.decorators import menu_required

user_bp = Blueprint('users', __name__, url_prefix='/settings/users')


def _get_current_actor():
    """Ambil identitas user yang sedang login untuk audit trail."""
    current_user = session.get('user') or {}
    nama = current_user.get('nama_lengkap')
    email = current_user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _is_superadmin():
    return (session.get('user') or {}).get('role') == 'superadmin'


def _get_user_scope():
    """
    Menentukan cakupan cabang berdasarkan unit user yang sedang login:
    - HO atau Superadmin: semua cabang (allowed_codes = None)
    - REG: unit REG itu sendiri + seluruh cabang di bawah regional tersebut
    - Cabang (mis. BDJ): hanya cabang tersebut saja
    Mengembalikan tuple: (allowed_codes_or_none, filtered_cabang_list)
    """
    all_cabang = CabangModel.get_all()
    current_user = session.get('user') or {}
    user_cabang = (current_user.get('kode_cabang') or '').strip().upper()
    role = (current_user.get('role') or '').strip().lower()

    cabang_map = {(c.get('kode_cabang') or '').strip().upper(): c for c in all_cabang}
    current_unit = cabang_map.get(user_cabang, {})
    tipe_unit = (current_unit.get('tipe_unit') or '').strip().upper()

    # HO atau Superadmin melihat semua cabang
    if role == 'superadmin' or tipe_unit == 'HO' or user_cabang == 'HO':
        return None, all_cabang

    # Regional (REG): unit REG itu sendiri + cabang-cabang di bawahnya
    if tipe_unit == 'REG' or user_cabang.startswith('REG'):
        allowed_codes = {user_cabang}
        for c in all_cabang:
            kode = (c.get('kode_cabang') or '').strip().upper()
            parent = (
                c.get('parent_kode')
                or c.get('kode_regional')
                or c.get('regional')
                or c.get('induk_cabang')
                or ''
            ).strip().upper()
            if parent == user_cabang:
                allowed_codes.add(kode)

        filtered_cabang = [
            c for c in all_cabang
            if (c.get('kode_cabang') or '').strip().upper() in allowed_codes
        ]
        return list(allowed_codes), filtered_cabang

    # Cabang biasa (contoh: BDJ): hanya cabang miliknya sendiri
    if user_cabang:
        filtered_cabang = [
            c for c in all_cabang
            if (c.get('kode_cabang') or '').strip().upper() == user_cabang
        ]
        return [user_cabang], filtered_cabang

    return [], []


def save_avatar_to_static(kd_user, data_url, old_image_path=None):
    """Simpan gambar hasil crop ke app/static/static/images/faces/ dan kembalikan path relatifnya."""
    if not data_url or not data_url.startswith('data:image/'):
        return None

    try:
        header, encoded = data_url.split(',', 1)
        img_bytes = base64.b64decode(encoded)

        faces_dir = os.path.join(current_app.static_folder, 'static', 'images', 'faces')
        os.makedirs(faces_dir, exist_ok=True)

        if old_image_path and old_image_path.startswith('static/images/faces/user_'):
            old_full_path = os.path.join(current_app.static_folder, old_image_path)
            if os.path.exists(old_full_path):
                try:
                    os.remove(old_full_path)
                except OSError:
                    pass

        filename = f"user_{kd_user}_{int(time.time())}.jpg"
        file_path = os.path.join(faces_dir, filename)

        with open(file_path, 'wb') as f:
            f.write(img_bytes)

        return f"static/images/faces/{filename}"
    except Exception as e:
        print(f"[ERROR] Gagal menyimpan file avatar: {e}")
        return None


@user_bp.route('/')
@menu_required('users')
def index():
    is_superadmin = _is_superadmin()
    allowed_codes, cabang_list = _get_user_scope()
    users = UserModel.get_all(
        include_deleted=is_superadmin,
        allowed_cabang_codes=allowed_codes
    )
    roles = RoleModel.get_all()

    # Role selain superadmin tidak boleh membuat/mengedit user menjadi superadmin
    if not is_superadmin:
        roles = [r for r in roles if (r.get('nama_role') or '').lower() != 'superadmin']

    return render_template(
        'settings/users.html',
        users=users,
        cabang_list=cabang_list,
        roles=roles,
        is_superadmin=is_superadmin,
        can_select_cabang=(allowed_codes is None or len(allowed_codes) > 1)
    )


@user_bp.route('/create', methods=['POST'])
@menu_required('users')
def create():
    is_superadmin = _is_superadmin()
    allowed_codes, _ = _get_user_scope()

    email = request.form.get('email')
    password = request.form.get('password')
    nama_lengkap = request.form.get('nama_lengkap')
    jabatan = request.form.get('jabatan')
    role = request.form.get('role')
    kode_cabang = (request.form.get('kode_cabang') or '').strip().upper()

    # Kunci kode_cabang jika user hanya memiliki akses 1 cabang (misal BDJ)
    if allowed_codes is not None:
        if len(allowed_codes) == 1:
            kode_cabang = allowed_codes[0]
        elif kode_cabang not in allowed_codes:
            flash('Anda tidak memiliki akses untuk menambahkan user di cabang tersebut.', 'danger')
            return redirect(url_for('users.index'))

    if not is_superadmin and (role or '').lower() == 'superadmin':
        flash('Anda tidak memiliki wewenang membuat akun Superadmin.', 'danger')
        return redirect(url_for('users.index'))

    try:
        UserModel.create(
            email=email,
            password=password,
            nama_lengkap=nama_lengkap,
            jabatan=jabatan,
            role=role,
            kode_cabang=kode_cabang,
            created_by=_get_current_actor()
        )
        flash('User berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan user: {str(e)}', 'danger')
    return redirect(url_for('users.index'))


@user_bp.route('/update/<int:kd_user>', methods=['POST'])
@menu_required('users')
def update(kd_user):
    is_superadmin = _is_superadmin()
    allowed_codes, _ = _get_user_scope()

    target_user = UserModel.get_by_id(kd_user)
    if not target_user:
        flash('Data user tidak ditemukan.', 'danger')
        return redirect(url_for('users.index'))

    target_cabang = (target_user.get('kode_cabang') or '').strip().upper()
    if allowed_codes is not None and target_cabang not in allowed_codes:
        flash('Anda tidak memiliki akses untuk mengubah user dari cabang lain.', 'danger')
        return redirect(url_for('users.index'))

    email = request.form.get('email')
    password = request.form.get('password')
    nama_lengkap = request.form.get('nama_lengkap')
    jabatan = request.form.get('jabatan')
    role = request.form.get('role')
    kode_cabang = (request.form.get('kode_cabang') or target_cabang).strip().upper()

    if allowed_codes is not None:
        if len(allowed_codes) == 1:
            kode_cabang = allowed_codes[0]
        elif kode_cabang not in allowed_codes:
            flash('Anda tidak memiliki akses memindahkan user ke cabang tersebut.', 'danger')
            return redirect(url_for('users.index'))

    if not is_superadmin and ((role or '').lower() == 'superadmin' or (target_user.get('role') or '').lower() == 'superadmin'):
        flash('Anda tidak memiliki wewenang mengubah data atau role Superadmin.', 'danger')
        return redirect(url_for('users.index'))

    try:
        UserModel.update_admin(
            kd_user=kd_user,
            email=email,
            nama_lengkap=nama_lengkap,
            jabatan=jabatan,
            role=role,
            kode_cabang=kode_cabang,
            password=password,
            updated_by=_get_current_actor()
        )
        if session.get('user') and session['user']['kd_user'] == kd_user:
            fresh_user = UserModel.get_by_id(kd_user)
            if fresh_user:
                sync_user_session(fresh_user)
        flash('Data user berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui user: {str(e)}', 'danger')
    return redirect(url_for('users.index'))


@user_bp.route('/delete/<int:kd_user>', methods=['POST'])
@menu_required('users')
def delete(kd_user):
    is_superadmin = _is_superadmin()
    allowed_codes, _ = _get_user_scope()

    try:
        if session.get('user') and session['user'].get('kd_user') == kd_user:
            flash('Anda tidak dapat menghapus akun Anda sendiri yang sedang aktif.', 'warning')
            return redirect(url_for('users.index'))

        target_user = UserModel.get_by_id(kd_user)
        if not target_user:
            flash('Data user tidak ditemukan.', 'danger')
            return redirect(url_for('users.index'))

        target_cabang = (target_user.get('kode_cabang') or '').strip().upper()
        if allowed_codes is not None and target_cabang not in allowed_codes:
            flash('Anda tidak memiliki akses untuk menghapus user dari cabang lain.', 'danger')
            return redirect(url_for('users.index'))

        if not is_superadmin and (target_user.get('role') or '').lower() == 'superadmin':
            flash('Anda tidak memiliki wewenang menghapus akun Superadmin.', 'danger')
            return redirect(url_for('users.index'))

        UserModel.delete(kd_user, deleted_by=_get_current_actor())
        flash('User berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus user: {str(e)}', 'danger')
    return redirect(url_for('users.index'))


@user_bp.route('/restore/<int:kd_user>', methods=['POST'])
@menu_required('users')
def restore(kd_user):
    if not _is_superadmin():
        flash('Hanya Superadmin yang dapat mengaktifkan kembali akun terhapus.', 'danger')
        return redirect(url_for('users.index'))

    try:
        UserModel.restore(kd_user, restored_by=_get_current_actor())
        flash('Akun user berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali user: {str(e)}', 'danger')
    return redirect(url_for('users.index'))


@user_bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        return redirect(url_for('auth.login'))

    kd_user = session['user']['kd_user']
    user = UserModel.get_by_id(kd_user)

    if request.method == 'POST':
        nama_lengkap = request.form.get('nama_lengkap')
        email = request.form.get('email')
        phone = request.form.get('phone')
        tgl_lahir = request.form.get('tgl_lahir')
        gender = request.form.get('gender')
        password = request.form.get('password')
        cropped_avatar = request.form.get('cropped_avatar')

        saved_image_path = None
        if cropped_avatar:
            saved_image_path = save_avatar_to_static(
                kd_user=kd_user,
                data_url=cropped_avatar,
                old_image_path=user.get('imageprofil')
            )

        try:
            UserModel.update_profile(
                kd_user=kd_user,
                nama_lengkap=nama_lengkap,
                email=email,
                phone=phone,
                tgl_lahir=tgl_lahir,
                gender=gender,
                imageprofil=saved_image_path,
                password=password,
                updated_by=_get_current_actor()
            )
            fresh_user = UserModel.get_by_id(kd_user)
            if fresh_user:
                sync_user_session(fresh_user)
            flash('Profil akun berhasil diperbarui!', 'success')
        except Exception as e:
            flash(f'Gagal menyimpan profil: {str(e)}', 'danger')

        return redirect(url_for('users.profile'))

    return render_template('settings/account_profile.html', user=user)