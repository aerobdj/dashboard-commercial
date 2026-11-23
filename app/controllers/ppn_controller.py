from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from app.models.ppn_model import PpnModel
from app.utils.decorators import menu_required

ppn_bp = Blueprint('ppn', __name__, url_prefix='/setting/ppn')


def _get_role(user):
    return (user.get('role') or '').strip().lower()


def _get_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


@ppn_bp.route('/')
@menu_required('master_ppn')
def index():
    user = session.get('user', {})
    role = _get_role(user)
    if role not in {'superadmin', 'pengawas'}:
        flash('Anda tidak memiliki hak akses ke menu Master PPN.', 'danger')
        return redirect(url_for('dashboard.index'))

    is_superadmin = (role == 'superadmin')
    ppn_list = PpnModel.get_all(include_deleted=is_superadmin)

    return render_template(
        'settings/ppn.html',
        ppn_list=ppn_list,
        is_superadmin=is_superadmin
    )


@ppn_bp.route('/create', methods=['POST'])
@menu_required('master_ppn')
def create():
    user = session.get('user', {})
    if _get_role(user) not in {'superadmin', 'pengawas'}:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppn.index'))

    nama_ppn = (request.form.get('nama_ppn') or '').strip()
    persentase_raw = request.form.get('persentase')
    berlaku_mulai = (request.form.get('berlaku_mulai') or '').strip()
    keterangan = (request.form.get('keterangan') or '').strip()

    if not nama_ppn or persentase_raw in (None, '') or not berlaku_mulai:
        flash('Nama PPN, Persentase, dan Tanggal Berlaku wajib diisi.', 'warning')
        return redirect(url_for('ppn.index'))

    try:
        persentase = float(persentase_raw)
        if persentase < 0 or persentase > 100:
            raise ValueError()
    except ValueError:
        flash('Persentase PPN harus antara 0 hingga 100.', 'warning')
        return redirect(url_for('ppn.index'))

    try:
        PpnModel.create({
            'nama_ppn': nama_ppn,
            'persentase': persentase,
            'berlaku_mulai': berlaku_mulai,
            'keterangan': keterangan,
        }, created_by=_get_actor(user))
        flash(f'Data {nama_ppn} ({persentase}%) berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan data PPN: {str(e)}', 'danger')

    return redirect(url_for('ppn.index'))


@ppn_bp.route('/update/<int:id_ppn>', methods=['POST'])
@menu_required('master_ppn')
def update(id_ppn):
    user = session.get('user', {})
    if _get_role(user) not in {'superadmin', 'pengawas'}:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppn.index'))

    existing = PpnModel.get_by_id(id_ppn)
    if not existing:
        flash('Data PPN tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('ppn.index'))

    nama_ppn = (request.form.get('nama_ppn') or '').strip()
    persentase_raw = request.form.get('persentase')
    berlaku_mulai = (request.form.get('berlaku_mulai') or '').strip()
    keterangan = (request.form.get('keterangan') or '').strip()

    if not nama_ppn or persentase_raw in (None, '') or not berlaku_mulai:
        flash('Nama PPN, Persentase, dan Tanggal Berlaku wajib diisi.', 'warning')
        return redirect(url_for('ppn.index'))

    try:
        persentase = float(persentase_raw)
        if persentase < 0 or persentase > 100:
            raise ValueError()
    except ValueError:
        flash('Persentase PPN harus antara 0 hingga 100.', 'warning')
        return redirect(url_for('ppn.index'))

    try:
        PpnModel.update(id_ppn, {
            'nama_ppn': nama_ppn,
            'persentase': persentase,
            'berlaku_mulai': berlaku_mulai,
            'keterangan': keterangan,
        }, updated_by=_get_actor(user))
        flash('Data PPN berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data PPN: {str(e)}', 'danger')

    return redirect(url_for('ppn.index'))


@ppn_bp.route('/delete/<int:id_ppn>', methods=['POST'])
@menu_required('master_ppn')
def delete(id_ppn):
    user = session.get('user', {})
    if _get_role(user) not in {'superadmin', 'pengawas'}:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('ppn.index'))

    try:
        PpnModel.delete(id_ppn, deleted_by=_get_actor(user))
        flash('Data PPN berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus data PPN: {str(e)}', 'danger')

    return redirect(url_for('ppn.index'))


@ppn_bp.route('/restore/<int:id_ppn>', methods=['POST'])
@menu_required('master_ppn')
def restore(id_ppn):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali data PPN terhapus.', 'danger')
        return redirect(url_for('ppn.index'))

    try:
        PpnModel.restore(id_ppn, restored_by=_get_actor(user))
        flash('Data PPN berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan data PPN: {str(e)}', 'danger')

    return redirect(url_for('ppn.index'))