from datetime import datetime, timezone, timedelta, date
from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import app
from app.models.pjp2u_model import Pjp2uModel
from app.utils.decorators import airport_required, menu_required

pjp2u_bp = Blueprint('pjp2u', __name__, url_prefix='/aeronautika/operasional/pjp2u')


def _get_role(user):
    if not isinstance(user, dict):
        user = {}
    raw_role = user.get('role') or user.get('user_role') or session.get('role') or ''
    return str(raw_role).strip().lower()


def _get_actor(user):
    nama = user.get('nama_lengkap')
    email = user.get('email')
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or 'System'


def _get_local_today_iso():
    wita_now = datetime.now(timezone(timedelta(hours=8)))
    return wita_now.strftime('%Y-%m-%d')


def _get_accessible_cabangs(user):
    role = _get_role(user)
    query = (
        app.supabase.table('cabang')
        .select('kode_cabang, nama_cabang, tipe_unit, parent_kode, kota')
        .is_('deleted_at', 'null')
    )

    if role == 'superadmin':
        res = query.order('kode_cabang', desc=False).execute()
        return None, (res.data or [])

    if 'allowed_cabang' in user:
        allowed_cabang = user.get('allowed_cabang')
        if allowed_cabang is None:
            res = query.order('kode_cabang', desc=False).execute()
            return None, (res.data or [])
        if not allowed_cabang:
            return [], []
        clean_allowed = [c.strip().upper() for c in allowed_cabang if c and c.strip()]
        res = query.in_('kode_cabang', clean_allowed).order('kode_cabang', desc=False).execute()
        return clean_allowed, (res.data or [])

    user_cabang = (user.get('kode_cabang') or '').strip().upper()
    if not user_cabang:
        return [], []
    if user_cabang in ('HO', 'KANTOR PUSAT'):
        res = query.order('kode_cabang', desc=False).execute()
        return None, (res.data or [])

    all_cabs = (query.order('kode_cabang', desc=False).execute()).data or []
    reg_cabs = [c for c in all_cabs if (c.get('parent_kode') or '').strip().upper() == user_cabang]
    if reg_cabs:
        return [c['kode_cabang'] for c in reg_cabs], reg_cabs

    single = [c for c in all_cabs if (c.get('kode_cabang') or '').strip().upper() == user_cabang]
    return [user_cabang], single


def _compute_row_permissions(row, role, active_adjusted_parent_ids=None):
    return Pjp2uModel.compute_row_permissions(
        row=row,
        role=role,
        active_adjusted_parent_ids=active_adjusted_parent_ids,
        now_utc=datetime.now(timezone.utc),
    )


def _group_by_airline(rows):
    groups_map = {}
    for r in rows:
        op_id = r.get('operator') or 0
        if op_id not in groups_map:
            groups_map[op_id] = {
                'operator_id': op_id,
                'airline_name': r.get('airline_name') or 'Unknown Airline',
                'airline_code_2': r.get('airline_code_2') or '-',
                'airline_logo': r.get('airline_logo'),
                'rows': [],
                'sum_pax': 0,
                'sum_psc': 0,
                'sum_pend_psc': 0.0,
                'sum_pend_counter_idr': 0.0,
                'sum_pend_counter_usd': 0.0,
                'sum_pend_cucs': 0.0,
                'sum_pend_counter_cucs': 0.0,
            }
        g = groups_map[op_id]
        g['rows'].append(r)
        g['sum_pax'] += int(r.get('jumlah_pax') or 0)
        g['sum_psc'] += int(r.get('total_prod_psc') or 0)
        g['sum_pend_psc'] += float(r.get('pend_psc') or 0)
        cnt_val = float(r.get('pend_counter') or 0)
        cucs_val = float(r.get('pend_cucs') or 0)
        if (r.get('mata_uang_counter') or 'IDR').upper() == 'USD':
            g['sum_pend_counter_usd'] += cnt_val
        else:
            g['sum_pend_counter_idr'] += cnt_val
        g['sum_pend_cucs'] += cucs_val
        g['sum_pend_counter_cucs'] += (cnt_val if (r.get('mata_uang_counter') or 'IDR').upper() != 'USD' else 0.0) + cucs_val

    return sorted(groups_map.values(), key=lambda x: x['airline_name'])


def _build_payload_from_form(form, master_bundle, allowed_codes, is_adjustment=False, parent_row=None):
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)
    cabang = (
        allowed_codes[0] if is_single_cabang
        else (form.get('cabang') or (parent_row.get('cabang') if parent_row else '') or '').strip().upper()
    )
    if not cabang:
        raise ValueError("Cabang wajib dipilih.")
    if allowed_codes is not None and cabang not in allowed_codes:
        raise ValueError(f"Anda tidak memiliki akses untuk cabang {cabang}.")

    tanggal_str = (form.get('tanggal') or (parent_row.get('tanggal') if parent_row else '') or '').strip()
    if not tanggal_str:
        raise ValueError("Tanggal penerbangan wajib diisi.")
    tgl_obj = date.fromisoformat(tanggal_str[:10])

    boarding_time = (form.get('boarding_time') or '').strip() or None
    flight_number = (form.get('flight_number') or '').strip().upper()
    if not flight_number:
        raise ValueError("Nomor penerbangan (Flight Number) wajib diisi.")

    if is_adjustment and not flight_number.endswith('J'):
        flight_number = f"{flight_number}J"

    id_flightnumber = Pjp2uModel._to_int(form.get('id_flightnumber'), 0) or None
    id_registration = Pjp2uModel._to_int(form.get('id_registration'), 0) or None
    registration = (form.get('registration') or '').strip().upper() or None

    reg_obj = next(
        (r for r in master_bundle['registrations']
         if (id_registration and r['id_registration'] == id_registration)
         or (registration and (r.get('registration') or '').upper() == registration)),
        None
    )
    if not reg_obj:
        raise ValueError("Registrasi belum terdaftar! Silakan tambahkan terlebih dahulu pada menu Airline Registration.")

    id_registration = reg_obj['id_registration']
    registration = (reg_obj.get('registration') or registration or '').upper()
    operator_id = reg_obj.get('id_airline')
    scope_registration = reg_obj.get('scope') or 'Domestik'
    seat = int(reg_obj.get('seat') or 0)

    fn_clean = flight_number[:-1] if (is_adjustment and flight_number.endswith('J')) else flight_number
    fn_obj = next(
        (f for f in master_bundle['flight_numbers']
         if (id_flightnumber and f['id_flightnumber'] == id_flightnumber)
         or ((f.get('flight_number') or '').upper() == fn_clean and (f.get('kode_cabang') or '').upper() == cabang)),
        None
    )
    if fn_obj:
        id_flightnumber = fn_obj['id_flightnumber']
        if not operator_id:
            operator_id = fn_obj.get('id_airline')

    origin = cabang if is_single_cabang else ((form.get('origin') or cabang).strip().upper())
    destination = (form.get('destination') or '').strip().upper()
    if not destination:
        raise ValueError("Bandara tujuan (Destination) wajib diisi.")

    dest_ap = master_bundle['airport_by_iata'].get(destination)
    scope_route = (
        (form.get('scope_route') or '').strip()
        or (dest_ap.get('scope') if dest_ap else None)
        or (fn_obj.get('destination_scope') if fn_obj else None)
        or 'Domestik'
    )

    pricing = Pjp2uModel.resolve_pricing_snapshot(
        master_bundle=master_bundle,
        cabang=cabang,
        scope_route=scope_route,
        tanggal_str=tanggal_str,
        id_airline=operator_id,
        scope_registration=scope_registration,
    )

    raw_pax_json = (form.get('offload_passengers_json') or '').strip()
    parsed_pax = Pjp2uModel.parse_offload_passengers_json(raw_pax_json, pricing) if raw_pax_json else None

    form_with_seat = dict(form)
    form_with_seat['seat'] = seat

    if parsed_pax is not None:
        summary = Pjp2uModel.summarize_offload_passengers(parsed_pax)
        if is_adjustment and parent_row:
            base_pax = parent_row.get('offload_passengers') or []
            base_summary = Pjp2uModel.summarize_offload_passengers(base_pax)
            form_with_seat['offload'] = summary['offload_count'] - base_summary['offload_count']
            form_with_seat['diskon'] = summary['promo_count'] - base_summary['promo_count']
            form_with_seat['lama'] = summary['lama_count'] - base_summary['lama_count']
        else:
            form_with_seat['offload'] = summary['offload_count']

    metrics = Pjp2uModel.compute_metrics(form_with_seat, pricing, is_adjustment=is_adjustment)

    payload = {
        'parent_id_pjp2u': parent_row['id_pjp2u'] if parent_row else None,
        'tahun': tgl_obj.year,
        'bulan': tgl_obj.month,
        'tanggal': tanggal_str[:10],
        'cabang': cabang,
        'status': 'ADJUSTMENT' if is_adjustment else 'NORMAL',
        'boarding_time': boarding_time,
        'operator': operator_id,
        'registration': registration,
        'id_registration': id_registration,
        'flight_number': flight_number,
        'id_flightnumber': id_flightnumber,
        'origin': origin,
        'destination': destination,
        'scope_registration': scope_registration,
        'scope_route': scope_route,
        'id_tarif_baru': pricing['id_tarif_baru'],
        'id_tarif_lama': pricing['id_tarif_lama'],
        'id_promo': pricing['id_promo'],
        'persentase_diskon': pricing['persentase_diskon'],
        'persentase_ppn': pricing['persentase_ppn'],
        'tarif_psc_dpp_baru': pricing['tarif_psc_dpp_baru'],
        'tarif_psc_dpp_lama': pricing['tarif_psc_dpp_lama'],
        'tarif_counter_dpp': pricing['tarif_counter_dpp'],
        'tarif_cucs_dpp': pricing['tarif_cucs_dpp'],
        **metrics,
    }

    if is_adjustment:
        payload['justifikasi_adjustment'] = (form.get('justifikasi_adjustment') or '').strip() or None
        payload['detail_justifikasi_adjustment'] = (form.get('detail_justifikasi_adjustment') or '').strip() or None
        payload['date_adjustment'] = (form.get('date_adjustment') or _get_local_today_iso()).strip()[:10]

    return payload, parsed_pax


@pjp2u_bp.route('/')
@airport_required
@menu_required('aeronautika_pjp2u')
def index():
    user = session.get('user', {})
    role = _get_role(user)
    is_superadmin = (role == 'superadmin')
    is_privileged = role in ('superadmin', 'pengawas')

    allowed_codes, cabang_list = _get_accessible_cabangs(user)
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)

    today_str = _get_local_today_iso()
    has_date_param = ('date_from' in request.args) or ('date_to' in request.args)
    if not has_date_param:
        date_from = today_str
        date_to = today_str
    else:
        date_from = (request.args.get('date_from') or '').strip()
        date_to = (request.args.get('date_to') or '').strip()

    filter_cabang = '' if is_single_cabang else (request.args.get('cabang') or '').strip().upper()

    if filter_cabang and allowed_codes is not None and filter_cabang not in allowed_codes:
        filter_cabang = ''

    all_rows = Pjp2uModel.get_list(
        allowed_cabangs=allowed_codes,
        filter_cabang=filter_cabang or None,
        date_from=date_from or None,
        date_to=date_to or None,
        include_deleted=is_superadmin,
    )

    active_adjusted_parent_ids = Pjp2uModel.get_active_adjusted_parent_ids(allowed_cabangs=allowed_codes)

    active_rows = [r for r in all_rows if not r.get('deleted_at')]
    deleted_rows = [r for r in all_rows if r.get('deleted_at')] if is_superadmin else []

    normal_rows = [
        _compute_row_permissions(r, role, active_adjusted_parent_ids)
        for r in active_rows
        if (r.get('status') or 'NORMAL').upper() == 'NORMAL'
    ]
    adjustment_rows = [
        _compute_row_permissions(r, role, active_adjusted_parent_ids)
        for r in active_rows
        if (r.get('status') or '').upper() == 'ADJUSTMENT'
    ]
    deleted_normal_rows = [r for r in deleted_rows if (r.get('status') or 'NORMAL').upper() == 'NORMAL']
    deleted_adjustment_rows = [r for r in deleted_rows if (r.get('status') or '').upper() == 'ADJUSTMENT']

    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    return render_template(
        'aeronautika/operasional/pjp2u.html',
        normal_groups=_group_by_airline(normal_rows),
        adjustment_groups=_group_by_airline(adjustment_rows),
        deleted_normal_groups=_group_by_airline(deleted_normal_rows),
        deleted_adjustment_groups=_group_by_airline(deleted_adjustment_rows),
        normal_count=len(normal_rows),
        adjustment_count=len(adjustment_rows),
        deleted_normal_count=len(deleted_normal_rows),
        deleted_adjustment_count=len(deleted_adjustment_rows),
        cabang_list=cabang_list,
        master_bundle=master_bundle,
        is_superadmin=is_superadmin,
        is_privileged=is_privileged,
        is_single_cabang=is_single_cabang,
        default_cabang=(allowed_codes[0] if is_single_cabang else (cabang_list[0]['kode_cabang'] if cabang_list else '')),
        filter_cabang=filter_cabang,
        date_from=date_from,
        date_to=date_to,
    )


@pjp2u_bp.route('/create', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def create():
    user = session.get('user', {})
    allowed_codes, _ = _get_accessible_cabangs(user)
    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload, parsed_pax = _build_payload_from_form(request.form, master_bundle, allowed_codes, is_adjustment=False)
        Pjp2uModel.create(payload, created_by=_get_actor(user), offload_passengers=parsed_pax)
        flash('Data operasional PJP2U berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menyimpan data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/update/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def update(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    existing = Pjp2uModel.get_by_id(id_pjp2u)
    if not existing:
        flash('Data PJP2U tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang mengubah data cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    active_adjusted_parent_ids = Pjp2uModel.get_active_adjusted_parent_ids(allowed_cabangs=allowed_codes)
    _compute_row_permissions(existing, role, active_adjusted_parent_ids)
    if not existing['perm']['can_edit']:
        flash('Batas waktu edit telah habis atau data sudah diverifikasi oleh Airline.', 'danger')
        return redirect(url_for('pjp2u.index'))

    is_adj = (existing.get('status') or '').upper() == 'ADJUSTMENT'
    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload, parsed_pax = _build_payload_from_form(request.form, master_bundle, allowed_codes, is_adjustment=is_adj)
        payload['parent_id_pjp2u'] = existing.get('parent_id_pjp2u')
        Pjp2uModel.update(id_pjp2u, payload, updated_by=_get_actor(user), offload_passengers=parsed_pax)
        flash('Data PJP2U berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/offload-passengers/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def save_offload_passengers(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    existing = Pjp2uModel.get_by_id(id_pjp2u)
    if not existing:
        flash('Data PJP2U tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang mengubah data cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    active_adjusted_parent_ids = Pjp2uModel.get_active_adjusted_parent_ids(allowed_cabangs=allowed_codes)
    _compute_row_permissions(existing, role, active_adjusted_parent_ids)
    if not existing['perm']['can_edit_offload']:
        flash('Verifikasi Offload sudah diproses oleh Airline atau batas waktu edit telah habis.', 'danger')
        return redirect(url_for('pjp2u.index'))

    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)
    pricing = Pjp2uModel.resolve_pricing_snapshot(
        master_bundle=master_bundle,
        cabang=existing.get('cabang'),
        scope_route=existing.get('scope_route'),
        tanggal_str=existing.get('tanggal'),
        id_airline=existing.get('operator'),
        scope_registration=existing.get('scope_registration'),
    )

    try:
        raw_pax_json = (request.form.get('offload_passengers_json') or '[]').strip()
        parsed_pax = Pjp2uModel.parse_offload_passengers_json(raw_pax_json, pricing)
        summary = Pjp2uModel.summarize_offload_passengers(parsed_pax)

        delta_offload = summary['offload_count'] - int(existing.get('offload') or 0)
        delta_diskon = summary['promo_count'] - int(existing.get('pax_diskon') or 0)
        delta_lama = summary['lama_count'] - int(existing.get('pax_lama') or 0)

        new_form = {
            'adult': existing.get('adult') or 0,
            'child': existing.get('child') or 0,
            'infant': existing.get('infant') or 0,
            'transit': existing.get('transit') or 0,
            'crew': existing.get('crew') or 0,
            'offload': summary['offload_count'],
            'diskon': max(0, int(existing.get('pax_diskon') or 0) + delta_diskon),
            'lama': max(0, int(existing.get('pax_lama') or 0) + delta_lama),
            'seat': existing.get('seat') or 0,
        }
        metrics = Pjp2uModel.compute_metrics(new_form, pricing, is_adjustment=False)
        update_payload = {
            **metrics,
            'id_promo': pricing['id_promo'] if summary['promo_count'] > 0 else existing.get('id_promo'),
            'id_tarif_lama': pricing['id_tarif_lama'] if summary['lama_count'] > 0 else existing.get('id_tarif_lama'),
            'persentase_diskon': pricing['persentase_diskon'] if summary['promo_count'] > 0 else existing.get('persentase_diskon'),
            'tarif_psc_dpp_lama': pricing['tarif_psc_dpp_lama'] if summary['lama_count'] > 0 else existing.get('tarif_psc_dpp_lama'),
        }
        if delta_offload != 0:
            update_payload['verification_offload_at'] = None
            update_payload['name_verification_offload'] = None
            update_payload['jabatan_verification_offload'] = None

        Pjp2uModel.update(id_pjp2u, update_payload, updated_by=_get_actor(user), offload_passengers=parsed_pax)
        flash(f"Rincian penumpang offload ({summary['offload_count']} pax ditagih) berhasil disimpan!", 'success')
    except Exception as e:
        flash(f'Gagal menyimpan penumpang offload: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/adjust/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def adjust(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ('superadmin', 'pengawas'):
        flash('Hanya Pengawas dan Superadmin yang dapat membuat Adjustment PJP2U.', 'danger')
        return redirect(url_for('pjp2u.index'))

    parent_row = Pjp2uModel.get_by_id(id_pjp2u)
    if not parent_row:
        flash('Data referensi PJP2U Normal tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and parent_row['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang membuat adjustment cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    active_adjusted_parent_ids = Pjp2uModel.get_active_adjusted_parent_ids(allowed_cabangs=allowed_codes)
    if id_pjp2u in active_adjusted_parent_ids:
        flash('Penerbangan ini sudah memiliki Adjustment aktif. Hapus adjustment lama terlebih dahulu jika ingin membuat ulang.', 'warning')
        return redirect(url_for('pjp2u.index'))

    master_bundle = Pjp2uModel.get_master_bundle(allowed_cabangs=allowed_codes)

    try:
        payload, parsed_pax = _build_payload_from_form(
            request.form, master_bundle, allowed_codes, is_adjustment=True, parent_row=parent_row
        )
        created_adj = Pjp2uModel.create(payload, created_by=_get_actor(user), offload_passengers=parsed_pax)
        if parsed_pax is not None:
            Pjp2uModel.sync_offload_passengers(
                id_pjp2u=parent_row['id_pjp2u'],
                cabang=parent_row.get('cabang'),
                pax_list=parsed_pax,
                actor=_get_actor(user),
            )
        flash(f"Adjustment {created_adj['flight_number']} berhasil disimpan ke tab Adjustment!", 'success')
    except Exception as e:
        flash(f'Gagal menyimpan Adjustment PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/delete/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def delete(id_pjp2u):
    user = session.get('user', {})
    role = _get_role(user)
    existing = Pjp2uModel.get_by_id(id_pjp2u)
    if not existing:
        flash('Data PJP2U tidak ditemukan.', 'warning')
        return redirect(url_for('pjp2u.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang menghapus data cabang ini.', 'danger')
        return redirect(url_for('pjp2u.index'))

    active_adjusted_parent_ids = Pjp2uModel.get_active_adjusted_parent_ids(allowed_cabangs=allowed_codes)
    _compute_row_permissions(existing, role, active_adjusted_parent_ids)
    if not existing['perm']['can_delete']:
        flash('Batas waktu hapus (3 hari) telah terlewati.', 'danger')
        return redirect(url_for('pjp2u.index'))

    try:
        Pjp2uModel.delete(id_pjp2u, deleted_by=_get_actor(user))
        flash('Data PJP2U berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))


@pjp2u_bp.route('/restore/<int:id_pjp2u>', methods=['POST'])
@airport_required
@menu_required('aeronautika_pjp2u')
def restore(id_pjp2u):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengembalikan data terhapus.', 'danger')
        return redirect(url_for('pjp2u.index'))

    try:
        Pjp2uModel.restore(id_pjp2u, restored_by=_get_actor(user))
        flash('Data PJP2U berhasil dipulihkan!', 'success')
    except Exception as e:
        flash(f'Gagal memulihkan data PJP2U: {str(e)}', 'danger')

    return redirect(url_for('pjp2u.index'))