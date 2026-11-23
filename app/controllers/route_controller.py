from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.utils.decorators import airport_required
from app.models.airport_model import AirportModel

route_bp = Blueprint('route_setting', __name__, url_prefix='/aeronautika/setting/route')


def route_access_required(f):
    @wraps(f)
    @airport_required
    def decorated(*args, **kwargs):
        user = session.get('user') or {}
        role = (user.get('role') or '').strip().lower()
        allowed_menus = user.get('allowed_menus') or []

        if role not in ('superadmin', 'pengawas'):
            flash('Akses ditolak! Menu Route hanya dapat diakses oleh Superadmin dan Pengawas.', 'danger')
            return redirect(url_for('dashboard.index'))

        if role == 'pengawas' and 'routes' not in allowed_menus:
            flash('Role Pengawas belum diberikan izin akses menu Route.', 'danger')
            return redirect(url_for('dashboard.index'))

        return f(*args, **kwargs)
    return decorated


def _get_actor():
    u = session.get('user') or {}
    nama = u.get('nama_lengkap')
    email = u.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


@route_bp.route('/')
@route_access_required
def index():
    user = session.get('user') or {}
    role = (user.get('role') or '').strip().lower()
    is_superadmin = (role == 'superadmin')

    all_records = AirportModel.get_all(include_deleted=is_superadmin)
    airports = [a for a in all_records if a.get('deleted_at') is None]
    deleted_airports = [a for a in all_records if a.get('deleted_at') is not None] if is_superadmin else []

    user_cabang = (user.get('kode_cabang') or '').strip().upper()
    iata_list = [a['iata'] for a in airports]
    if user_cabang in iata_list:
        default_origin = user_cabang
    elif 'BDJ' in iata_list:
        default_origin = 'BDJ'
    else:
        default_origin = iata_list[0] if iata_list else ''

    return render_template(
        'aeronautika/route.html',
        airports=airports,
        deleted_airports=deleted_airports,
        is_superadmin=is_superadmin,
        default_origin=default_origin,
        user=user
    )


@route_bp.route('/create', methods=['POST'])
@route_access_required
def create():
    iata = (request.form.get('iata') or '').strip().upper()
    if len(iata) != 3 or not iata.isalpha():
        flash('Kode IATA wajib terdiri dari 3 huruf (contoh: BDJ, CGK, KUL).', 'warning')
        return redirect(url_for('route_setting.index'))

    if AirportModel.iata_exists(iata):
        flash(f'Bandara dengan kode IATA {iata} sudah terdaftar.', 'danger')
        return redirect(url_for('route_setting.index'))

    try:
        AirportModel.create(request.form, created_by=_get_actor())
        flash(f'Bandara {iata} berhasil ditambahkan.', 'success')
    except ValueError:
        flash('Format Latitude / Longitude tidak valid. Gunakan angka desimal (contoh: -3.442361).', 'danger')
    except Exception as e:
        flash(f'Gagal menambahkan data bandara: {str(e)}', 'danger')

    return redirect(url_for('route_setting.index'))


@route_bp.route('/edit/<int:id_airport>', methods=['POST'])
@route_access_required
def edit(id_airport):
    iata = (request.form.get('iata') or '').strip().upper()
    if len(iata) != 3 or not iata.isalpha():
        flash('Kode IATA wajib terdiri dari 3 huruf.', 'warning')
        return redirect(url_for('route_setting.index'))

    if AirportModel.iata_exists(iata, exclude_id=id_airport):
        flash(f'Kode IATA {iata} sudah digunakan bandara lain.', 'danger')
        return redirect(url_for('route_setting.index'))

    try:
        AirportModel.update(id_airport, request.form, updated_by=_get_actor())
        flash(f'Data bandara {iata} berhasil diperbarui.', 'success')
    except ValueError:
        flash('Format Latitude / Longitude tidak valid.', 'danger')
    except Exception as e:
        flash(f'Gagal memperbarui data bandara: {str(e)}', 'danger')

    return redirect(url_for('route_setting.index'))


@route_bp.route('/delete/<int:id_airport>', methods=['POST'])
@route_access_required
def delete(id_airport):
    try:
        AirportModel.delete(id_airport, deleted_by=_get_actor())
        flash('Data bandara berhasil dihapus.', 'success')
    except Exception as e:
        flash(f'Gagal menghapus data bandara: {str(e)}', 'danger')

    return redirect(url_for('route_setting.index'))

@route_bp.route('/restore/<int:id_airport>', methods=['POST'])
@route_access_required
def restore(id_airport):
    user = session.get('user') or {}
    if (user.get('role') or '').strip().lower() != 'superadmin':
        flash('Hanya Superadmin yang dapat mengembalikan data bandara terhapus.', 'danger')
        return redirect(url_for('route_setting.index'))

    target = AirportModel.get_by_id(id_airport, include_deleted=True)
    if not target:
        flash('Data bandara tidak ditemukan.', 'danger')
        return redirect(url_for('route_setting.index'))

    # Cegah duplikasi jika kode IATA yang sama sudah dibuat ulang saat data ini masih terhapus
    if AirportModel.iata_exists(target['iata'], exclude_id=id_airport):
        flash(f"Gagal restore: Bandara aktif dengan kode IATA {target['iata']} sudah ada.", 'warning')
        return redirect(url_for('route_setting.index'))

    try:
        AirportModel.restore(id_airport, restored_by=_get_actor())
        flash(f"Bandara {target['iata']} ({target['airport_name']}) berhasil dikembalikan!", 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan data bandara: {str(e)}', 'danger')

    return redirect(url_for('route_setting.index'))