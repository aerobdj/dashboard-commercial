from datetime import datetime, timezone
import app


class AirlineModel:
    TABLE = "airline_data"

    @staticmethod
    def get_all(include_deleted=False):
        query = app.supabase.table(AirlineModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.order("airline_name", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_airline, include_deleted=False):
        query = app.supabase.table(AirlineModel.TABLE).select("*").eq("id_airline", id_airline)
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        code_2 = (data.get("code_2") or "").strip().upper() or None
        code_3 = (data.get("code_3") or "").strip().upper() or None
        payload = {
            "airline_name": data["airline_name"].strip(),
            "code_2": code_2,
            "code_3": code_3,
            "logo": data.get("logo"),
            "created_by": created_by,
            "created_at": now_utc,
            "updated_by": created_by,
            "update_at": now_utc,
            "delete_by": None,
            "delete_at": None,
        }
        return app.supabase.table(AirlineModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_airline, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        code_2 = (data.get("code_2") or "").strip().upper() or None
        code_3 = (data.get("code_3") or "").strip().upper() or None
        payload = {
            "airline_name": data["airline_name"].strip(),
            "code_2": code_2,
            "code_3": code_3,
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        if data.get("logo"):
            payload["logo"] = data["logo"]

        return (
            app.supabase.table(AirlineModel.TABLE)
            .update(payload)
            .eq("id_airline", id_airline)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_airline, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "delete_by": deleted_by,
            "delete_at": now_utc,
        }
        return (
            app.supabase.table(AirlineModel.TABLE)
            .update(payload)
            .eq("id_airline", id_airline)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_airline, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "delete_by": None,
            "delete_at": None,
            "updated_by": restored_by,
            "update_at": now_utc,
        }
        return (
            app.supabase.table(AirlineModel.TABLE)
            .update(payload)
            .eq("id_airline", id_airline)
            .execute()
        )