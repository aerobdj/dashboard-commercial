from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.role_model import RoleModel
from app.models.user_model import UserModel
from app.controllers.auth_controller import sync_user_session
from app.utils.decorators import menu_required

roles_bp = Blueprint('roles', __name__, url_prefix='/settings/roles')

# Daftar seluruh menu yang bisa diatur hak aksesnya
AVAILABLE_MENUS = [
    {'key': 'dashboard', 'label': 'Dashboard Utama', 'group': 'Main Menu'},
    {'key': 'mitra_usaha', 'label': 'Mitra Usaha', 'group': 'Commercial'},
    {'key': 'aeronautika_admin', 'label': 'Administrasi', 'group': 'Aeronautika'},
    {'key': 'aeronautika_ops', 'label': 'Operasional', 'group': 'Aeronautika'},
    {'key': 'aeronautika_tools', 'label': 'Operasional - Tools (Picture to PDF & Pax Rekon)', 'group': 'Aeronautika'},
    {'key': 'airlines', 'label': 'Setting - Airlines', 'group': 'Aeronautika'},
    {'key': 'airlines_users', 'label': 'Setting - Airlines Users', 'group': 'Aeronautika'},
    {'key': 'tarif_aeronautika', 'label': 'Setting - Tarif', 'group': 'Aeronautika'},
    {'key': 'routes', 'label': 'Setting - Route', 'group': 'Aeronautika'},
    {'key': 'airline_registrations', 'label': 'Setting - Registration', 'group': 'Aeronautika'},
    {'key': 'flight_numbers', 'label': 'Setting - Number Flight', 'group': 'Aeronautika'},
    {'key': 'users', 'label': 'Manajemen Users', 'group': 'Setting'},
    {'key': 'cabang', 'label': 'Cabang Perusahaan', 'group': 'Setting'},
    {'key': 'coa_pendapatan', 'label': 'COA Pendapatan', 'group': 'Setting'},
    {'key': 'role_access', 'label': 'Role Access', 'group': 'Setting'},
    {'key': 'master_ppn', 'label': 'PPN', 'group': 'Setting'},
]

@roles_bp.route('/')
@menu_required('role_access')
def index():
    roles = RoleModel.get_all()
    return render_template('settings/role_access.html', roles=roles, available_menus=AVAILABLE_MENUS)

@roles_bp.route('/create', methods=['POST'])
@menu_required('role_access')
def create():
    nama_role = request.form.get('nama_role')
    deskripsi = request.form.get('deskripsi')
    allowed_menus = request.form.getlist('allowed_menus')

    try:
        RoleModel.create(nama_role, deskripsi, allowed_menus)
        flash('Role baru berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan role: {str(e)}', 'danger')
    return redirect(url_for('roles.index'))

@roles_bp.route('/update/<int:id_role>', methods=['POST'])
@menu_required('role_access')
def update(id_role):
    nama_role = request.form.get('nama_role')
    deskripsi = request.form.get('deskripsi')
    allowed_menus = request.form.getlist('allowed_menus')

    try:
        RoleModel.update(id_role, nama_role, deskripsi, allowed_menus)
        # Sinkronisasi ulang session jika role user yang sedang login ikut diubah
        if session.get('user') and session['user'].get('role') == nama_role:
            fresh_user = UserModel.get_by_id(session['user']['kd_user'])
            if fresh_user:
                sync_user_session(fresh_user)
        flash('Hak akses role berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui role: {str(e)}', 'danger')
    return redirect(url_for('roles.index'))

@roles_bp.route('/delete/<int:id_role>', methods=['POST'])
@menu_required('role_access')
def delete(id_role):
    try:
        RoleModel.delete(id_role)
        flash('Role berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus role (pastikan tidak sedang dipakai user): {str(e)}', 'danger')
    return redirect(url_for('roles.index'))