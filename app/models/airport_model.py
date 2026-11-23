from datetime import datetime, timezone
import app


class AirportModel:
    TABLE = "airport"

    @staticmethod
    def get_all(include_deleted=False):
        query = app.supabase.table(AirportModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.order("iata", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_airport, include_deleted=False):
        query = (
            app.supabase.table(AirportModel.TABLE)
            .select("*")
            .eq("id_airport", id_airport)
        )
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def iata_exists(iata, exclude_id=None):
        query = (
            app.supabase.table(AirportModel.TABLE)
            .select("id_airport")
            .ilike("iata", iata.strip())
            .is_("deleted_at", "null")
        )
        if exclude_id is not None:
            query = query.neq("id_airport", exclude_id)
        res = query.limit(1).execute()
        return bool(res.data)

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        scope = (data.get("scope") or "Domestik").strip()
        if scope not in ("Domestik", "Internasional"):
            scope = "Domestik"

        payload = {
            "iata": data["iata"].strip().upper(),
            "icao": (data.get("icao") or "").strip().upper() or None,
            "airport_name": data["airport_name"].strip(),
            "city": data["city"].strip(),
            "province": (data.get("province") or "").strip() or None,
            "country": (data.get("country") or "Indonesia").strip(),
            "scope": scope,
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "status": bool(data.get("status", True)),
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "delete_by": None,
        }
        return app.supabase.table(AirportModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_airport, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        scope = (data.get("scope") or "Domestik").strip()
        if scope not in ("Domestik", "Internasional"):
            scope = "Domestik"

        payload = {
            "iata": data["iata"].strip().upper(),
            "icao": (data.get("icao") or "").strip().upper() or None,
            "airport_name": data["airport_name"].strip(),
            "city": data["city"].strip(),
            "province": (data.get("province") or "").strip() or None,
            "country": (data.get("country") or "Indonesia").strip(),
            "scope": scope,
            "latitude": float(data["latitude"]),
            "longitude": float(data["longitude"]),
            "status": bool(data.get("status", True)),
            "updated_at": now_utc,
            "updated_by": updated_by,
        }
        return (
            app.supabase.table(AirportModel.TABLE)
            .update(payload)
            .eq("id_airport", id_airport)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_airport, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": False,
            "deleted_at": now_utc,
            "delete_by": deleted_by,
        }
        return (
            app.supabase.table(AirportModel.TABLE)
            .update(payload)
            .eq("id_airport", id_airport)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_airport, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": True,
            "deleted_at": None,
            "delete_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(AirportModel.TABLE)
            .update(payload)
            .eq("id_airport", id_airport)
            .execute()
        )