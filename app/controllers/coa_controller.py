from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.coa_model import CoaModel
from app.utils.decorators import menu_required

coa_bp = Blueprint('coa', __name__, url_prefix='/settings/coa-pendapatan')


def _get_current_actor():
    current_user = session.get('user') or {}
    nama = current_user.get('nama_lengkap')
    email = current_user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _is_superadmin():
    return (session.get('user') or {}).get('role') == 'superadmin'


@coa_bp.route('/')
@menu_required('coa_pendapatan')
def index():
    is_superadmin = _is_superadmin()
    coa_list = CoaModel.get_all(include_deleted=is_superadmin)
    sub_klasifikasi_list = sorted(
        list({item['sub_klasifikasi'] for item in coa_list if item.get('sub_klasifikasi') and not item.get('deleted_at')})
    )
    return render_template(
        'settings/coa_pendapatan.html',
        coa_list=coa_list,
        sub_klasifikasi_list=sub_klasifikasi_list,
        is_superadmin=is_superadmin
    )


@coa_bp.route('/create', methods=['POST'])
@menu_required('coa_pendapatan')
def create():
    kode_account = (request.form.get('kode_account') or '').strip()
    klasifikasi = request.form.get('klasifikasi')
    sub_klasifikasi = request.form.get('sub_klasifikasi')
    deskripsi_coa = request.form.get('deskripsi_coa')

    existing = CoaModel.get_by_kode(kode_account, include_deleted=True)
    if existing:
        if existing.get('deleted_at'):
            flash(
                f'Kode Account "{kode_account}" sudah ada di data terhapus. Hubungi Superadmin untuk mengaktifkannya kembali.',
                'warning'
            )
        else:
            flash(f'Kode Account "{kode_account}" sudah terdaftar!', 'danger')
        return redirect(url_for('coa.index'))

    try:
        CoaModel.create(
            kode_account=kode_account,
            klasifikasi=klasifikasi,
            sub_klasifikasi=sub_klasifikasi,
            deskripsi_coa=deskripsi_coa,
            created_by=_get_current_actor()
        )
        flash('Data COA Pendapatan berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan COA: {str(e)}', 'danger')
    return redirect(url_for('coa.index'))


@coa_bp.route('/update/<int:id_coa>', methods=['POST'])
@menu_required('coa_pendapatan')
def update(id_coa):
    kode_account = request.form.get('kode_account')
    klasifikasi = request.form.get('klasifikasi')
    sub_klasifikasi = request.form.get('sub_klasifikasi')
    deskripsi_coa = request.form.get('deskripsi_coa')

    try:
        CoaModel.update(
            id_coa=id_coa,
            kode_account=kode_account,
            klasifikasi=klasifikasi,
            sub_klasifikasi=sub_klasifikasi,
            deskripsi_coa=deskripsi_coa,
            updated_by=_get_current_actor()
        )
        flash('Data COA Pendapatan berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui COA: {str(e)}', 'danger')
    return redirect(url_for('coa.index'))


@coa_bp.route('/delete/<int:id_coa>', methods=['POST'])
@menu_required('coa_pendapatan')
def delete(id_coa):
    try:
        CoaModel.delete(id_coa, deleted_by=_get_current_actor())
        flash('Data COA Pendapatan berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus COA: {str(e)}', 'danger')
    return redirect(url_for('coa.index'))


@coa_bp.route('/restore/<int:id_coa>', methods=['POST'])
@menu_required('coa_pendapatan')
def restore(id_coa):
    if not _is_superadmin():
        flash('Hanya Superadmin yang dapat mengaktifkan kembali data COA terhapus.', 'danger')
        return redirect(url_for('coa.index'))

    try:
        CoaModel.restore(id_coa, restored_by=_get_current_actor())
        flash('Data COA Pendapatan berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali COA: {str(e)}', 'danger')
    return redirect(url_for('coa.index'))