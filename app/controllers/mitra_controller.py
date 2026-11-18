import os
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from app.models.mitra_model import MitraModel
from app.models.cabang_model import CabangModel
from app.utils.decorators import menu_required

mitra_bp = Blueprint('mitra', __name__, url_prefix='/commercial/mitra-usaha')

ALLOWED_ROLES = {'superadmin', 'pengawas', 'admin', 'user'}
WRITE_ROLES = {'superadmin', 'pengawas'}
DELETE_ROLES = {'superadmin', 'pengawas'}

DEFAULT_TYPE_MITRA = [
    "F&B", "Retail", "Service", "Duty Free", "Airport Lounge",
    "Jasa Keuangan", "Telekomunikasi", "Advertising", "Angkutan Darat",
    "Pengelola Parkir", "Perhotelan", "Airlines", "Ground Handling",
    "Kargo & Logistik", "Penyedia Bahan Bakar", "Katering", "UMKM", "Pop Up"
]

POLA_KERJASAMA_OPTIONS = [
    "Sewa Ruang", "Sewa Lahan", "Revenue Share", "Sewa Tempat", "Pameran",
    "Utilitas", "Digital Platform", "Media Digital", "Media Cetak"
]


def _get_role(user):
    return (user.get('role') or '').strip().lower()


def _get_current_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def get_user_scope(user):
    """Menentukan daftar kode_cabang berdasarkan hierarki cabang (HO / Regional / Cabang)."""
    role = _get_role(user)
    tipe_unit = (user.get('tipe_unit') or '').strip().upper()
    kode_cabang = (user.get('kode_cabang') or '').strip().upper()

    if role == 'superadmin' or tipe_unit == 'HO' or not kode_cabang:
        return None

    return CabangModel.get_allowed_cabang_codes(kode_cabang)


def save_contract_file(file_storage, old_file_path=None):
    """Simpan file kontrak (PDF/DOC/Gambar) ke app/static/static/uploads/kontrak/."""
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    unique_name = f"kontrak_{int(time.time())}_{filename}"
    upload_dir = os.path.join(current_app.static_folder, 'static', 'uploads', 'kontrak')
    os.makedirs(upload_dir, exist_ok=True)

    if old_file_path:
        old_full_path = os.path.join(current_app.static_folder, old_file_path)
        if os.path.exists(old_full_path):
            try:
                os.remove(old_full_path)
            except OSError:
                pass

    file_storage.save(os.path.join(upload_dir, unique_name))
    return f"static/uploads/kontrak/{unique_name}"


def parse_nullable_number(val):
    if val is None or str(val).strip() == '':
        return None
    s = str(val).strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


@mitra_bp.route('/')
@menu_required('mitra_usaha')
def index():
    user = session.get('user', {})
    role = _get_role(user)

    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses ke menu Mitra Usaha.', 'danger')
        return redirect(url_for('dashboard.index'))

    is_superadmin = (role == 'superadmin')
    can_write = (role in WRITE_ROLES)
    can_delete = (role in DELETE_ROLES)

    allowed_cabang = get_user_scope(user)
    mitra_list = MitraModel.get_all(
        allowed_cabang=allowed_cabang,
        include_deleted=is_superadmin
    )
    all_cabang = CabangModel.get_all(include_deleted=is_superadmin)

    cabang_map = {c['kode_cabang']: c['nama_cabang'] for c in all_cabang}

    unit_bandara = [
        c for c in all_cabang
        if not c.get('deleted_at')
        and (c.get('tipe_unit') or '').strip().upper() not in ('HO', 'REGIONAL', 'REGION')
    ]
    if not unit_bandara:
        unit_bandara = [c for c in all_cabang if not c.get('deleted_at')]

    if allowed_cabang is None:
        selectable_cabang = unit_bandara
    else:
        selectable_cabang = [c for c in unit_bandara if c['kode_cabang'] in allowed_cabang]

    db_types = {m['type_mitra'] for m in mitra_list if m.get('type_mitra')}
    type_mitra_options = sorted(list(set(DEFAULT_TYPE_MITRA).union(db_types)))

    return render_template(
        'commercial/mitra_usaha.html',
        mitra_list=mitra_list,
        cabang_list=selectable_cabang,
        cabang_map=cabang_map,
        can_select_cabang=(allowed_cabang is None or len(selectable_cabang) > 1),
        type_mitra_options=type_mitra_options,
        pola_options=POLA_KERJASAMA_OPTIONS,
        is_superadmin=is_superadmin,
        can_write=can_write,
        can_delete=can_delete
    )


@mitra_bp.route('/create', methods=['POST'])
@menu_required('mitra_usaha')
def create():
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda hanya memiliki akses lihat (View Only) pada menu Mitra Usaha.', 'danger')
        return redirect(url_for('mitra.index'))

    allowed_cabang = get_user_scope(user)

    selected_type = request.form.get('type_mitra')
    custom_type = request.form.get('type_mitra_custom')
    final_type = custom_type.strip() if selected_type == '__NEW__' and custom_type else selected_type

    tipe_unit = (user.get('tipe_unit') or '').strip().upper()
    if tipe_unit == 'CABANG' and role != 'superadmin':
        kode_cabang = user.get('kode_cabang')
    else:
        kode_cabang = request.form.get('kode_cabang') or user.get('kode_cabang')
        if allowed_cabang is not None and kode_cabang not in allowed_cabang:
            flash('Anda tidak memiliki akses untuk menambahkan mitra di cabang tersebut.', 'danger')
            return redirect(url_for('mitra.index'))

    if not kode_cabang:
        flash('Unit Cabang Bandara wajib dipilih.', 'warning')
        return redirect(url_for('mitra.index'))

    uploaded_file = save_contract_file(request.files.get('file_kontrak'))

    form_data = {
        "kode_cabang": kode_cabang,
        "nama_pt": request.form.get('nama_pt', ''),
        "brand": request.form.get('brand', ''),
        "type_mitra": final_type or '',
        "kode_contract": request.form.get('kode_contract', ''),
        "no_ba": request.form.get('no_ba', ''),
        "tgl_ba": request.form.get('tgl_ba'),
        "kode_ruang": request.form.get('kode_ruang', ''),
        "luas": parse_nullable_number(request.form.get('luas')),
        "tarif_sewa": parse_nullable_number(request.form.get('tarif_sewa')),
        "pola_kerjasama": request.form.getlist('pola_kerjasama'),
        "type_kerjasama": request.form.get('type_kerjasama', 'MOB'),
        "nominal_kerjasama": parse_nullable_number(request.form.get('nominal_kerjasama')),
        "presentase_rs": parse_nullable_number(request.form.get('presentase_rs')),
        "jangkawaktu_awal": request.form.get('jangkawaktu_awal'),
        "jangkawaktu_akhir": request.form.get('jangkawaktu_akhir'),
        "file": uploaded_file
    }

    try:
        MitraModel.create(form_data, created_by=_get_current_actor(user))
        flash('Data Mitra Usaha berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan Mitra Usaha: {str(e)}', 'danger')
    return redirect(url_for('mitra.index'))


@mitra_bp.route('/update/<int:id_mitra>', methods=['POST'])
@menu_required('mitra_usaha')
def update(id_mitra):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda hanya memiliki akses lihat (View Only) pada menu Mitra Usaha.', 'danger')
        return redirect(url_for('mitra.index'))

    allowed_cabang = get_user_scope(user)
    existing = MitraModel.get_by_id(id_mitra)

    if not existing:
        flash('Data Mitra Usaha tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('mitra.index'))

    if allowed_cabang is not None and existing.get('kode_cabang') not in allowed_cabang:
        flash('Anda tidak memiliki akses untuk mengubah data cabang ini.', 'danger')
        return redirect(url_for('mitra.index'))

    selected_type = request.form.get('type_mitra')
    custom_type = request.form.get('type_mitra_custom')
    final_type = custom_type.strip() if selected_type == '__NEW__' and custom_type else selected_type

    tipe_unit = (user.get('tipe_unit') or '').strip().upper()
    if tipe_unit == 'CABANG' and role != 'superadmin':
        kode_cabang = user.get('kode_cabang')
    else:
        kode_cabang = request.form.get('kode_cabang') or existing.get('kode_cabang')
        if allowed_cabang is not None and kode_cabang not in allowed_cabang:
            flash('Cabang tujuan berada di luar wilayah hierarki Anda.', 'danger')
            return redirect(url_for('mitra.index'))

    uploaded_file = save_contract_file(
        request.files.get('file_kontrak'),
        old_file_path=existing.get('file')
    )

    form_data = {
        "kode_cabang": kode_cabang,
        "nama_pt": request.form.get('nama_pt', ''),
        "brand": request.form.get('brand', ''),
        "type_mitra": final_type or '',
        "kode_contract": request.form.get('kode_contract', ''),
        "no_ba": request.form.get('no_ba', ''),
        "tgl_ba": request.form.get('tgl_ba'),
        "kode_ruang": request.form.get('kode_ruang', ''),
        "luas": parse_nullable_number(request.form.get('luas')),
        "tarif_sewa": parse_nullable_number(request.form.get('tarif_sewa')),
        "pola_kerjasama": request.form.getlist('pola_kerjasama'),
        "type_kerjasama": request.form.get('type_kerjasama', 'MOB'),
        "nominal_kerjasama": parse_nullable_number(request.form.get('nominal_kerjasama')),
        "presentase_rs": parse_nullable_number(request.form.get('presentase_rs')),
        "jangkawaktu_awal": request.form.get('jangkawaktu_awal'),
        "jangkawaktu_akhir": request.form.get('jangkawaktu_akhir'),
        "file": uploaded_file
    }

    try:
        MitraModel.update(id_mitra, form_data, updated_by=_get_current_actor(user))
        flash('Data Mitra Usaha berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui Mitra Usaha: {str(e)}', 'danger')
    return redirect(url_for('mitra.index'))


@mitra_bp.route('/toggle-status/<int:id_mitra>', methods=['POST'])
@menu_required('mitra_usaha')
def toggle_status(id_mitra):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda hanya memiliki akses lihat (View Only) pada menu Mitra Usaha.', 'danger')
        return redirect(url_for('mitra.index'))

    allowed_cabang = get_user_scope(user)
    existing = MitraModel.get_by_id(id_mitra)

    if not existing:
        flash('Data Mitra Usaha tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('mitra.index'))

    if allowed_cabang is not None and existing.get('kode_cabang') not in allowed_cabang:
        flash('Anda tidak memiliki akses untuk mengubah status mitra cabang ini.', 'danger')
        return redirect(url_for('mitra.index'))

    try:
        new_status = MitraModel.toggle_status(id_mitra, updated_by=_get_current_actor(user))
        flash(f'Status Mitra Usaha berhasil diubah menjadi {new_status}!', 'success')
    except Exception as e:
        flash(f'Gagal mengubah status: {str(e)}', 'danger')
    return redirect(url_for('mitra.index'))


@mitra_bp.route('/delete/<int:id_mitra>', methods=['POST'])
@menu_required('mitra_usaha')
def delete(id_mitra):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in DELETE_ROLES:
        flash('Anda tidak memiliki hak akses untuk menghapus data Mitra Usaha.', 'danger')
        return redirect(url_for('mitra.index'))

    allowed_cabang = get_user_scope(user)
    existing = MitraModel.get_by_id(id_mitra)
    if not existing:
        flash('Data Mitra Usaha tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('mitra.index'))

    if allowed_cabang is not None and existing.get('kode_cabang') not in allowed_cabang:
        flash('Anda tidak memiliki akses untuk menghapus data cabang ini.', 'danger')
        return redirect(url_for('mitra.index'))

    deleted_reason = (request.form.get('deleted_reason') or '').strip()
    if not deleted_reason:
        flash('Alasan penghapusan data wajib diisi!', 'warning')
        return redirect(url_for('mitra.index'))

    try:
        MitraModel.delete(
            id_mitra,
            deleted_by=_get_current_actor(user),
            deleted_reason=deleted_reason
        )
        flash('Data Mitra Usaha berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus Mitra Usaha: {str(e)}', 'danger')
    return redirect(url_for('mitra.index'))


@mitra_bp.route('/restore/<int:id_mitra>', methods=['POST'])
@menu_required('mitra_usaha')
def restore(id_mitra):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali data Mitra Usaha terhapus.', 'danger')
        return redirect(url_for('mitra.index'))

    try:
        MitraModel.restore(id_mitra, restored_by=_get_current_actor(user))
        flash('Data Mitra Usaha berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali Mitra Usaha: {str(e)}', 'danger')
    return redirect(url_for('mitra.index'))