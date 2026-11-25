import json
from datetime import datetime, timezone
from app.utils.ba_verification import generate_ba_token
import app


class Pjp2uModel:
    TABLE = "operasional_pjp2u"
    OFFLOAD_PAX_TABLE = "pjp2u_offload_passenger"
    AIRLINE_TABLE = "airline_data"
    REG_TABLE = "airline_registration"
    FLIGHT_TABLE = "flight_numbers"
    AIRPORT_TABLE = "airport"
    TARIF_TABLE = "tarif_aeronautika"
    TARIF_DETAIL_TABLE = "tarif_aeronautika_detail"
    PROMO_TABLE = "pjp2u_promo"
    PPN_TABLE = "master_ppn"

    @staticmethod
    def _to_int(val, default=0):
        try:
            if val in (None, ""):
                return default
            return int(float(val))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _to_float(val, default=0.0):
        try:
            if val in (None, ""):
                return default
            return float(str(val).replace(",", ""))
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _parse_iso_dt(dt_str):
        if not dt_str:
            return None
        if isinstance(dt_str, datetime):
            return dt_str if dt_str.tzinfo else dt_str.replace(tzinfo=timezone.utc)
        try:
            clean = str(dt_str).strip().replace("Z", "+00:00")
            if len(clean) == 10:
                parsed = datetime.fromisoformat(f"{clean}T00:00:00+00:00")
            else:
                parsed = datetime.fromisoformat(clean)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception:
            return None

    @staticmethod
    def get_active_adjusted_parent_ids(allowed_cabangs=None):
        query = (
            app.supabase.table(Pjp2uModel.TABLE)
            .select("parent_id_pjp2u, cabang")
            .eq("status", "ADJUSTMENT")
            .is_("deleted_at", "null")
            .not_.is_("parent_id_pjp2u", "null")
        )
        if allowed_cabangs is not None:
            clean_cabs = [c.strip().upper() for c in allowed_cabangs if c and c.strip()]
            if not clean_cabs:
                return set()
            query = query.in_("cabang", clean_cabs)

        res = query.execute()
        parent_ids = set()
        for r in (res.data or []):
            pid = Pjp2uModel._to_int(r.get("parent_id_pjp2u"), 0)
            if pid > 0:
                parent_ids.add(pid)
        return parent_ids

    @staticmethod
    def compute_row_permissions(row, role, active_adjusted_parent_ids=None, now_utc=None):
        now = now_utc or datetime.now(timezone.utc)
        role_low = str(role or "").strip().lower()
        adj_parent_ids = active_adjusted_parent_ids or set()

        ref_dt = (
            Pjp2uModel._parse_iso_dt(row.get("created_at"))
            or Pjp2uModel._parse_iso_dt(row.get("createdatetime"))
            or Pjp2uModel._parse_iso_dt(row.get("tanggal"))
            or now
        )
        age_hours = max(0.0, (now - ref_dt).total_seconds() / 3600.0)
        age_days = age_hours / 24.0

        status = (row.get("status") or "NORMAL").strip().upper()
        is_superadmin = role_low == "superadmin"
        is_pengawas = role_low == "pengawas"
        is_privileged = is_superadmin or is_pengawas
        is_admin = role_low == "admin"
        is_user = role_low == "user"

        row_id = Pjp2uModel._to_int(row.get("id_pjp2u"), 0)
        has_active_adjustment = row_id > 0 and (row_id in adj_parent_ids)

        if status == "NORMAL":
            is_verified = bool(row.get("verification_at"))
            is_offload_verified = bool(row.get("verification_offload_at"))

            # Edit di menu Normal:
            # - Superadmin & Pengawas: masih bisa edit apabila masih <= 1 minggu (7 hari / 168 jam)
            # - Admin: jika sudah diverifikasi tidak bisa edit; jika belum diverifikasi maksimal 3 hari (72 jam)
            # - User: jika sudah diverifikasi tidak bisa edit; jika belum diverifikasi maksimal 1,5 hari (36 jam)
            if is_privileged:
                can_edit = age_days <= 7.0
            elif is_admin:
                can_edit = (not is_verified) and (age_days <= 3.0)
            elif is_user:
                can_edit = (not is_verified) and (age_hours <= 36.0)
            else:
                can_edit = False

            # Kelola penumpang offload di Normal
            if is_privileged:
                can_edit_offload = (not is_offload_verified) and (age_days <= 7.0)
            elif is_admin:
                can_edit_offload = (not is_offload_verified) and (age_days <= 3.0)
            elif is_user:
                can_edit_offload = (not is_offload_verified) and (age_hours <= 36.0)
            else:
                can_edit_offload = False

            # Delete:
            # - Superadmin & Pengawas: terbuka selamanya
            # - User & Admin: jika sudah > 3 hari (72 jam) di-hide
            if is_privileged:
                can_delete = True
            elif is_admin or is_user:
                can_delete = age_days <= 3.0
            else:
                can_delete = False

            # Tombol Adj di Normal: otomatis di-hide jika sudah pernah di-adjustment (dan belum dihapus)
            can_adjust = is_privileged and (not has_active_adjustment)
            can_ba_normal = is_verified
            can_ba_offload = (Pjp2uModel._to_int(row.get("offload"), 0) > 0) and is_offload_verified
            can_ba_adjustment = False
        else:
            is_adj_verified = bool(row.get("verification_adjustment_at"))
            can_edit = is_privileged and (not is_adj_verified)
            can_edit_offload = False
            if is_privileged:
                can_delete = True
            elif is_admin or is_user:
                can_delete = age_days <= 3.0
            else:
                can_delete = False
            can_adjust = False
            can_ba_normal = False
            can_ba_offload = False
            can_ba_adjustment = is_adj_verified

        row["has_active_adjustment"] = has_active_adjustment
        row["perm"] = {
            "can_edit": can_edit,
            "can_edit_offload": can_edit_offload,
            "can_delete": can_delete,
            "can_adjust": can_adjust,
            "can_ba_normal": can_ba_normal,
            "can_ba_offload": can_ba_offload,
            "can_ba_adjustment": can_ba_adjustment,
        }
        return row

    @staticmethod
    def resolve_effective_tariff_scope(scope_registration, scope_route):
        reg_scope = (scope_registration or "Domestik").strip().lower()
        if "inter" in reg_scope:
            return "Internasional"
        return (scope_route or "Domestik").strip() or "Domestik"

    @staticmethod
    def get_master_bundle(allowed_cabangs=None):
        al_res = (
            app.supabase.table(Pjp2uModel.AIRLINE_TABLE)
            .select("id_airline, airline_name, code_2, code_3, logo")
            .is_("delete_at", "null")
            .order("airline_name", desc=False)
            .execute()
        )
        airlines = al_res.data or []
        airline_map = {Pjp2uModel._to_int(a["id_airline"]): a for a in airlines}

        ap_res = (
            app.supabase.table(Pjp2uModel.AIRPORT_TABLE)
            .select("id_airport, iata, icao, airport_name, city, country, scope")
            .is_("deleted_at", "null")
            .order("iata", desc=False)
            .execute()
        )
        airports = ap_res.data or []
        airport_by_id = {Pjp2uModel._to_int(ap["id_airport"]): ap for ap in airports}
        airport_by_iata = {(ap.get("iata") or "").strip().upper(): ap for ap in airports if ap.get("iata")}

        fn_query = (
            app.supabase.table(Pjp2uModel.FLIGHT_TABLE)
            .select("id_flightnumber, id_airline, flight_number, origin_airport_id, destination_airport_id, scope, kode_cabang, status")
            .is_("deleted_at", "null")
        )
        if allowed_cabangs is not None:
            clean_cabs = [c.strip().upper() for c in allowed_cabangs if c and c.strip()]
            if not clean_cabs:
                flight_numbers = []
            else:
                fn_query = fn_query.in_("kode_cabang", clean_cabs)
                flight_numbers = fn_query.order("flight_number", desc=False).execute().data or []
        else:
            flight_numbers = fn_query.order("flight_number", desc=False).execute().data or []

        for fn in flight_numbers:
            orig_id = Pjp2uModel._to_int(fn.get("origin_airport_id"), 0)
            dest_id = Pjp2uModel._to_int(fn.get("destination_airport_id"), 0)
            al_id = Pjp2uModel._to_int(fn.get("id_airline"), 0)

            orig_ap = airport_by_id.get(orig_id) or {}
            dest_ap = airport_by_id.get(dest_id) or {}
            al_obj = airline_map.get(al_id) or {}

            cab_code = (fn.get("kode_cabang") or "").strip().upper()
            fn["kode_cabang"] = cab_code
            fn["origin_iata"] = (orig_ap.get("iata") or cab_code).strip().upper()
            fn["origin_name"] = orig_ap.get("airport_name") or ""
            fn["destination_iata"] = (dest_ap.get("iata") or "").strip().upper()
            fn["destination_name"] = dest_ap.get("airport_name") or ""
            fn["destination_scope"] = (fn.get("scope") or dest_ap.get("scope") or "Domestik").strip()
            fn["airline_name"] = al_obj.get("airline_name") or ""
            fn["code_2"] = al_obj.get("code_2") or ""

        reg_res = (
            app.supabase.table(Pjp2uModel.REG_TABLE)
            .select("*")
            .is_("deleted_at", "null")
            .order("registration", desc=False)
            .execute()
        )
        registrations = reg_res.data or []
        for reg in registrations:
            al_obj = airline_map.get(Pjp2uModel._to_int(reg.get("id_airline"), 0)) or {}
            reg["registration"] = (reg.get("registration") or "").strip().upper()
            reg["airline_name"] = al_obj.get("airline_name") or "Unknown Airline"
            reg["code_2"] = al_obj.get("code_2") or ""
            reg["airline_logo"] = al_obj.get("logo") or ""

        t_query = (
            app.supabase.table(Pjp2uModel.TARIF_TABLE)
            .select("*")
            .in_("jenis_jasa", ["PJP2U", "COUNTER", "CUCS"])
            .is_("delete_at", "null")
        )
        if allowed_cabangs is not None:
            clean_cabs = [c.strip().upper() for c in allowed_cabangs if c and c.strip()]
            if not clean_cabs:
                tarifs = []
            else:
                tarifs = t_query.in_("kode_cabang", clean_cabs).order("berlaku_mulai", desc=True).execute().data or []
        else:
            tarifs = t_query.order("berlaku_mulai", desc=True).execute().data or []

        t_ids = [t["id_tarif"] for t in tarifs if t.get("id_tarif") is not None]
        det_map = {}
        if t_ids:
            det_res = (
                app.supabase.table(Pjp2uModel.TARIF_DETAIL_TABLE)
                .select("*")
                .in_("id_tarif", t_ids)
                .order("tahap_ke", desc=False)
                .execute()
            )
            for d in (det_res.data or []):
                det_map.setdefault(d["id_tarif"], []).append(d)

        for t in tarifs:
            dets = det_map.get(t["id_tarif"], [])
            t["kode_cabang"] = (t.get("kode_cabang") or "").strip().upper()
            t["jenis_jasa"] = (t.get("jenis_jasa") or "").strip().upper()
            t["sub_kategori"] = (t.get("sub_kategori") or "").strip()
            t["mata_uang"] = (t.get("mata_uang") or "IDR").strip().upper()
            t["details"] = dets
            if dets:
                kel = Pjp2uModel._to_float(dets[0].get("kelipatan_unit"), 1.0) or 1.0
                raw_dpp = Pjp2uModel._to_float(dets[0].get("tarif_dpp"), 0.0)
                t["tarif_dpp_utama"] = raw_dpp / kel
            else:
                t["tarif_dpp_utama"] = 0.0

        promo_res = (
            app.supabase.table(Pjp2uModel.PROMO_TABLE)
            .select("*")
            .is_("delete_at", "null")
            .order("flight_date_start", desc=True)
            .execute()
        )
        promos = promo_res.data or []
        for p in promos:
            raw_cabs = p.get("kode_cabang")
            if isinstance(raw_cabs, str):
                p["kode_cabang"] = [c.strip().upper() for c in raw_cabs.strip("[]{}").replace('"', "").split(",") if c.strip()] or None
            elif isinstance(raw_cabs, list):
                p["kode_cabang"] = [str(c).strip().upper() for c in raw_cabs if str(c).strip()] or None

            raw_al = p.get("id_airline")
            if isinstance(raw_al, str):
                p["id_airline"] = [int(x.strip()) for x in raw_al.strip("[]{}").replace('"', "").split(",") if x.strip().isdigit()] or None
            elif isinstance(raw_al, list):
                p["id_airline"] = [int(x) for x in raw_al if str(x).isdigit()] or None
            elif isinstance(raw_al, int):
                p["id_airline"] = [raw_al]

        ppn_res = (
            app.supabase.table(Pjp2uModel.PPN_TABLE)
            .select("*")
            .is_("delete_at", "null")
            .order("berlaku_mulai", desc=True)
            .execute()
        )
        ppn_list = ppn_res.data or []

        return {
            "airlines": airlines,
            "airline_map": airline_map,
            "airports": airports,
            "airport_by_iata": airport_by_iata,
            "flight_numbers": flight_numbers,
            "registrations": registrations,
            "tarifs": tarifs,
            "promos": promos,
            "ppn_list": ppn_list,
        }

    @staticmethod
    def resolve_pricing_snapshot(
        master_bundle,
        cabang,
        scope_route,
        tanggal_str,
        id_airline=None,
        scope_registration=None,
    ):
        cab = (cabang or "").strip().upper()
        effective_scope = Pjp2uModel.resolve_effective_tariff_scope(scope_registration, scope_route)
        scope_low = effective_scope.strip().lower()
        tgl = str(tanggal_str or "")[:10]

        ppn_pct = 11.0
        for p in master_bundle.get("ppn_list", []):
            bm = str(p.get("berlaku_mulai") or "")[:10]
            if not bm or bm <= tgl:
                ppn_pct = float(p.get("persentase") or 11.0)
                break

        tarifs = master_bundle.get("tarifs", [])

        def _match_tarifs(jenis):
            matched = [
                t for t in tarifs
                if (t.get("kode_cabang") or "").upper() == cab
                and (t.get("jenis_jasa") or "").upper() == jenis
                and (t.get("sub_kategori") or "").strip().lower() == scope_low
                and (not t.get("berlaku_mulai") or str(t.get("berlaku_mulai"))[:10] <= tgl)
            ]
            if not matched and jenis in ("COUNTER", "CUCS"):
                matched = [
                    t for t in tarifs
                    if (t.get("kode_cabang") or "").upper() == cab
                    and (t.get("jenis_jasa") or "").upper() == jenis
                    and (t.get("sub_kategori") or "").strip().lower() == "domestik"
                    and (not t.get("berlaku_mulai") or str(t.get("berlaku_mulai"))[:10] <= tgl)
                ]
            return matched

        pjp2u_tarifs = _match_tarifs("PJP2U")
        tarif_baru_obj = pjp2u_tarifs[0] if len(pjp2u_tarifs) >= 1 else None
        tarif_lama_obj = pjp2u_tarifs[1] if len(pjp2u_tarifs) >= 2 else None

        counter_tarifs = _match_tarifs("COUNTER")
        counter_obj = counter_tarifs[0] if counter_tarifs else None

        cucs_tarifs = _match_tarifs("CUCS")
        cucs_obj = cucs_tarifs[0] if cucs_tarifs else None

        tarif_psc_baru = float(tarif_baru_obj["tarif_dpp_utama"]) if tarif_baru_obj else 0.0
        tarif_psc_lama = float(tarif_lama_obj["tarif_dpp_utama"]) if tarif_lama_obj else tarif_psc_baru
        tarif_baru_berlaku = str(tarif_baru_obj.get("berlaku_mulai") or "")[:10] if tarif_baru_obj else ""
        is_kena_ppn_psc = bool(tarif_baru_obj.get("is_kena_ppn", True)) if tarif_baru_obj else True
        mata_uang_psc = (tarif_baru_obj.get("mata_uang") or "IDR").upper() if tarif_baru_obj else "IDR"

        tarif_counter = float(counter_obj["tarif_dpp_utama"]) if counter_obj else 0.0
        is_kena_ppn_counter = bool(counter_obj.get("is_kena_ppn", True)) if counter_obj else True
        mata_uang_counter = (counter_obj.get("mata_uang") or "IDR").upper() if counter_obj else "IDR"

        tarif_cucs = float(cucs_obj["tarif_dpp_utama"]) if cucs_obj else 0.0
        is_kena_ppn_cucs = bool(cucs_obj.get("is_kena_ppn", True)) if cucs_obj else True
        mata_uang_cucs = (cucs_obj.get("mata_uang") or "IDR").upper() if cucs_obj else "IDR"

        active_promo = None
        for pr in master_bundle.get("promos", []):
            if (pr.get("sub_kategori") or "").strip().lower() != scope_low:
                continue
            f_start = str(pr.get("flight_date_start") or "")[:10]
            f_end = str(pr.get("flight_date_end") or "")[:10]
            if f_start and tgl < f_start:
                continue
            if f_end and tgl > f_end:
                continue
            pr_cabs = pr.get("kode_cabang")
            if pr_cabs and cab not in pr_cabs:
                continue
            pr_airlines = pr.get("id_airline")
            if pr_airlines and id_airline and int(id_airline) not in pr_airlines:
                continue
            active_promo = pr
            break

        diskon_pct = float(active_promo.get("persentase_diskon") or 0.0) if active_promo else 0.0

        return {
            "effective_tariff_scope": effective_scope,
            "mata_uang_psc": mata_uang_psc,
            "mata_uang_counter": mata_uang_counter,
            "mata_uang_cucs": mata_uang_cucs,
            "id_tarif_baru": tarif_baru_obj["id_tarif"] if tarif_baru_obj else None,
            "id_tarif_lama": tarif_lama_obj["id_tarif"] if tarif_lama_obj else None,
            "tarif_baru_berlaku": tarif_baru_berlaku,
            "id_promo": active_promo["id_promo"] if active_promo else None,
            "nama_promo": active_promo["nama_promo"] if active_promo else None,
            "promo_doi_start": str(active_promo.get("doi_start") or "")[:10] if active_promo else "",
            "promo_doi_end": str(active_promo.get("doi_end") or "")[:10] if active_promo else "",
            "persentase_diskon": diskon_pct,
            "persentase_ppn": ppn_pct,
            "tarif_psc_dpp_baru": tarif_psc_baru,
            "tarif_psc_dpp_lama": tarif_psc_lama,
            "tarif_counter_dpp": tarif_counter,
            "tarif_cucs_dpp": tarif_cucs,
            "ppn_mult_psc": (1.0 + ppn_pct / 100.0) if is_kena_ppn_psc else 1.0,
            "ppn_mult_counter": (1.0 + ppn_pct / 100.0) if is_kena_ppn_counter else 1.0,
            "ppn_mult_cucs": (1.0 + ppn_pct / 100.0) if is_kena_ppn_cucs else 1.0,
        }

    @staticmethod
    def classify_offload_passenger(pax_item, pricing):
        doi_promo = str(pax_item.get("doi_promo") or "").strip()[:10]
        doi_lama = str(pax_item.get("doi_lama") or "").strip()[:10]

        kategori_promo = "NORMAL"
        id_promo = None
        if doi_promo and pricing.get("id_promo"):
            d_start = pricing.get("promo_doi_start") or ""
            d_end = pricing.get("promo_doi_end") or ""
            in_start = (not d_start) or (doi_promo >= d_start)
            in_end = (not d_end) or (doi_promo <= d_end)
            if in_start and in_end:
                kategori_promo = "DISKON"
                id_promo = pricing.get("id_promo")

        kategori_tarif = "BARU"
        id_tarif_lama = None
        if doi_lama and pricing.get("id_tarif_lama"):
            baru_mulai = pricing.get("tarif_baru_berlaku") or ""
            if not baru_mulai or doi_lama < baru_mulai:
                kategori_tarif = "LAMA"
                id_tarif_lama = pricing.get("id_tarif_lama")

        status_offload = str(pax_item.get("status_offload") or "DITAGIH").strip().upper()
        if status_offload not in ("DITAGIH", "ADJUSTMENT"):
            status_offload = "DITAGIH"

        return {
            "id_offload_passenger": pax_item.get("id_offload_passenger"),
            "nama_pax": (pax_item.get("nama_pax") or "").strip(),
            "seat": (pax_item.get("seat") or "-").strip() or "-",
            "pnr": (pax_item.get("pnr") or "").strip().upper(),
            "doi_promo": doi_promo or None,
            "doi_lama": doi_lama or None,
            "id_promo": id_promo,
            "id_tarif_lama": id_tarif_lama,
            "kategori_promo": kategori_promo,
            "kategori_tarif": kategori_tarif,
            "status_offload": status_offload,
        }

    @staticmethod
    def parse_offload_passengers_json(raw_json, pricing):
        if not raw_json:
            return []
        if isinstance(raw_json, list):
            items = raw_json
        else:
            try:
                items = json.loads(raw_json)
            except Exception:
                return []
        if not isinstance(items, list):
            return []

        result = []
        for it in items:
            if not isinstance(it, dict):
                continue
            nama = (it.get("nama_pax") or "").strip()
            if not nama:
                continue
            result.append(Pjp2uModel.classify_offload_passenger(it, pricing))
        return result

    @staticmethod
    def summarize_offload_passengers(pax_list):
        ditagih = [p for p in (pax_list or []) if (p.get("status_offload") or "DITAGIH").upper() == "DITAGIH"]
        return {
            "offload_count": len(ditagih),
            "promo_count": sum(1 for p in ditagih if (p.get("kategori_promo") or "").upper() == "DISKON"),
            "lama_count": sum(1 for p in ditagih if (p.get("kategori_tarif") or "").upper() == "LAMA"),
        }

    @staticmethod
    def compute_metrics(form_data, pricing, is_adjustment=False):
        adult = Pjp2uModel._to_int(form_data.get("adult"), 0)
        child = Pjp2uModel._to_int(form_data.get("child"), 0)
        infant = Pjp2uModel._to_int(form_data.get("infant"), 0)
        transit = Pjp2uModel._to_int(form_data.get("transit"), 0)
        crew = Pjp2uModel._to_int(form_data.get("crew"), 0)
        offload = Pjp2uModel._to_int(form_data.get("offload"), 0)
        pax_diskon = Pjp2uModel._to_int(form_data.get("diskon"), 0)
        pax_lama = Pjp2uModel._to_int(form_data.get("lama"), 0)
        seat = Pjp2uModel._to_int(form_data.get("seat"), 0)

        jumlah_pax = adult + child + infant
        total_prod_psc = adult + child + offload - transit
        total_prod_counter = adult + child + infant + offload
        total_prod_cucs = adult + child + infant + offload

        if not is_adjustment:
            if total_prod_psc < 0:
                raise ValueError("Total Produksi PSC tidak boleh bernilai negatif pada transaksi Normal.")
            if pax_diskon < 0 or pax_diskon > total_prod_psc:
                raise ValueError("Jumlah Pax Diskon tidak boleh melebihi Total Produksi PSC.")
            if pax_lama < 0 or pax_lama > total_prod_psc:
                raise ValueError("Jumlah Pax Tarif Lama tidak boleh melebihi Total Produksi PSC.")

        pax_normal = total_prod_psc - pax_diskon
        pax_baru = total_prod_psc - pax_lama

        persentase_payingpax = round((total_prod_psc / seat) * 100.0, 2) if seat > 0 else 0.0
        persentase_lf = round((jumlah_pax / seat) * 100.0, 2) if seat > 0 else 0.0

        t_baru = pricing["tarif_psc_dpp_baru"]
        t_lama = pricing["tarif_psc_dpp_lama"]
        disc_factor = 1.0 - (pricing["persentase_diskon"] / 100.0)
        ppn_psc = pricing["ppn_mult_psc"]
        ppn_cnt = pricing["ppn_mult_counter"]
        ppn_cucs = pricing["ppn_mult_cucs"]

        pend_psc_normal_dpp = pax_normal * t_baru
        pend_psc_diskon_dpp = pax_diskon * t_baru * disc_factor
        pend_psc_normal = round(pend_psc_normal_dpp * ppn_psc, 2)
        pend_psc_diskon = round(pend_psc_diskon_dpp * ppn_psc, 2)

        pend_psc_baru = round((pax_baru * t_baru) * ppn_psc, 2)
        pend_psc_lama = round((pax_lama * t_lama) * ppn_psc, 2)

        selisih_lama_dpp = pax_lama * (t_lama - t_baru)
        pend_psc_dpp = round(pend_psc_normal_dpp + pend_psc_diskon_dpp + selisih_lama_dpp, 2)
        pend_psc = round(pend_psc_dpp * ppn_psc, 2)

        pend_counter = round((total_prod_counter * pricing["tarif_counter_dpp"]) * ppn_cnt, 2)
        pend_cucs = round((total_prod_cucs * pricing["tarif_cucs_dpp"]) * ppn_cucs, 2)

        return {
            "adult": adult,
            "child": child,
            "infant": infant,
            "transit": transit,
            "crew": crew,
            "jumlah_pax": jumlah_pax,
            "offload": offload,
            "pax_diskon": pax_diskon,
            "pax_normal": pax_normal,
            "pax_baru": pax_baru,
            "pax_lama": pax_lama,
            "total_prod_psc": total_prod_psc,
            "total_prod_counter": total_prod_counter,
            "total_prod_cucs": total_prod_cucs,
            "seat": seat,
            "persentase_payingpax": persentase_payingpax,
            "persentase_lf": persentase_lf,
            "pend_psc_dpp": pend_psc_dpp,
            "pend_psc": pend_psc,
            "pend_psc_diskon": pend_psc_diskon,
            "pend_psc_normal": pend_psc_normal,
            "pend_psc_lama": pend_psc_lama,
            "pend_psc_baru": pend_psc_baru,
            "pend_counter": pend_counter,
            "pend_cucs": pend_cucs,
        }

    @staticmethod
    def get_offload_passengers_by_pjp2u_ids(pjp2u_ids):
        clean_ids = [int(x) for x in (pjp2u_ids or []) if x is not None]
        if not clean_ids:
            return {}
        res = (
            app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE)
            .select("*")
            .in_("id_pjp2u", list(set(clean_ids)))
            .is_("deleted_at", "null")
            .order("id_offload_passenger", desc=False)
            .execute()
        )
        grouped = {}
        for item in (res.data or []):
            grouped.setdefault(item["id_pjp2u"], []).append(item)
        return grouped

    @staticmethod
    def sync_offload_passengers(id_pjp2u, cabang, pax_list, actor=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        existing_res = (
            app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE)
            .select("id_offload_passenger")
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )
        existing_ids = {row["id_offload_passenger"] for row in (existing_res.data or [])}
        kept_ids = set()

        for p in (pax_list or []):
            row_payload = {
                "id_pjp2u": id_pjp2u,
                "cabang": (cabang or "").strip().upper(),
                "nama_pax": p["nama_pax"],
                "seat": p.get("seat") or "-",
                "pnr": p.get("pnr") or "",
                "doi_promo": p.get("doi_promo"),
                "doi_lama": p.get("doi_lama"),
                "id_promo": p.get("id_promo"),
                "id_tarif_lama": p.get("id_tarif_lama"),
                "kategori_promo": p.get("kategori_promo") or "NORMAL",
                "kategori_tarif": p.get("kategori_tarif") or "BARU",
                "status_offload": p.get("status_offload") or "DITAGIH",
                "updated_at": now_utc,
                "updated_by": actor,
            }
            existing_id = p.get("id_offload_passenger")
            if existing_id and int(existing_id) in existing_ids:
                eid = int(existing_id)
                app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE).update(row_payload).eq("id_offload_passenger", eid).execute()
                kept_ids.add(eid)
            else:
                row_payload["created_at"] = now_utc
                row_payload["created_by"] = actor
                row_payload["deleted_at"] = None
                row_payload["deleted_by"] = None
                ins = app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE).insert(row_payload).execute()
                if ins.data:
                    kept_ids.add(ins.data[0]["id_offload_passenger"])

        removed_ids = existing_ids - kept_ids
        for rid in removed_ids:
            app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE).update({
                "deleted_at": now_utc,
                "deleted_by": actor,
            }).eq("id_offload_passenger", rid).execute()

    @staticmethod
    def _enrich_rows(rows):
        if not rows:
            return []
        al_res = (
            app.supabase.table(Pjp2uModel.AIRLINE_TABLE)
            .select("id_airline, airline_name, code_2, code_3, logo")
            .execute()
        )
        al_map = {a["id_airline"]: a for a in (al_res.data or [])}

        cnt_res = (
            app.supabase.table(Pjp2uModel.TARIF_TABLE)
            .select("kode_cabang, sub_kategori, mata_uang, berlaku_mulai")
            .eq("jenis_jasa", "COUNTER")
            .is_("delete_at", "null")
            .order("berlaku_mulai", desc=True)
            .execute()
        )
        cnt_tarifs = cnt_res.data or []

        def _get_cnt_currency(cabang, scope_reg, scope_route, tanggal):
            cab = (cabang or "").strip().upper()
            eff_scope = Pjp2uModel.resolve_effective_tariff_scope(scope_reg, scope_route).strip().lower()
            tgl = str(tanggal or "")[:10]
            matched = [
                t for t in cnt_tarifs
                if (t.get("kode_cabang") or "").strip().upper() == cab
                and (t.get("sub_kategori") or "").strip().lower() == eff_scope
                and (not t.get("berlaku_mulai") or str(t.get("berlaku_mulai"))[:10] <= tgl)
            ]
            if not matched:
                matched = [
                    t for t in cnt_tarifs
                    if (t.get("kode_cabang") or "").strip().upper() == cab
                    and (t.get("sub_kategori") or "").strip().lower() == "domestik"
                    and (not t.get("berlaku_mulai") or str(t.get("berlaku_mulai"))[:10] <= tgl)
                ]
            return (matched[0].get("mata_uang") or "IDR").strip().upper() if matched else "IDR"

        all_ids = [r["id_pjp2u"] for r in rows if r.get("id_pjp2u")]
        parent_ids = [r["parent_id_pjp2u"] for r in rows if r.get("parent_id_pjp2u")]
        offload_lookup_ids = list(set(all_ids + parent_ids))
        offload_pax_map = Pjp2uModel.get_offload_passengers_by_pjp2u_ids(offload_lookup_ids)

        parent_map = {}
        if parent_ids:
            p_res = (
                app.supabase.table(Pjp2uModel.TABLE)
                .select("*")
                .in_("id_pjp2u", list(set(parent_ids)))
                .execute()
            )
            parent_map = {p["id_pjp2u"]: p for p in (p_res.data or [])}

        for r in rows:
            al = al_map.get(r.get("operator")) or {}
            r["airline_name"] = al.get("airline_name") or "Unknown Airline"
            r["airline_code_2"] = al.get("code_2") or "-"
            r["airline_logo"] = al.get("logo")
            parent_obj = parent_map.get(r.get("parent_id_pjp2u"))
            r["parent_record"] = parent_obj

            own_pax = offload_pax_map.get(r.get("id_pjp2u"), [])
            parent_pax = offload_pax_map.get(r.get("parent_id_pjp2u"), []) if r.get("parent_id_pjp2u") else []
            r["offload_passengers"] = own_pax if own_pax else parent_pax

            r["mata_uang_counter"] = _get_cnt_currency(
                r.get("cabang"),
                r.get("scope_registration"),
                r.get("scope_route"),
                r.get("tanggal"),
            )
        return rows

    @staticmethod
    def get_list(
        allowed_cabangs=None,
        filter_cabang=None,
        date_from=None,
        date_to=None,
        airline_ids=None,
        include_deleted=False,
    ):
        query = app.supabase.table(Pjp2uModel.TABLE).select("*")

        if allowed_cabangs is not None:
            if len(allowed_cabangs) == 0:
                return []
            query = query.in_("cabang", allowed_cabangs)

        if filter_cabang:
            query = query.eq("cabang", filter_cabang.strip().upper())

        if airline_ids is not None:
            if len(airline_ids) == 0:
                return []
            query = query.in_("operator", [int(x) for x in airline_ids])

        if date_from:
            query = query.gte("tanggal", date_from)
        if date_to:
            query = query.lte("tanggal", date_to)

        if not include_deleted:
            query = query.is_("deleted_at", "null")

        res = (
            query.order("tanggal", desc=True)
            .order("boarding_time", desc=False)
            .order("id_pjp2u", desc=True)
            .execute()
        )
        return Pjp2uModel._enrich_rows(res.data or [])

    @staticmethod
    def get_by_id(id_pjp2u, include_deleted=False):
        query = app.supabase.table(Pjp2uModel.TABLE).select("*").eq("id_pjp2u", id_pjp2u)
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        if not res.data:
            return None
        return Pjp2uModel._enrich_rows(res.data)[0]

    @staticmethod
    def create(payload, created_by=None, offload_passengers=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload["created_at"] = now_utc
        payload["created_by"] = created_by
        payload["updated_at"] = now_utc
        payload["updated_by"] = created_by
        payload["deleted_at"] = None
        payload["deleted_by"] = None
        res = app.supabase.table(Pjp2uModel.TABLE).insert(payload).execute()
        if not res.data:
            raise ValueError("Gagal menyimpan data operasional PJP2U.")
        created_row = res.data[0]
        if offload_passengers is not None:
            Pjp2uModel.sync_offload_passengers(
                id_pjp2u=created_row["id_pjp2u"],
                cabang=created_row.get("cabang"),
                pax_list=offload_passengers,
                actor=created_by,
            )
        return created_row

    @staticmethod
    def update(id_pjp2u, payload, updated_by=None, offload_passengers=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload["updated_at"] = now_utc
        payload["updated_by"] = updated_by
        res = (
            app.supabase.table(Pjp2uModel.TABLE)
            .update(payload)
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )
        if offload_passengers is not None:
            cab = payload.get("cabang") or (res.data[0].get("cabang") if res.data else "")
            Pjp2uModel.sync_offload_passengers(
                id_pjp2u=id_pjp2u,
                cabang=cab,
                pax_list=offload_passengers,
                actor=updated_by,
            )
        return res

    @staticmethod
    def delete(id_pjp2u, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        app.supabase.table(Pjp2uModel.OFFLOAD_PAX_TABLE).update({
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }).eq("id_pjp2u", id_pjp2u).is_("deleted_at", "null").execute()

        return (
            app.supabase.table(Pjp2uModel.TABLE)
            .update({"deleted_at": now_utc, "deleted_by": deleted_by})
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_pjp2u, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(Pjp2uModel.TABLE)
            .update({
                "deleted_at": None,
                "deleted_by": None,
                "updated_at": now_utc,
                "updated_by": restored_by,
            })
            .eq("id_pjp2u", id_pjp2u)
            .execute()
        )

    @staticmethod
    def _ensure_token(id_pjp2u, col_name, jenis_ba):
        res = (
            app.supabase.table(Pjp2uModel.TABLE)
            .select(col_name)
            .eq("id_pjp2u", id_pjp2u)
            .limit(1)
            .execute()
        )
        existing_val = (res.data[0].get(col_name) if res.data else None) or ""
        return existing_val.strip() or generate_ba_token(jenis_ba)

    @staticmethod
    def verify_normal(id_pjp2u, verifier_name, verifier_jabatan):
        now_utc = datetime.now(timezone.utc).isoformat()
        token_normal = Pjp2uModel._ensure_token(id_pjp2u, "ba_token_normal", "NORMAL")
        return (
            app.supabase.table(Pjp2uModel.TABLE)
            .update({
                "name_verification": verifier_name,
                "jabatan_verification": verifier_jabatan,
                "verification_at": now_utc,
                "ba_token_normal": token_normal,
            })
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def verify_offload(id_pjp2u, verifier_name, verifier_jabatan):
        now_utc = datetime.now(timezone.utc).isoformat()
        token_offload = Pjp2uModel._ensure_token(id_pjp2u, "ba_token_offload", "OFFLOAD")
        return (
            app.supabase.table(Pjp2uModel.TABLE)
            .update({
                "name_verification_offload": verifier_name,
                "jabatan_verification_offload": verifier_jabatan,
                "verification_offload_at": now_utc,
                "ba_token_offload": token_offload,
            })
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def verify_adjustment(id_pjp2u, verifier_name, verifier_jabatan, doc_mode, nomor_surat=None, file_url=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        token_adj = Pjp2uModel._ensure_token(id_pjp2u, "ba_token_adjustment", "ADJUSTMENT")
        clean_mode = (doc_mode or "AUTO").strip().upper()
        final_file_url = file_url if clean_mode == "UPLOAD" else None

        return (
            app.supabase.table(Pjp2uModel.TABLE)
            .update({
                "name_verification_adjustment": verifier_name,
                "jabatan_verification_adjustment": verifier_jabatan,
                "verification_adjustment_at": now_utc,
                "adjustment_doc_mode": clean_mode,
                "adjustment_nomor_surat": nomor_surat if clean_mode == "AUTO" else None,
                "adjustment_file_url": final_file_url,
                "ba_token_adjustment": token_adj,
            })
            .eq("id_pjp2u", id_pjp2u)
            .is_("deleted_at", "null")
            .execute()
        )