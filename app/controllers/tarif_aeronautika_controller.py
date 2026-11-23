from flask import Blueprint, render_template, request, redirect, url_for, flash, session
import app
from app.models.tarif_aeronautika_model import TarifAeronautikaModel
from app.utils.decorators import menu_required

tarif_aero_bp = Blueprint('tarif_aero', __name__, url_prefix='/aeronautika/setting/tarif')

ALLOWED_ROLES = {'superadmin', 'pengawas'}

# Urutan baku Sub Kategori (1..13) dan scope Jenis Jasa yang diizinkan
SUB_KATEGORI_CONFIG = [
    {"value": "Domestik", "scope": "GLOBAL"},
    {"value": "Internasional", "scope": "GLOBAL"},
    {"value": "Haji", "scope": "GLOBAL"},
    {"value": "Incoming", "scope": "PJKP2U"},
    {"value": "Outgoing", "scope": "PJKP2U"},
    {"value": "Import", "scope": "PJKP2U"},
    {"value": "Export", "scope": "PJKP2U"},
    {"value": "Passenger", "scope": "EXTENDED_ADVANCE"},
    {"value": "Cargo", "scope": "EXTENDED_ADVANCE"},
    {"value": "Local", "scope": "EXTENDED_ADVANCE"},
    {"value": "Run Up Engine", "scope": "EXTENDED_ADVANCE"},
    {"value": "Photo", "scope": "EXTENDED_ADVANCE"},
    {"value": "Training", "scope": "EXTENDED_ADVANCE"},
]


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


def _get_accessible_cabangs(user):
    """
    Mengikuti pola session user['allowed_cabang'] dan struktur tabel cabang
    (kode_cabang, nama_cabang, tipe_unit, parent_kode, kota):
    - None          : HO / Superadmin -> semua cabang
    - List > 1 item : Regional (misal REG6 -> ['BDJ', 'PKY', 'BPN', 'PNK'])
    - List 1 item   : Cabang tunggal (misal ['BDJ'])
    """
    role = _get_role(user)
    query = app.supabase.table('cabang').select('kode_cabang, nama_cabang, tipe_unit, parent_kode, kota').is_('deleted_at', 'null')

    if role == 'superadmin':
        res = query.order('kode_cabang', desc=False).execute()
        return None, (res.data or [])

    # Gunakan allowed_cabang yang sudah di-resolve saat login (sama seperti flight_number_controller.py)
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

    # Fallback jika session lama belum memuat allowed_cabang
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


def _resolve_promo_cabangs(request_form, allowed_codes):
    """
    Validasi dan resolusi pilihan cabang pada Promo/Diskon sesuai hierarki:
    - HO (allowed_codes is None) : Bisa Nasional (None) atau pilih multi-cabang
    - Regional (len > 1)         : Wajib pilih 1 atau lebih cabang di bawah Regional-nya
    - Cabang Tunggal (len == 1)  : Otomatis terkunci ke cabang user tersebut
    """
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)
    is_nasional = request_form.get('is_nasional') == '1'
    selected_cabs = [
        c.strip().upper()
        for c in request_form.getlist('kode_cabang')
        if c and c.strip()
    ]

    if is_single_cabang:
        return [allowed_codes[0]], None

    if is_nasional or '__ALL__' in selected_cabs:
        if allowed_codes is not None:
            return None, ('Hanya Superadmin / Kantor Pusat (HO) yang dapat mengatur promo Nasional untuk seluruh cabang.', 'danger')
        return None, None

    if not selected_cabs:
        return None, ('Pilih minimal 1 cabang bandara atau centang Berlaku Nasional.', 'warning')

    if allowed_codes is not None:
        invalid_cabs = [c for c in selected_cabs if c not in allowed_codes]
        if invalid_cabs:
            return None, (f'Anda tidak memiliki wewenang untuk cabang: {", ".join(invalid_cabs)}.', 'danger')

    return selected_cabs, None


def _can_manage_existing_promo(promo_row, allowed_codes):
    """Memastikan user Regional/Cabang hanya dapat mengubah/menghapus promo milik wilayahnya sendiri (bukan Nasional/cabang lain)."""
    if allowed_codes is None:
        return True
    promo_cabs = promo_row.get('kode_cabang')
    if not promo_cabs:
        # Promo Nasional (None) hanya boleh diubah/dihapus oleh HO/Superadmin
        return False
    allowed_set = {c.strip().upper() for c in allowed_codes}
    promo_set = {str(c).strip().upper() for c in promo_cabs}
    return promo_set.issubset(allowed_set)


def _parse_details_from_form(form):
    batas_bawah_list = form.getlist('batas_bawah[]')
    batas_atas_list = form.getlist('batas_atas[]')
    kelipatan_list = form.getlist('kelipatan_unit[]')
    tarif_dpp_list = form.getlist('tarif_dpp[]')

    details = []
    for i, raw_tarif in enumerate(tarif_dpp_list):
        clean_tarif = (raw_tarif or '').strip().replace(',', '')
        if clean_tarif == '':
            continue
        bb = (batas_bawah_list[i] if i < len(batas_bawah_list) else '0').strip() or '0'
        ba = (batas_atas_list[i] if i < len(batas_atas_list) else '').strip()
        kel = (kelipatan_list[i] if i < len(kelipatan_list) else '1').strip() or '1'
        details.append({
            'batas_bawah': float(bb),
            'batas_atas': float(ba) if ba != '' else None,
            'kelipatan_unit': float(kel),
            'tarif_dpp': float(clean_tarif),
        })
    return details


@tarif_aero_bp.route('/')
@menu_required('tarif_aeronautika')
def index():
    user = session.get('user', {})
    role = _get_role(user)
    if role not in ALLOWED_ROLES:
        flash('Menu Tarif Aeronautika hanya dapat diakses oleh Superadmin dan Pengawas.', 'danger')
        return redirect(url_for('dashboard.index'))

    is_superadmin = (role == 'superadmin')
    allowed_codes, cabang_list = _get_accessible_cabangs(user)
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)

    tarif_list = TarifAeronautikaModel.get_all(
        allowed_cabangs=allowed_codes,
        include_deleted=is_superadmin
    )
    promo_list = TarifAeronautikaModel.get_all_promos(
        allowed_cabangs=allowed_codes,
        include_deleted=is_superadmin
    )
    airline_list = TarifAeronautikaModel.get_all_airlines()

    coa_res = (
        app.supabase.table('coa_pendapatan')
        .select('*')
        .eq('klasifikasi', 'Aeronautika')
        .is_('deleted_at', 'null')
        .order('kode_account', desc=False)
        .execute()
    )
    coa_list = [
        c for c in (coa_res.data or [])
        if (c.get('klasifikasi') or '').strip().lower() == 'aeronautika'
    ]

    base_sub_kats = [item['value'] for item in SUB_KATEGORI_CONFIG]
    extra_sub_kats = sorted({
        r.get('sub_kategori') for r in tarif_list
        if r.get('sub_kategori') and r.get('sub_kategori') not in base_sub_kats
    })
    ordered_sub_kats = base_sub_kats + extra_sub_kats

    merged_config = list(SUB_KATEGORI_CONFIG) + [
        {"value": sk, "scope": "GLOBAL"} for sk in extra_sub_kats
    ]

    existing_satuans = sorted({
        *(r.get('satuan') for r in tarif_list if r.get('satuan')),
        'Pax', 'Ton', 'Jam', 'Kg', 'Pemakaian'
    })

    return render_template(
        'aeronautika/tarif.html',
        tarif_list=tarif_list,
        promo_list=promo_list,
        airline_list=airline_list,
        cabang_list=cabang_list,
        coa_list=coa_list,
        jenis_jasa_choices=TarifAeronautikaModel.JENIS_JASA_CHOICES,
        sub_kategori_choices=ordered_sub_kats,
        sub_kategori_config=merged_config,
        satuan_choices=existing_satuans,
        is_superadmin=is_superadmin,
        is_global_scope=(allowed_codes is None),
        is_single_cabang=is_single_cabang
    )


@tarif_aero_bp.route('/create', methods=['POST'])
@menu_required('tarif_aeronautika')
def create():
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)

    kode_cabang = (
        allowed_codes[0] if is_single_cabang
        else (request.form.get('kode_cabang') or '').strip().upper()
    )
    if allowed_codes is not None and kode_cabang not in allowed_codes:
        flash(f'Anda tidak memiliki wewenang mengatur tarif untuk cabang {kode_cabang}.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    kode_account = (request.form.get('kode_account') or '').strip()
    jenis_jasa = (request.form.get('jenis_jasa') or '').strip().upper()
    sub_kategori = (request.form.get('sub_kategori') or '').strip()
    terminal = (request.form.get('terminal') or '').strip() or None
    mata_uang = (request.form.get('mata_uang') or 'IDR').strip().upper()
    metode_hitung = (request.form.get('metode_hitung') or 'PER_UNIT').strip().upper()
    satuan = (request.form.get('satuan') or 'Pax').strip()
    is_kena_ppn = request.form.get('is_kena_ppn') == '1'
    berlaku_mulai = (request.form.get('berlaku_mulai') or '').strip()
    nomor_sk = (request.form.get('nomor_sk') or '').strip() or None

    if not all([kode_cabang, kode_account, jenis_jasa, sub_kategori, berlaku_mulai]):
        flash('Cabang, COA Pendapatan, Jenis Jasa, Sub Kategori, dan Tanggal Berlaku wajib diisi.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    try:
        details = _parse_details_from_form(request.form)
    except ValueError:
        flash('Format angka pada rincian tarif DPP tidak valid.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    if not details:
        flash('Minimal harus mengisi 1 baris rincian Tarif DPP.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.create(
            {
                'kode_cabang': kode_cabang,
                'kode_account': kode_account,
                'jenis_jasa': jenis_jasa,
                'sub_kategori': sub_kategori,
                'terminal': terminal,
                'mata_uang': mata_uang,
                'metode_hitung': metode_hitung,
                'satuan': satuan,
                'is_kena_ppn': is_kena_ppn,
                'berlaku_mulai': berlaku_mulai,
                'nomor_sk': nomor_sk,
            },
            details,
            created_by=_get_actor(user),
        )
        flash('Tarif Aeronautika berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menambahkan Tarif Aeronautika: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


@tarif_aero_bp.route('/update/<int:id_tarif>', methods=['POST'])
@menu_required('tarif_aeronautika')
def update(id_tarif):
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    existing = TarifAeronautikaModel.get_by_id(id_tarif)
    if not existing:
        flash('Data tarif tidak ditemukan atau sudah dihapus.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    is_single_cabang = (allowed_codes is not None and len(allowed_codes) == 1)

    kode_cabang = (
        allowed_codes[0] if is_single_cabang
        else (request.form.get('kode_cabang') or existing.get('kode_cabang') or '').strip().upper()
    )
    if allowed_codes is not None and (existing['kode_cabang'] not in allowed_codes or kode_cabang not in allowed_codes):
        flash('Anda tidak memiliki wewenang mengubah tarif cabang ini.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    try:
        details = _parse_details_from_form(request.form)
    except ValueError:
        flash('Format angka pada rincian tarif DPP tidak valid.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    if not details:
        flash('Minimal harus mengisi 1 baris rincian Tarif DPP.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.update(
            id_tarif,
            {
                'kode_cabang': kode_cabang,
                'kode_account': (request.form.get('kode_account') or '').strip(),
                'jenis_jasa': (request.form.get('jenis_jasa') or '').strip().upper(),
                'sub_kategori': (request.form.get('sub_kategori') or '').strip(),
                'terminal': (request.form.get('terminal') or '').strip() or None,
                'mata_uang': (request.form.get('mata_uang') or 'IDR').strip().upper(),
                'metode_hitung': (request.form.get('metode_hitung') or 'PER_UNIT').strip().upper(),
                'satuan': (request.form.get('satuan') or 'Pax').strip(),
                'is_kena_ppn': request.form.get('is_kena_ppn') == '1',
                'berlaku_mulai': (request.form.get('berlaku_mulai') or '').strip(),
                'nomor_sk': (request.form.get('nomor_sk') or '').strip() or None,
            },
            details,
            updated_by=_get_actor(user),
        )
        flash('Tarif Aeronautika berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui Tarif Aeronautika: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


@tarif_aero_bp.route('/delete/<int:id_tarif>', methods=['POST'])
@menu_required('tarif_aeronautika')
def delete(id_tarif):
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    existing = TarifAeronautikaModel.get_by_id(id_tarif)
    if not existing:
        flash('Data tarif tidak ditemukan.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    if allowed_codes is not None and existing['kode_cabang'] not in allowed_codes:
        flash('Anda tidak memiliki wewenang menghapus tarif cabang ini.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.delete(id_tarif, deleted_by=_get_actor(user))
        flash('Tarif Aeronautika berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus Tarif Aeronautika: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


@tarif_aero_bp.route('/restore/<int:id_tarif>', methods=['POST'])
@menu_required('tarif_aeronautika')
def restore(id_tarif):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali tarif terhapus.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.restore(id_tarif, restored_by=_get_actor(user))
        flash('Tarif Aeronautika berhasil dikembalikan!', 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan Tarif Aeronautika: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


# ================= ROUTES PROMO / DISKON PJP2U =================
@tarif_aero_bp.route('/promo/create', methods=['POST'])
@menu_required('tarif_aeronautika')
def create_promo():
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    final_cabs, cab_err = _resolve_promo_cabangs(request.form, allowed_codes)
    if cab_err:
        flash(cab_err[0], cab_err[1])
        return redirect(url_for('tarif_aero.index'))

    is_all_airlines = request.form.get('is_all_airlines') == '1'
    selected_airlines = [
        a.strip() for a in request.form.getlist('id_airline') if a and a.strip()
    ]

    if is_all_airlines:
        final_airlines = None
    else:
        if not selected_airlines:
            flash('Pilih minimal 1 maskapai atau aktifkan saklar Semua Maskapai.', 'warning')
            return redirect(url_for('tarif_aero.index'))
        final_airlines = selected_airlines

    try:
        TarifAeronautikaModel.create_promo({
            'nama_promo': request.form.get('nama_promo'),
            'id_airline': final_airlines,
            'kode_cabang': final_cabs,
            'sub_kategori': request.form.get('sub_kategori'),
            'persentase_diskon': request.form.get('persentase_diskon'),
            'flight_date_start': request.form.get('flight_date_start'),
            'flight_date_end': request.form.get('flight_date_end'),
            'doi_start': request.form.get('doi_start'),
            'doi_end': request.form.get('doi_end'),
            'nomor_sk': request.form.get('nomor_sk'),
        }, created_by=_get_actor(user))
        flash('Program Diskon / Promo PJP2U berhasil ditambahkan!', 'success')
    except Exception as e:
        flash(f'Gagal menyimpan promo PJP2U: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


@tarif_aero_bp.route('/promo/update/<int:id_promo>', methods=['POST'])
@menu_required('tarif_aeronautika')
def update_promo(id_promo):
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)

    # Validasi wewenang terhadap data promo yang akan diedit
    all_promos = TarifAeronautikaModel.get_all_promos(allowed_cabangs=None, include_deleted=False)
    existing_promo = next((p for p in all_promos if p.get('id_promo') == id_promo), None)
    if not existing_promo:
        flash('Data program diskon tidak ditemukan.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    if not _can_manage_existing_promo(existing_promo, allowed_codes):
        flash('Anda tidak memiliki wewenang mengubah program diskon Nasional atau cabang di luar wilayah Anda.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    final_cabs, cab_err = _resolve_promo_cabangs(request.form, allowed_codes)
    if cab_err:
        flash(cab_err[0], cab_err[1])
        return redirect(url_for('tarif_aero.index'))

    is_all_airlines = request.form.get('is_all_airlines') == '1'
    selected_airlines = [
        a.strip() for a in request.form.getlist('id_airline') if a and a.strip()
    ]

    if is_all_airlines:
        final_airlines = None
    else:
        if not selected_airlines:
            flash('Pilih minimal 1 maskapai atau aktifkan saklar Semua Maskapai.', 'warning')
            return redirect(url_for('tarif_aero.index'))
        final_airlines = selected_airlines

    try:
        TarifAeronautikaModel.update_promo(id_promo, {
            'nama_promo': request.form.get('nama_promo'),
            'id_airline': final_airlines,
            'kode_cabang': final_cabs,
            'sub_kategori': request.form.get('sub_kategori'),
            'persentase_diskon': request.form.get('persentase_diskon'),
            'flight_date_start': request.form.get('flight_date_start'),
            'flight_date_end': request.form.get('flight_date_end'),
            'doi_start': request.form.get('doi_start'),
            'doi_end': request.form.get('doi_end'),
            'nomor_sk': request.form.get('nomor_sk'),
        }, updated_by=_get_actor(user))
        flash('Program Diskon / Promo PJP2U berhasil diperbarui!', 'success')
    except Exception as e:
        flash(f'Gagal memperbarui promo PJP2U: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))


@tarif_aero_bp.route('/promo/delete/<int:id_promo>', methods=['POST'])
@menu_required('tarif_aeronautika')
def delete_promo(id_promo):
    user = session.get('user', {})
    if _get_role(user) not in ALLOWED_ROLES:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    allowed_codes, _ = _get_accessible_cabangs(user)
    all_promos = TarifAeronautikaModel.get_all_promos(allowed_cabangs=None, include_deleted=False)
    existing_promo = next((p for p in all_promos if p.get('id_promo') == id_promo), None)
    if not existing_promo:
        flash('Data program diskon tidak ditemukan.', 'warning')
        return redirect(url_for('tarif_aero.index'))

    if not _can_manage_existing_promo(existing_promo, allowed_codes):
        flash('Anda tidak memiliki wewenang menghapus program diskon Nasional atau cabang di luar wilayah Anda.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.delete_promo(id_promo, deleted_by=_get_actor(user))
        flash('Program Diskon PJP2U berhasil dihapus!', 'success')
    except Exception as e:
        flash(f'Gagal menghapus promo PJP2U: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))

@tarif_aero_bp.route('/promo/restore/<int:id_promo>', methods=['POST'])
@menu_required('tarif_aeronautika')
def restore_promo(id_promo):
    user = session.get('user', {})
    if _get_role(user) != 'superadmin':
        flash('Hanya Superadmin yang dapat mengaktifkan kembali program diskon terhapus.', 'danger')
        return redirect(url_for('tarif_aero.index'))

    try:
        TarifAeronautikaModel.restore_promo(id_promo, restored_by=_get_actor(user))
        flash('Program Diskon PJP2U berhasil dikembalikan!', 'success')
    except Exception as e:
        flash(f'Gagal mengembalikan promo PJP2U: {str(e)}', 'danger')

    return redirect(url_for('tarif_aero.index'))