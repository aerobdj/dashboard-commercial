from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import app
from app.utils.decorators import airport_required
from app.models.flight_number_model import FlightNumberModel
from app.models.airport_model import AirportModel

flight_number_bp = Blueprint('flight_number', __name__, url_prefix='/aeronautika/setting/number-flight')


def flight_number_access_required(f):
    @wraps(f)
    @airport_required
    def decorated(*args, **kwargs):
        user = session.get('user') or {}
        role = (user.get('role') or '').strip().lower()
        allowed_menus = list(user.get('allowed_menus') or [])

        if role not in ('superadmin', 'pengawas', 'admin'):
            flash('Akses ditolak! Menu Number Flight hanya dapat diakses oleh Superadmin, Pengawas, dan Admin.', 'danger')
            return redirect(url_for('dashboard.index'))

        if role != 'superadmin' and 'flight_numbers' not in allowed_menus:
            try:
                role_res = app.supabase.table('roles').select('allowed_menus').ilike('role_name', role).limit(1).execute()
                if role_res.data and role_res.data[0].get('allowed_menus'):
                    fresh_menus = role_res.data[0]['allowed_menus']
                    user['allowed_menus'] = fresh_menus
                    session['user'] = user
                    allowed_menus = fresh_menus
            except Exception:
                pass

            if 'flight_numbers' not in allowed_menus:
                flash('Anda belum diberikan izin akses menu Number Flight.', 'danger')
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


def _get_cabang_options(allowed_cabang):
    query = app.supabase.table('cabang').select('kode_cabang, nama_cabang').is_('deleted_at', 'null')
    if allowed_cabang is not None:
        if not allowed_cabang:
            return []
        query = query.in_('kode_cabang', allowed_cabang)
    res = query.order('kode_cabang', desc=False).execute()
    return res.data or []


def _is_cabang_allowed(kode_cabang, allowed_cabang):
    if allowed_cabang is None:
        return True
    return kode_cabang.strip().upper() in [c.upper() for c in allowed_cabang]


def _resolve_origin_airport_id(kode_cabang, form_origin_id, is_single_cabang):
    """Jika user cabang tunggal, paksa origin mengikuti kode_cabang di master airport."""
    airports = AirportModel.get_all(include_deleted=False)
    cabang_airport = next((a for a in airports if (a.get('iata') or '').upper() == kode_cabang.upper()), None)
    if is_single_cabang and cabang_airport:
        return cabang_airport['id_airport']
    if form_origin_id:
        return int(form_origin_id)
    return cabang_airport['id_airport'] if cabang_airport else None


def _get_airline_code(id_airline):
    al_res = app.supabase.table('airline_data').select('code_2, code_3').eq('id_airline', int(id_airline)).limit(1).execute()
    al_row = al_res.data[0] if al_res.data else {}
    return al_row.get('code_2') or al_row.get('code_3') or ''


@flight_number_bp.route('/')
@flight_number_access_required
def index():
    user = session.get('user') or {}
    role = (user.get('role') or '').strip().lower()
    allowed_cabang = user.get('allowed_cabang')  # None = HO, List = REG / Cabang
    can_restore = role in ('superadmin', 'pengawas')
    is_single_cabang = (allowed_cabang is not None and len(allowed_cabang) == 1)

    all_records = FlightNumberModel.get_all(
        include_deleted=can_restore,
        allowed_cabang_codes=allowed_cabang
    )
    active_flights = [r for r in all_records if r.get('deleted_at') is None]
    deleted_flights = [r for r in all_records if r.get('deleted_at') is not None] if can_restore else []

    airlines_res = app.supabase.table('airline_data').select('*').order('airline_name', desc=False).execute()
    airlines = airlines_res.data or []
    airports = AirportModel.get_all(include_deleted=False)
    cabang_list = _get_cabang_options(allowed_cabang)

    # Cari default origin airport sesuai kode_cabang user
    user_cabang = (cabang_list[0]['kode_cabang'] if is_single_cabang and cabang_list else (user.get('kode_cabang') or '')).upper()
    default_origin_airport = next((a for a in airports if (a.get('iata') or '').upper() == user_cabang), None)

    return render_template(
        'aeronautika/flight_number.html',
        flights=active_flights,
        deleted_flights=deleted_flights,
        airlines=airlines,
        airports=airports,
        cabang_list=cabang_list,
        can_restore=can_restore,
        is_single_cabang=is_single_cabang,
        default_origin_airport=default_origin_airport
    )


@flight_number_bp.route('/create', methods=['POST'])
@flight_number_access_required
def create():
    user = session.get('user') or {}
    allowed_cabang = user.get('allowed_cabang')
    is_single_cabang = (allowed_cabang is not None and len(allowed_cabang) == 1)

    kode_cabang = (
        allowed_cabang[0] if is_single_cabang
        else (request.form.get('kode_cabang') or user.get('kode_cabang') or '')
    ).strip().upper()

    id_airline = request.form.get('id_airline')
    raw_flight_number = request.form.get('flight_number')
    origin_id = _resolve_origin_airport_id(kode_cabang, request.form.get('origin_airport_id'), is_single_cabang)
    dest_id = request.form.get('destination_airport_id')

    if not all([kode_cabang, id_airline, raw_flight_number, origin_id, dest_id]):
        flash('Pastikan Cabang, Maskapai, Flight Number, Origin (terdaftar di Master Route), dan Destination sudah terisi.', 'warning')
        return redirect(url_for('flight_number.index'))

    airline_code = _get_airline_code(id_airline)
    flight_number = FlightNumberModel.format_flight_number(raw_flight_number, airline_code=airline_code)

    if not _is_cabang_allowed(kode_cabang, allowed_cabang):
        flash(f'Anda tidak memiliki wewenang untuk cabang {kode_cabang}.', 'danger')
        return redirect(url_for('flight_number.index'))

    if int(origin_id) == int(dest_id):
        flash('Bandara Origin dan Destination tidak boleh sama.', 'warning')
        return redirect(url_for('flight_number.index'))

    if FlightNumberModel.exists(flight_number, kode_cabang):
        flash(f'Flight Number {flight_number} pada cabang {kode_cabang} sudah terdaftar.', 'danger')
        return redirect(url_for('flight_number.index'))

    try:
        FlightNumberModel.create({
            'id_airline': id_airline,
            'flight_number': flight_number,
            'origin_airport_id': origin_id,
            'destination_airport_id': dest_id,
            'kode_cabang': kode_cabang,
            'status': True,
        }, created_by=_get_actor())
        flash(f'Flight Number {flight_number} berhasil ditambahkan.', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan Flight Number: {str(e)}', 'danger')

    return redirect(url_for('flight_number.index'))


@flight_number_bp.route('/edit/<int:id_flightnumber>', methods=['POST'])
@flight_number_access_required
def edit(id_flightnumber):
    user = session.get('user') or {}
    allowed_cabang = user.get('allowed_cabang')
    is_single_cabang = (allowed_cabang is not None and len(allowed_cabang) == 1)

    existing = FlightNumberModel.get_by_id(id_flightnumber)
    if not existing or not _is_cabang_allowed(existing.get('kode_cabang', ''), allowed_cabang):
        flash('Data tidak ditemukan atau di luar wewenang cabang Anda.', 'danger')
        return redirect(url_for('flight_number.index'))

    kode_cabang = (
        allowed_cabang[0] if is_single_cabang
        else (request.form.get('kode_cabang') or existing.get('kode_cabang') or '')
    ).strip().upper()

    id_airline = request.form.get('id_airline')
    raw_flight_number = request.form.get('flight_number')
    origin_id = _resolve_origin_airport_id(kode_cabang, request.form.get('origin_airport_id'), is_single_cabang)
    dest_id = request.form.get('destination_airport_id')

    if not all([kode_cabang, id_airline, raw_flight_number, origin_id, dest_id]):
        flash('Semua field wajib diisi dengan benar.', 'warning')
        return redirect(url_for('flight_number.index'))

    airline_code = _get_airline_code(id_airline)
    flight_number = FlightNumberModel.format_flight_number(raw_flight_number, airline_code=airline_code)

    if not _is_cabang_allowed(kode_cabang, allowed_cabang):
        flash(f'Anda tidak memiliki wewenang untuk cabang {kode_cabang}.', 'danger')
        return redirect(url_for('flight_number.index'))

    if int(origin_id) == int(dest_id):
        flash('Bandara Origin dan Destination tidak boleh sama.', 'warning')
        return redirect(url_for('flight_number.index'))

    if FlightNumberModel.exists(flight_number, kode_cabang, exclude_id=id_flightnumber):
        flash(f'Flight Number {flight_number} pada cabang {kode_cabang} sudah digunakan.', 'danger')
        return redirect(url_for('flight_number.index'))

    try:
        FlightNumberModel.update(id_flightnumber, {
            'id_airline': id_airline,
            'flight_number': flight_number,
            'origin_airport_id': origin_id,
            'destination_airport_id': dest_id,
            'kode_cabang': kode_cabang,
            'status': True,
        }, updated_by=_get_actor())
        flash(f'Flight Number {flight_number} berhasil diperbarui.', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui Flight Number: {str(e)}', 'danger')

    return redirect(url_for('flight_number.index'))


@flight_number_bp.route('/delete/<int:id_flightnumber>', methods=['POST'])
@flight_number_access_required
def delete(id_flightnumber):
    user = session.get('user') or {}
    allowed_cabang = user.get('allowed_cabang')

    existing = FlightNumberModel.get_by_id(id_flightnumber)
    if not existing or not _is_cabang_allowed(existing.get('kode_cabang', ''), allowed_cabang):
        flash('Data tidak ditemukan atau di luar wewenang cabang Anda.', 'danger')
        return redirect(url_for('flight_number.index'))

    try:
        FlightNumberModel.delete(id_flightnumber, deleted_by=_get_actor())
        flash(f"Flight Number {existing.get('flight_number')} berhasil dihapus.", 'success')
    except Exception as e:
        flash(f'Gagal menghapus Flight Number: {str(e)}', 'danger')

    return redirect(url_for('flight_number.index'))


@flight_number_bp.route('/restore/<int:id_flightnumber>', methods=['POST'])
@flight_number_access_required
def restore(id_flightnumber):
    user = session.get('user') or {}
    role = (user.get('role') or '').strip().lower()
    allowed_cabang = user.get('allowed_cabang')

    if role not in ('superadmin', 'pengawas'):
        flash('Hanya Superadmin dan Pengawas yang dapat mengembalikan data terhapus.', 'danger')
        return redirect(url_for('flight_number.index'))

    target = FlightNumberModel.get_by_id(id_flightnumber, include_deleted=True)
    if not target or not _is_cabang_allowed(target.get('kode_cabang', ''), allowed_cabang):
        flash('Data tidak ditemukan atau di luar wewenang cabang Anda.', 'danger')
        return redirect(url_for('flight_number.index'))

    if FlightNumberModel.exists(target['flight_number'], target['kode_cabang'], exclude_id=id_flightnumber):
        flash(f"Gagal restore: Flight Number aktif {target['flight_number']} di cabang {target['kode_cabang']} sudah ada.", 'warning')
        return redirect(url_for('flight_number.index'))

    try:
        FlightNumberModel.restore(id_flightnumber, restored_by=_get_actor())
        flash(f"Flight Number {target['flight_number']} berhasil dikembalikan!", 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan Flight Number: {str(e)}', 'danger')

    return redirect(url_for('flight_number.index'))


@flight_number_bp.route('/lookup')
@airport_required
def lookup():
    fn = request.args.get('flight_number', '')
    cabang = request.args.get('kode_cabang') or (session.get('user') or {}).get('kode_cabang')
    record = FlightNumberModel.lookup_by_flight_number(fn, kode_cabang=cabang)
    if not record:
        return jsonify({'found': False})
    return jsonify({
        'found': True,
        'flight_number': record['flight_number'],
        'id_airline': record['id_airline'],
        'airline_name': record.get('airline', {}).get('airline_name'),
        'origin_iata': record.get('origin', {}).get('iata'),
        'destination_iata': record.get('destination', {}).get('iata'),
        'scope': record.get('scope')
    })