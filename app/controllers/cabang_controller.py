from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from functools import wraps
from app.models.cabang_model import CabangModel
from app.utils.decorators import menu_required

cabang_bp = Blueprint('cabang', __name__, url_prefix='/setting/cabang')

TIPE_UNITS = ['HO', 'REGIONAL', 'CABANG']


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def _get_current_actor():
    current_user = session.get('user') or {}
    nama = current_user.get('nama_lengkap')
    email = current_user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _is_superadmin():
    return (session.get('user') or {}).get('role') == 'superadmin'


def _get_cabang_scope():
    """Menentukan daftar kode_cabang yang boleh diakses user login."""
    if _is_superadmin():
        return None
    user_cabang = ((session.get('user') or {}).get('kode_cabang') or '').strip().upper()
    if not user_cabang:
        return []
    return CabangModel.get_allowed_cabang_codes(user_cabang)


@cabang_bp.route('/')
@menu_required('cabang')
@login_required
def index():
    is_superadmin = _is_superadmin()
    allowed_codes = _get_cabang_scope()

    cabang_list = CabangModel.get_all(
        include_deleted=is_superadmin,
        allowed_cabang_codes=allowed_codes
    )
    parents = CabangModel.get_parents()
    return render_template(
        'settings/cabang.html',
        cabang_list=cabang_list,
        parents=parents,
        tipe_units=TIPE_UNITS,
        is_superadmin=is_superadmin
    )


@cabang_bp.route('/create', methods=['POST'])
@menu_required('cabang')
@login_required
def create():
    kode_cabang = request.form.get('kode_cabang', '').strip().upper()
    nama_cabang = request.form.get('nama_cabang')
    tipe_unit = request.form.get('tipe_unit')
    parent_kode = request.form.get('parent_kode') or None
    kota = request.form.get('kota')
    status_aktif = True if request.form.get('status_aktif') == 'on' else False
    status_bandara = request.form.getlist('status')

    if tipe_unit == 'HO':
        parent_kode = None

    existing = CabangModel.get_by_kode(kode_cabang, include_deleted=True)
    if existing:
        if existing.get('deleted_at'):
            flash(
                f'Kode Cabang "{kode_cabang}" sudah ada di data terhapus. Hubungi Superadmin untuk mengaktifkannya kembali.',
                'warning'
            )
        else:
            flash(f'Kode Cabang "{kode_cabang}" sudah terdaftar!', 'danger')
        return redirect(url_for('cabang.index'))

    try:
        CabangModel.create(
            kode_cabang=kode_cabang,
            nama_cabang=nama_cabang,
            tipe_unit=tipe_unit,
            parent_kode=parent_kode,
            kota=kota,
            status_aktif=status_aktif,
            status=status_bandara,
            created_by=_get_current_actor()
        )
        flash('Data cabang berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambah cabang: {str(e)}', 'danger')

    return redirect(url_for('cabang.index'))


@cabang_bp.route('/update/<string:old_kode>', methods=['POST'])
@menu_required('cabang')
@login_required
def update(old_kode):
    old_kode = old_kode.strip().upper()
    allowed_codes = _get_cabang_scope()
    if allowed_codes is not None and old_kode not in allowed_codes:
        flash('Anda tidak memiliki akses untuk mengubah cabang tersebut.', 'danger')
        return redirect(url_for('cabang.index'))

    kode_cabang = request.form.get('kode_cabang', '').strip().upper()
    nama_cabang = request.form.get('nama_cabang')
    tipe_unit = request.form.get('tipe_unit')
    parent_kode = request.form.get('parent_kode') or None
    kota = request.form.get('kota')
    status_aktif = True if request.form.get('status_aktif') == 'on' else False
    status_bandara = request.form.getlist('status')

    if tipe_unit == 'HO':
        parent_kode = None

    if parent_kode == kode_cabang:
        flash('Unit induk tidak boleh merujuk ke dirinya sendiri!', 'danger')
        return redirect(url_for('cabang.index'))

    try:
        CabangModel.update(
            old_kode_cabang=old_kode,
            kode_cabang=kode_cabang,
            nama_cabang=nama_cabang,
            tipe_unit=tipe_unit,
            parent_kode=parent_kode,
            kota=kota,
            status_aktif=status_aktif,
            status=status_bandara,
            updated_by=_get_current_actor()
        )
        flash('Data cabang berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui cabang: {str(e)}', 'danger')

    return redirect(url_for('cabang.index'))


@cabang_bp.route('/delete/<string:kode_cabang>', methods=['POST'])
@menu_required('cabang')
@login_required
def delete(kode_cabang):
    kode_cabang = kode_cabang.strip().upper()
    allowed_codes = _get_cabang_scope()
    if allowed_codes is not None and kode_cabang not in allowed_codes:
        flash('Anda tidak memiliki akses untuk menghapus cabang tersebut.', 'danger')
        return redirect(url_for('cabang.index'))

    try:
        if CabangModel.has_active_children(kode_cabang):
            flash(f'Cabang "{kode_cabang}" tidak dapat dihapus karena masih memiliki sub-unit aktif.', 'warning')
            return redirect(url_for('cabang.index'))

        if CabangModel.has_active_users(kode_cabang):
            flash(f'Cabang "{kode_cabang}" tidak dapat dihapus karena masih memiliki user aktif yang terhubung.', 'warning')
            return redirect(url_for('cabang.index'))

        CabangModel.delete(kode_cabang, deleted_by=_get_current_actor())
        flash(f'Cabang "{kode_cabang}" berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus cabang: {str(e)}', 'danger')

    return redirect(url_for('cabang.index'))


@cabang_bp.route('/restore/<string:kode_cabang>', methods=['POST'])
@menu_required('cabang')
@login_required
def restore(kode_cabang):
    if not _is_superadmin():
        flash('Hanya Superadmin yang dapat mengaktifkan kembali cabang terhapus.', 'danger')
        return redirect(url_for('cabang.index'))

    kode_cabang = kode_cabang.strip().upper()
    try:
        CabangModel.restore(kode_cabang, restored_by=_get_current_actor())
        flash(f'Cabang "{kode_cabang}" berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali cabang: {str(e)}', 'danger')

    return redirect(url_for('cabang.index'))