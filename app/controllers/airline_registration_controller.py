from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import app
from app.utils.decorators import airport_required
from app.models.airline_registration_model import AirlineRegistrationModel

airline_registration_bp = Blueprint(
    'airline_registration',
    __name__,
    url_prefix='/aeronautika/setting/registration'
)


def registration_access_required(f):
    @wraps(f)
    @airport_required
    def decorated(*args, **kwargs):
        user = session.get('user') or {}
        role = (user.get('role') or '').strip().lower()
        allowed_menus = list(user.get('allowed_menus') or [])

        if role not in ('superadmin', 'pengawas', 'admin'):
            flash('Akses ditolak! Menu Registration hanya dapat diakses oleh Superadmin, Pengawas, dan Admin.', 'danger')
            return redirect(url_for('dashboard.index'))

        if role != 'superadmin' and 'airline_registrations' not in allowed_menus:
            try:
                role_res = app.supabase.table('roles').select('allowed_menus').ilike('role_name', role).limit(1).execute()
                if role_res.data and role_res.data[0].get('allowed_menus'):
                    fresh_menus = role_res.data[0]['allowed_menus']
                    user['allowed_menus'] = fresh_menus
                    session['user'] = user
                    allowed_menus = fresh_menus
            except Exception:
                pass

            if 'airline_registrations' not in allowed_menus:
                flash('Anda belum diberikan izin akses menu Registration.', 'danger')
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


@airline_registration_bp.route('/')
@registration_access_required
def index():
    user = session.get('user') or {}
    role = (user.get('role') or '').strip().lower()
    is_superadmin = (role == 'superadmin')

    # Tanpa filter hirarki cabang (HO, REG, Cabang akses semua)
    all_records = AirlineRegistrationModel.get_all(include_deleted=is_superadmin)
    active_registrations = [r for r in all_records if r.get('deleted_at') is None]
    deleted_registrations = [r for r in all_records if r.get('deleted_at') is not None] if is_superadmin else []

    airlines_res = app.supabase.table('airline_data').select('*').order('airline_name', desc=False).execute()
    airlines = airlines_res.data or []

    return render_template(
        'aeronautika/registration.html',
        registrations=active_registrations,
        deleted_registrations=deleted_registrations,
        airlines=airlines,
        is_superadmin=is_superadmin,
    )


@airline_registration_bp.route('/create', methods=['POST'])
@registration_access_required
def create():
    registration = AirlineRegistrationModel.format_registration(request.form.get('registration'))
    id_airline = request.form.get('id_airline')
    type_flight = (request.form.get('type_flight') or '').strip().upper()
    seat_raw = request.form.get('seat')
    scope = request.form.get('scope')

    if not all([registration, id_airline, type_flight, seat_raw]):
        flash('Pastikan Nomor Registrasi, Airline, Type Flight, dan Seat sudah terisi.', 'warning')
        return redirect(url_for('airline_registration.index'))

    try:
        seat = int(seat_raw)
        if seat <= 0:
            raise ValueError()
    except ValueError:
        flash('Jumlah Seat harus berupa angka lebih dari 0.', 'warning')
        return redirect(url_for('airline_registration.index'))

    if AirlineRegistrationModel.exists(registration):
        flash(f'Registrasi pesawat {registration} sudah terdaftar.', 'danger')
        return redirect(url_for('airline_registration.index'))

    try:
        AirlineRegistrationModel.create({
            'registration': registration,
            'id_airline': id_airline,
            'type_flight': type_flight,
            'seat': seat,
            'scope': scope,
        }, created_by=_get_actor())
        flash(f'Registrasi pesawat {registration} berhasil ditambahkan.', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan registrasi pesawat: {str(e)}', 'danger')

    return redirect(url_for('airline_registration.index'))


@airline_registration_bp.route('/edit/<int:id_registration>', methods=['POST'])
@registration_access_required
def edit(id_registration):
    existing = AirlineRegistrationModel.get_by_id(id_registration)
    if not existing:
        flash('Data registrasi pesawat tidak ditemukan.', 'danger')
        return redirect(url_for('airline_registration.index'))

    registration = AirlineRegistrationModel.format_registration(request.form.get('registration'))
    id_airline = request.form.get('id_airline')
    type_flight = (request.form.get('type_flight') or '').strip().upper()
    seat_raw = request.form.get('seat')
    scope = request.form.get('scope')

    if not all([registration, id_airline, type_flight, seat_raw]):
        flash('Semua field wajib diisi dengan benar.', 'warning')
        return redirect(url_for('airline_registration.index'))

    try:
        seat = int(seat_raw)
        if seat <= 0:
            raise ValueError()
    except ValueError:
        flash('Jumlah Seat harus berupa angka lebih dari 0.', 'warning')
        return redirect(url_for('airline_registration.index'))

    if AirlineRegistrationModel.exists(registration, exclude_id=id_registration):
        flash(f'Registrasi pesawat {registration} sudah digunakan oleh data lain.', 'danger')
        return redirect(url_for('airline_registration.index'))

    try:
        AirlineRegistrationModel.update(id_registration, {
            'registration': registration,
            'id_airline': id_airline,
            'type_flight': type_flight,
            'seat': seat,
            'scope': scope,
        }, updated_by=_get_actor())
        flash(f'Registrasi pesawat {registration} berhasil diperbarui.', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui registrasi pesawat: {str(e)}', 'danger')

    return redirect(url_for('airline_registration.index'))


@airline_registration_bp.route('/delete/<int:id_registration>', methods=['POST'])
@registration_access_required
def delete(id_registration):
    existing = AirlineRegistrationModel.get_by_id(id_registration)
    if not existing:
        flash('Data registrasi pesawat tidak ditemukan.', 'danger')
        return redirect(url_for('airline_registration.index'))

    try:
        AirlineRegistrationModel.delete(id_registration, deleted_by=_get_actor())
        flash(f"Registrasi pesawat {existing.get('registration')} berhasil dihapus.", 'success')
    except Exception as e:
        flash(f'Gagal menghapus registrasi pesawat: {str(e)}', 'danger')

    return redirect(url_for('airline_registration.index'))


@airline_registration_bp.route('/restore/<int:id_registration>', methods=['POST'])
@registration_access_required
def restore(id_registration):
    user = session.get('user') or {}
    role = (user.get('role') or '').strip().lower()

    if role != 'superadmin':
        flash('Hanya Superadmin yang dapat mengembalikan data terhapus.', 'danger')
        return redirect(url_for('airline_registration.index'))

    target = AirlineRegistrationModel.get_by_id(id_registration, include_deleted=True)
    if not target:
        flash('Data registrasi pesawat tidak ditemukan.', 'danger')
        return redirect(url_for('airline_registration.index'))

    if AirlineRegistrationModel.exists(target['registration'], exclude_id=id_registration):
        flash(f"Gagal restore: Registrasi aktif {target['registration']} sudah ada.", 'warning')
        return redirect(url_for('airline_registration.index'))

    try:
        AirlineRegistrationModel.restore(id_registration, restored_by=_get_actor())
        flash(f"Registrasi pesawat {target['registration']} berhasil dikembalikan!", 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan registrasi pesawat: {str(e)}', 'danger')

    return redirect(url_for('airline_registration.index'))


@airline_registration_bp.route('/lookup')
@airport_required
def lookup():
    """Endpoint opsional untuk auto-fill Type Flight, Seat & Scope di modul transaksi."""
    reg = AirlineRegistrationModel.format_registration(request.args.get('registration', ''))
    if not reg:
        return jsonify({'found': False})
    res = (
        app.supabase.table(AirlineRegistrationModel.TABLE)
        .select('*')
        .ilike('registration', reg)
        .is_('deleted_at', 'null')
        .limit(1)
        .execute()
    )
    if not res.data:
        return jsonify({'found': False})
    rec = AirlineRegistrationModel._enrich_records(res.data)[0]
    return jsonify({
        'found': True,
        'registration': rec['registration'],
        'id_airline': rec['id_airline'],
        'airline_name': rec.get('airline', {}).get('airline_name'),
        'type_flight': rec.get('type_flight'),
        'seat': rec.get('seat'),
        'scope': rec.get('scope'),
    })