from datetime import datetime, timezone
import re
import app


class AirlineRegistrationModel:
    TABLE = "airline_registration"

    @staticmethod
    def format_registration(raw_reg):
        """
        Merapikan nomor registrasi pesawat menjadi uppercase rapat tanpa tanda hubung/spasi.
        Contoh: 'pk-gpf' -> 'PKGPF', 'pk gpf' -> 'PKGPF', 'n977jh' -> 'N977JH'.
        """
        return re.sub(r"[^A-Z0-9]", "", (raw_reg or "").upper())

    @staticmethod
    def _enrich_records(records):
        if not records:
            return []
        airlines_res = app.supabase.table("airline_data").select("*").execute()
        airline_map = {a["id_airline"]: a for a in (airlines_res.data or [])}

        enriched = []
        for row in records:
            row["airline"] = airline_map.get(row.get("id_airline")) or {}
            enriched.append(row)
        return enriched

    @staticmethod
    def get_all(include_deleted=False):
        query = app.supabase.table(AirlineRegistrationModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.order("registration", desc=False).execute()
        return AirlineRegistrationModel._enrich_records(res.data or [])

    @staticmethod
    def get_by_id(id_registration, include_deleted=False):
        query = (
            app.supabase.table(AirlineRegistrationModel.TABLE)
            .select("*")
            .eq("id_registration", id_registration)
        )
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        if not res.data:
            return None
        return AirlineRegistrationModel._enrich_records(res.data)[0]

    @staticmethod
    def exists(registration, exclude_id=None):
        clean_reg = AirlineRegistrationModel.format_registration(registration)
        query = (
            app.supabase.table(AirlineRegistrationModel.TABLE)
            .select("id_registration")
            .ilike("registration", clean_reg)
            .is_("deleted_at", "null")
        )
        if exclude_id is not None:
            query = query.neq("id_registration", exclude_id)
        res = query.limit(1).execute()
        return bool(res.data)

    @staticmethod
    def _normalize_scope(raw_scope, registration):
        val = (raw_scope or "").strip().capitalize()
        if val in ("Domestik", "Internasional"):
            return val
        return "Domestik" if registration.startswith("PK") else "Internasional"

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_reg = AirlineRegistrationModel.format_registration(data["registration"])
        scope = AirlineRegistrationModel._normalize_scope(data.get("scope"), clean_reg)

        payload = {
            "registration": clean_reg,
            "id_airline": int(data["id_airline"]),
            "type_flight": " ".join((data.get("type_flight") or "").split()).upper(),
            "seat": int(data.get("seat") or 0),
            "scope": scope,
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
        }
        return app.supabase.table(AirlineRegistrationModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_registration, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        clean_reg = AirlineRegistrationModel.format_registration(data["registration"])
        scope = AirlineRegistrationModel._normalize_scope(data.get("scope"), clean_reg)

        payload = {
            "registration": clean_reg,
            "id_airline": int(data["id_airline"]),
            "type_flight": " ".join((data.get("type_flight") or "").split()).upper(),
            "seat": int(data.get("seat") or 0),
            "scope": scope,
            "updated_at": now_utc,
            "updated_by": updated_by,
        }
        return (
            app.supabase.table(AirlineRegistrationModel.TABLE)
            .update(payload)
            .eq("id_registration", id_registration)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_registration, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }
        return (
            app.supabase.table(AirlineRegistrationModel.TABLE)
            .update(payload)
            .eq("id_registration", id_registration)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_registration, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": None,
            "deleted_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(AirlineRegistrationModel.TABLE)
            .update(payload)
            .eq("id_registration", id_registration)
            .execute()
        )