import os
import time
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from app.models.airline_model import AirlineModel
from app.utils.decorators import menu_required

airline_bp = Blueprint('airline', __name__, url_prefix='/aeronautika/setting/airlines')

ALLOWED_ROLES = {'superadmin', 'pengawas', 'admin'}
WRITE_ROLES = {'superadmin', 'pengawas'}


def _get_role(user):
    return (user.get('role') or '').strip().lower()


def _get_current_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def save_airline_logo(file_storage, old_file_path=None):
    """Simpan logo maskapai ke app/static/static/uploads/airlines/."""
    if not file_storage or not file_storage.filename:
        return None

    filename = secure_filename(file_storage.filename)
    unique_name = f"airline_{int(time.time())}_{filename}"
    upload_dir = os.path.join(current_app.static_folder, 'static', 'uploads', 'airlines')
    os.makedirs(upload_dir, exist_ok=True)

    if old_file_path:
        old_full_path = os.path.join(current_app.static_folder, old_file_path)
        if os.path.exists(old_full_path):
            try:
                os.remove(old_full_path)
            except OSError:
                pass

    file_storage.save(os.path.join(upload_dir, unique_name))
    return f"static/uploads/airlines/{unique_name}"


@airline_bp.route('/')
@menu_required('airlines')
def index():
    user = session.get('user', {})
    role = _get_role(user)

    if role not in ALLOWED_ROLES:
        flash('Anda tidak memiliki hak akses ke menu Airlines.', 'danger')
        return redirect(url_for('dashboard.index'))

    is_superadmin = (role == 'superadmin')
    can_write = (role in WRITE_ROLES)

    airline_list = AirlineModel.get_all(include_deleted=is_superadmin)

    return render_template(
        'aeronautika/airlines.html',
        airline_list=airline_list,
        is_superadmin=is_superadmin,
        can_write=can_write
    )


@airline_bp.route('/create', methods=['POST'])
@menu_required('airlines')
def create():
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda hanya memiliki akses lihat (View Only) pada menu Airlines.', 'danger')
        return redirect(url_for('airline.index'))

    airline_name = (request.form.get('airline_name') or '').strip()
    code_2 = (request.form.get('code_2') or '').strip().upper()
    code_3 = (request.form.get('code_3') or '').strip().upper()

    if not airline_name or not code_2 or not code_3:
        flash('Nama Airline, 2-Letter Code (IATA), dan 3-Letter Code (ICAO) wajib diisi.', 'warning')
        return redirect(url_for('airline.index'))

    if len(code_2) > 5 or len(code_3) > 5:
        flash('Format kode maskapai tidak valid.', 'warning')
        return redirect(url_for('airline.index'))

    logo_path = save_airline_logo(request.files.get('logo'))

    try:
        AirlineModel.create(
            {
                "airline_name": airline_name,
                "code_2": code_2,
                "code_3": code_3,
                "logo": logo_path,
            },
            created_by=_get_current_actor(user),
        )
        flash('Data Airline berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan data Airline: {str(e)}', 'danger')
    return redirect(url_for('airline.index'))


@airline_bp.route('/update/<int:id_airline>', methods=['POST'])
@menu_required('airlines')
def update(id_airline):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda hanya memiliki akses lihat (View Only) pada menu Airlines.', 'danger')
        return redirect(url_for('airline.index'))

    existing = AirlineModel.get_by_id(id_airline)
    if not existing:
        flash('Data Airline tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('airline.index'))

    airline_name = (request.form.get('airline_name') or '').strip()
    code_2 = (request.form.get('code_2') or '').strip().upper()
    code_3 = (request.form.get('code_3') or '').strip().upper()

    if not airline_name:
        flash('Nama Airline wajib diisi.', 'warning')
        return redirect(url_for('airline.index'))

    if (code_2 and len(code_2) > 5) or (code_3 and len(code_3) > 5):
        flash('Format kode maskapai tidak valid (maksimal 5 karakter).', 'warning')
        return redirect(url_for('airline.index'))

    logo_path = save_airline_logo(
        request.files.get('logo'),
        old_file_path=existing.get('logo')
    )

    try:
        AirlineModel.update(
            id_airline,
            {
                "airline_name": airline_name,
                "code_2": code_2,
                "code_3": code_3,
                "logo": logo_path,
            },
            updated_by=_get_current_actor(user),
        )
        flash('Data Airline berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data Airline: {str(e)}', 'danger')
    return redirect(url_for('airline.index'))


@airline_bp.route('/delete/<int:id_airline>', methods=['POST'])
@menu_required('airlines')
def delete(id_airline):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in WRITE_ROLES:
        flash('Anda tidak memiliki hak akses untuk menghapus data Airline.', 'danger')
        return redirect(url_for('airline.index'))

    existing = AirlineModel.get_by_id(id_airline)
    if not existing:
        flash('Data Airline tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('airline.index'))

    try:
        AirlineModel.delete(id_airline, deleted_by=_get_current_actor(user))
        flash('Data Airline berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus data Airline: {str(e)}', 'danger')
    return redirect(url_for('airline.index'))


@airline_bp.route('/restore/<int:id_airline>', methods=['POST'])
@menu_required('airlines')
def restore(id_airline):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali data Airline terhapus.', 'danger')
        return redirect(url_for('airline.index'))

    try:
        AirlineModel.restore(id_airline, restored_by=_get_current_actor(user))
        flash('Data Airline berhasil diaktifkan kembali!', 'success')
    except Exception as e:
        flash(f'Gagal mengaktifkan kembali data Airline: {str(e)}', 'danger')
    return redirect(url_for('airline.index'))