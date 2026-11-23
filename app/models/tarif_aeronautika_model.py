from datetime import datetime, timezone
import app


class TarifAeronautikaModel:
    TABLE = "tarif_aeronautika"
    DETAIL_TABLE = "tarif_aeronautika_detail"
    PROMO_TABLE = "pjp2u_promo"
    AIRLINE_TABLE = "airline_data"

    JENIS_JASA_CHOICES = [
        ("PJP2U", "PJP2U (Passenger Service Charge)"),
        ("PJP4U_LANDING", "PJP4U - Landing"),
        ("PJP4U_PARKING", "PJP4U - Parking / Penempatan"),
        ("PJP4U_SURCHARGE", "PJP4U - Parking Surcharge"),
        ("AVIOBRIDGE", "Aviobridge (Garbarata)"),
        ("COUNTER", "Counter Check-in"),
        ("CUCS", "CUCS (Common Use Check-in System)"),
        ("PJKP2U", "PJKP2U (Kargo & Pos)"),
        ("EXTENDED_ADVANCE", "Extended - Advance Operational"),
    ]

    @staticmethod
    def _enrich_tarifs(records):
        if not records:
            return []

        ids = [r["id_tarif"] for r in records if r.get("id_tarif") is not None]
        details_by_tarif = {}
        if ids:
            det_res = (
                app.supabase.table(TarifAeronautikaModel.DETAIL_TABLE)
                .select("*")
                .in_("id_tarif", ids)
                .order("tahap_ke", desc=False)
                .execute()
            )
            for d in (det_res.data or []):
                details_by_tarif.setdefault(d["id_tarif"], []).append(d)

        coa_res = app.supabase.table("coa_pendapatan").select("*").execute()
        coa_map = {c["kode_account"]: c for c in (coa_res.data or [])}

        for r in records:
            r["details"] = details_by_tarif.get(r["id_tarif"], [])
            r["coa"] = coa_map.get(r.get("kode_account")) or {}
        return records

    @staticmethod
    def get_all(allowed_cabangs=None, include_deleted=False):
        query = app.supabase.table(TarifAeronautikaModel.TABLE).select("*")
        if allowed_cabangs is not None:
            if len(allowed_cabangs) == 0:
                return []
            query = query.in_("kode_cabang", allowed_cabangs)
        if not include_deleted:
            query = query.is_("delete_at", "null")

        res = query.order("berlaku_mulai", desc=True).order("kode_cabang", desc=False).execute()
        return TarifAeronautikaModel._enrich_tarifs(res.data or [])

    @staticmethod
    def get_by_id(id_tarif, include_deleted=False):
        query = (
            app.supabase.table(TarifAeronautikaModel.TABLE)
            .select("*")
            .eq("id_tarif", id_tarif)
        )
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.limit(1).execute()
        if not res.data:
            return None
        return TarifAeronautikaModel._enrich_tarifs(res.data)[0]

    @staticmethod
    def create(header_data, details_list, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "kode_cabang": (header_data.get("kode_cabang") or "").strip().upper(),
            "kode_account": (header_data.get("kode_account") or "").strip(),
            "jenis_jasa": (header_data.get("jenis_jasa") or "").strip().upper(),
            "sub_kategori": (header_data.get("sub_kategori") or "").strip(),
            "terminal": (header_data.get("terminal") or "").strip() or None,
            "mata_uang": (header_data.get("mata_uang") or "IDR").strip().upper(),
            "metode_hitung": (header_data.get("metode_hitung") or "PER_UNIT").strip().upper(),
            "satuan": (header_data.get("satuan") or "Pax").strip(),
            "is_kena_ppn": bool(header_data.get("is_kena_ppn", True)),
            "berlaku_mulai": header_data["berlaku_mulai"],
            "nomor_sk": (header_data.get("nomor_sk") or "").strip() or None,
            "created_by": created_by,
            "created_at": now_utc,
            "updated_by": created_by,
            "update_at": now_utc,
            "delete_by": None,
            "delete_at": None,
        }
        res = app.supabase.table(TarifAeronautikaModel.TABLE).insert(payload).execute()
        if not res.data:
            raise ValueError("Gagal menyimpan header tarif aeronautika.")

        new_id = res.data[0]["id_tarif"]
        detail_rows = []
        for idx, item in enumerate(details_list, start=1):
            detail_rows.append({
                "id_tarif": new_id,
                "tahap_ke": idx,
                "batas_bawah": float(item.get("batas_bawah") or 0),
                "batas_atas": float(item["batas_atas"]) if item.get("batas_atas") not in (None, "") else None,
                "kelipatan_unit": float(item.get("kelipatan_unit") or 1),
                "tarif_dpp": float(item.get("tarif_dpp") or 0),
            })
        if detail_rows:
            app.supabase.table(TarifAeronautikaModel.DETAIL_TABLE).insert(detail_rows).execute()
        return res

    @staticmethod
    def update(id_tarif, header_data, details_list, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "kode_cabang": (header_data.get("kode_cabang") or "").strip().upper(),
            "kode_account": (header_data.get("kode_account") or "").strip(),
            "jenis_jasa": (header_data.get("jenis_jasa") or "").strip().upper(),
            "sub_kategori": (header_data.get("sub_kategori") or "").strip(),
            "terminal": (header_data.get("terminal") or "").strip() or None,
            "mata_uang": (header_data.get("mata_uang") or "IDR").strip().upper(),
            "metode_hitung": (header_data.get("metode_hitung") or "PER_UNIT").strip().upper(),
            "satuan": (header_data.get("satuan") or "Pax").strip(),
            "is_kena_ppn": bool(header_data.get("is_kena_ppn", True)),
            "berlaku_mulai": header_data["berlaku_mulai"],
            "nomor_sk": (header_data.get("nomor_sk") or "").strip() or None,
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        res = (
            app.supabase.table(TarifAeronautikaModel.TABLE)
            .update(payload)
            .eq("id_tarif", id_tarif)
            .is_("delete_at", "null")
            .execute()
        )

        # Replace detail tiers
        app.supabase.table(TarifAeronautikaModel.DETAIL_TABLE).delete().eq("id_tarif", id_tarif).execute()
        detail_rows = []
        for idx, item in enumerate(details_list, start=1):
            detail_rows.append({
                "id_tarif": id_tarif,
                "tahap_ke": idx,
                "batas_bawah": float(item.get("batas_bawah") or 0),
                "batas_atas": float(item["batas_atas"]) if item.get("batas_atas") not in (None, "") else None,
                "kelipatan_unit": float(item.get("kelipatan_unit") or 1),
                "tarif_dpp": float(item.get("tarif_dpp") or 0),
            })
        if detail_rows:
            app.supabase.table(TarifAeronautikaModel.DETAIL_TABLE).insert(detail_rows).execute()
        return res

    @staticmethod
    def delete(id_tarif, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(TarifAeronautikaModel.TABLE)
            .update({"delete_by": deleted_by, "delete_at": now_utc})
            .eq("id_tarif", id_tarif)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_tarif, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(TarifAeronautikaModel.TABLE)
            .update({
                "delete_by": None,
                "delete_at": None,
                "updated_by": restored_by,
                "update_at": now_utc,
            })
            .eq("id_tarif", id_tarif)
            .execute()
        )

    # ================= PROMO / DISKON PJP2U (MULTI-CABANG & AIRLINE) =================
    @staticmethod
    def get_all_airlines():
        res = (
            app.supabase.table(TarifAeronautikaModel.AIRLINE_TABLE)
            .select("id_airline, airline_name, code_2, code_3, logo")
            .is_("delete_at", "null")
            .order("airline_name", desc=False)
            .execute()
        )
        return res.data or []

    @staticmethod
    def get_all_promos(allowed_cabangs=None, include_deleted=False):
        query = app.supabase.table(TarifAeronautikaModel.PROMO_TABLE).select("*")
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.order("flight_date_start", desc=True).execute()
        rows = res.data or []

        # Kumpulkan semua id_airline unik dari seluruh baris promo
        all_airline_ids = set()
        for r in rows:
            raw_al = r.get("id_airline")
            if isinstance(raw_al, list):
                clean_ids = [int(x) for x in raw_al if str(x).isdigit()]
                r["id_airline"] = clean_ids if clean_ids else None
                all_airline_ids.update(clean_ids)
            elif isinstance(raw_al, int):
                r["id_airline"] = [raw_al]
                all_airline_ids.add(raw_al)
            elif isinstance(raw_al, str) and raw_al.strip():
                clean_ids = [int(x.strip()) for x in raw_al.strip("{}").split(",") if x.strip().isdigit()]
                r["id_airline"] = clean_ids if clean_ids else None
                all_airline_ids.update(clean_ids)
            else:
                r["id_airline"] = None

        airline_map = {}
        if all_airline_ids:
            al_res = (
                app.supabase.table(TarifAeronautikaModel.AIRLINE_TABLE)
                .select("id_airline, airline_name, code_2, code_3, logo")
                .in_("id_airline", list(all_airline_ids))
                .execute()
            )
            airline_map = {a["id_airline"]: a for a in (al_res.data or [])}

        for r in rows:
            val = r.get("kode_cabang")
            if isinstance(val, str):
                clean = [c.strip().upper() for c in val.split(",") if c.strip()]
                r["kode_cabang"] = clean if clean else None
            elif isinstance(val, list):
                clean = [str(c).strip().upper() for c in val if str(c).strip()]
                r["kode_cabang"] = clean if clean else None
            else:
                r["kode_cabang"] = None

            # Lampirkan list objek airline yang terpilih pada promo ini
            if r.get("id_airline"):
                r["airlines"] = [airline_map[aid] for aid in r["id_airline"] if aid in airline_map]
            else:
                r["airlines"] = []

        if allowed_cabangs is None:
            return rows

        allowed_set = {c.strip().upper() for c in allowed_cabangs}
        return [
            r for r in rows
            if not r.get("kode_cabang") or bool(set(r["kode_cabang"]) & allowed_set)
        ]

    @staticmethod
    def _normalize_promo_airlines(raw_airlines):
        if not raw_airlines:
            return None
        if isinstance(raw_airlines, (int, str)):
            raw_airlines = [raw_airlines]
        clean_ids = sorted({
            int(str(x).strip())
            for x in raw_airlines
            if str(x).strip().isdigit()
        })
        return clean_ids if clean_ids else None

    @staticmethod
    def _normalize_promo_cabangs(raw_cabs):
        if not raw_cabs:
            return None
        if isinstance(raw_cabs, str):
            raw_cabs = [c.strip() for c in raw_cabs.split(",") if c.strip()]
        clean_cabs = sorted({str(c).strip().upper() for c in raw_cabs if str(c).strip()})
        if not clean_cabs or "__ALL__" in clean_cabs or "ALL" in clean_cabs:
            return None
        return clean_cabs

    @staticmethod
    def _normalize_id_airline(raw_id):
        if raw_id in (None, "", "__ALL__", "ALL"):
            return None
        try:
            return int(raw_id)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def create_promo(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_cabs = TarifAeronautikaModel._normalize_promo_cabangs(data.get("kode_cabang"))
        clean_airline_ids = TarifAeronautikaModel._normalize_promo_airlines(data.get("id_airline"))

        payload = {
            "nama_promo": (data.get("nama_promo") or "").strip(),
            "id_airline": clean_airline_ids,
            "kode_cabang": clean_cabs,
            "sub_kategori": (data.get("sub_kategori") or "Domestik").strip(),
            "persentase_diskon": float(data.get("persentase_diskon") or 50),
            "flight_date_start": data["flight_date_start"],
            "flight_date_end": data["flight_date_end"],
            "doi_start": data.get("doi_start") or None,
            "doi_end": data.get("doi_end") or None,
            "nomor_sk": (data.get("nomor_sk") or "").strip() or None,
            "created_by": created_by,
            "created_at": now_utc,
            "updated_by": created_by,
            "update_at": now_utc,
            "delete_by": None,
            "delete_at": None,
        }
        return app.supabase.table(TarifAeronautikaModel.PROMO_TABLE).insert(payload).execute()

    @staticmethod
    def update_promo(id_promo, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_cabs = TarifAeronautikaModel._normalize_promo_cabangs(data.get("kode_cabang"))
        clean_airline_ids = TarifAeronautikaModel._normalize_promo_airlines(data.get("id_airline"))

        payload = {
            "nama_promo": (data.get("nama_promo") or "").strip(),
            "id_airline": clean_airline_ids,
            "kode_cabang": clean_cabs,
            "sub_kategori": (data.get("sub_kategori") or "Domestik").strip(),
            "persentase_diskon": float(data.get("persentase_diskon") or 50),
            "flight_date_start": data["flight_date_start"],
            "flight_date_end": data["flight_date_end"],
            "doi_start": data.get("doi_start") or None,
            "doi_end": data.get("doi_end") or None,
            "nomor_sk": (data.get("nomor_sk") or "").strip() or None,
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        return (
            app.supabase.table(TarifAeronautikaModel.PROMO_TABLE)
            .update(payload)
            .eq("id_promo", id_promo)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def delete_promo(id_promo, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(TarifAeronautikaModel.PROMO_TABLE)
            .update({"delete_by": deleted_by, "delete_at": now_utc})
            .eq("id_promo", id_promo)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def restore_promo(id_promo, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(TarifAeronautikaModel.PROMO_TABLE)
            .update({
                "delete_by": None,
                "delete_at": None,
                "updated_by": restored_by,
                "update_at": now_utc,
            })
            .eq("id_promo", id_promo)
            .execute()
        )