from datetime import datetime, timezone
import re
import app


class FlightNumberModel:
    TABLE = "flight_numbers"

    @staticmethod
    def format_flight_number(raw_fn, airline_code=None):
        """
        Menghasilkan format seragam 'GA 535' dari input apa pun:
        - '535' (dengan airline GA) -> 'GA 535'
        - 'GA535'                   -> 'GA 535'
        - 'GA 535'                  -> 'GA 535'
        """
        text = " ".join((raw_fn or "").split()).upper()
        code = (airline_code or "").strip().upper()

        # Jika user hanya mengetik angka (misal '535' atau '535A') dan airline_code tersedia
        if code and re.match(r"^[0-9]+[A-Z]?$", text):
            return f"{code} {text}"

        # Jika user mengetik kode maskapai tanpa spasi (misal 'GA535') atau banyak spasi ('GA   535')
        match = re.match(r"^([A-Z0-9]{2})\s*([0-9]+[A-Z]?)$", text)
        if match:
            return f"{match.group(1)} {match.group(2)}"

        return text

    @staticmethod
    def _enrich_records(records):
        if not records:
            return []

        airlines_res = app.supabase.table("airline_data").select("*").execute()
        airports_res = app.supabase.table("airport").select("*").execute()

        airline_map = {a["id_airline"]: a for a in (airlines_res.data or [])}
        airport_map = {ap["id_airport"]: ap for ap in (airports_res.data or [])}

        enriched = []
        for row in records:
            row["airline"] = airline_map.get(row.get("id_airline")) or {}
            row["origin"] = airport_map.get(row.get("origin_airport_id")) or {}
            row["destination"] = airport_map.get(row.get("destination_airport_id")) or {}
            enriched.append(row)
        return enriched

    @staticmethod
    def get_all(include_deleted=False, allowed_cabang_codes=None):
        query = app.supabase.table(FlightNumberModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")

        if allowed_cabang_codes is not None:
            if not allowed_cabang_codes:
                return []
            query = query.in_("kode_cabang", allowed_cabang_codes)

        res = query.order("flight_number", desc=False).execute()
        return FlightNumberModel._enrich_records(res.data or [])

    @staticmethod
    def get_by_id(id_flightnumber, include_deleted=False):
        query = (
            app.supabase.table(FlightNumberModel.TABLE)
            .select("*")
            .eq("id_flightnumber", id_flightnumber)
        )
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        if not res.data:
            return None
        return FlightNumberModel._enrich_records(res.data)[0]

    @staticmethod
    def lookup_by_flight_number(flight_number, kode_cabang=None):
        clean_fn = FlightNumberModel.format_flight_number(flight_number)
        if not clean_fn:
            return None

        query = (
            app.supabase.table(FlightNumberModel.TABLE)
            .select("*")
            .ilike("flight_number", clean_fn)
            .eq("status", True)
            .is_("deleted_at", "null")
        )
        if kode_cabang:
            query = query.eq("kode_cabang", kode_cabang.strip().upper())

        res = query.limit(1).execute()
        if not res.data:
            return None
        return FlightNumberModel._enrich_records(res.data)[0]

    @staticmethod
    def exists(flight_number, kode_cabang, exclude_id=None):
        clean_fn = FlightNumberModel.format_flight_number(flight_number)
        query = (
            app.supabase.table(FlightNumberModel.TABLE)
            .select("id_flightnumber")
            .ilike("flight_number", clean_fn)
            .eq("kode_cabang", kode_cabang.strip().upper())
            .is_("deleted_at", "null")
        )
        if exclude_id is not None:
            query = query.neq("id_flightnumber", exclude_id)
        res = query.limit(1).execute()
        return bool(res.data)

    @staticmethod
    def _resolve_scope(origin_id, destination_id):
        orig_res = app.supabase.table("airport").select("country, scope").eq("id_airport", origin_id).limit(1).execute()
        dest_res = app.supabase.table("airport").select("country, scope").eq("id_airport", destination_id).limit(1).execute()
        orig = orig_res.data[0] if orig_res.data else {}
        dest = dest_res.data[0] if dest_res.data else {}

        is_intl = (
            (orig.get("country", "").strip().lower() != dest.get("country", "").strip().lower())
            or orig.get("scope") == "Internasional"
            or dest.get("scope") == "Internasional"
        )
        return "Internasional" if is_intl else "Domestik"

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_fn = FlightNumberModel.format_flight_number(data["flight_number"])
        origin_id = int(data["origin_airport_id"])
        dest_id = int(data["destination_airport_id"])
        scope = FlightNumberModel._resolve_scope(origin_id, dest_id)
        al_res = app.supabase.table("airline_data").select("code_2, code_3").eq("id_airline", int(data["id_airline"])).limit(1).execute()
        al_row = al_res.data[0] if al_res.data else {}
        airline_code = al_row.get("code_2") or al_row.get("code_3") or ""

        clean_fn = FlightNumberModel.format_flight_number(data["flight_number"], airline_code=airline_code)

        payload = {
            "id_airline": int(data["id_airline"]),
            "flight_number": clean_fn,
            "origin_airport_id": origin_id,
            "destination_airport_id": dest_id,
            "scope": scope,
            "kode_cabang": data["kode_cabang"].strip().upper(),
            "status": bool(data.get("status", True)),
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
        }
        return app.supabase.table(FlightNumberModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_flightnumber, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_fn = FlightNumberModel.format_flight_number(data["flight_number"])
        origin_id = int(data["origin_airport_id"])
        dest_id = int(data["destination_airport_id"])
        scope = FlightNumberModel._resolve_scope(origin_id, dest_id)
        al_res = app.supabase.table("airline_data").select("code_2, code_3").eq("id_airline", int(data["id_airline"])).limit(1).execute()
        al_row = al_res.data[0] if al_res.data else {}
        airline_code = al_row.get("code_2") or al_row.get("code_3") or ""

        clean_fn = FlightNumberModel.format_flight_number(data["flight_number"], airline_code=airline_code)

        payload = {
            "id_airline": int(data["id_airline"]),
            "flight_number": clean_fn,
            "origin_airport_id": origin_id,
            "destination_airport_id": dest_id,
            "scope": scope,
            "kode_cabang": data["kode_cabang"].strip().upper(),
            "status": bool(data.get("status", True)),
            "updated_at": now_utc,
            "updated_by": updated_by,
        }
        return (
            app.supabase.table(FlightNumberModel.TABLE)
            .update(payload)
            .eq("id_flightnumber", id_flightnumber)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_flightnumber, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": False,
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }
        return (
            app.supabase.table(FlightNumberModel.TABLE)
            .update(payload)
            .eq("id_flightnumber", id_flightnumber)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_flightnumber, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": True,
            "deleted_at": None,
            "deleted_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(FlightNumberModel.TABLE)
            .update(payload)
            .eq("id_flightnumber", id_flightnumber)
            .execute()
        )