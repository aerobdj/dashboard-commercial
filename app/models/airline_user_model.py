from datetime import datetime, timezone
from werkzeug.security import generate_password_hash
import app


class AirlineUserModel:
    TABLE = "airline_users"

    @staticmethod
    def get_all(include_deleted=False, allowed_cabang_codes=None):
        query = app.supabase.table(AirlineUserModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("delete_at", "null")
        if allowed_cabang_codes is not None:
            if not allowed_cabang_codes:
                return []
            query = query.in_("kode_cabang", allowed_cabang_codes)
        res = query.order("nama_lengkap", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_airlineusers, include_deleted=False):
        query = (
            app.supabase.table(AirlineUserModel.TABLE)
            .select("*")
            .eq("id_airlineusers", id_airlineusers)
        )
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def email_exists(email, exclude_id=None):
        query = (
            app.supabase.table(AirlineUserModel.TABLE)
            .select("id_airlineusers")
            .ilike("email", email.strip())
            .is_("delete_at", "null")
        )
        if exclude_id is not None:
            query = query.neq("id_airlineusers", exclude_id)
        res = query.limit(1).execute()
        return bool(res.data)

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        role = (data.get("role") or "user").strip().lower()
        if role not in ("user", "admin"):
            role = "user"

        airline_ids = [int(x) for x in (data.get("airlines") or []) if str(x).isdigit()]
        is_active = bool(data.get("status", True))

        payload = {
            "email": data["email"].strip().lower(),
            "password": generate_password_hash(data["password"]),
            "nama_lengkap": data["nama_lengkap"].strip(),
            "jabatan": data["jabatan"].strip(),
            "role": role,
            "status": is_active,
            "kode_cabang": data["kode_cabang"].strip().upper(),
            "airlines": airline_ids,
            "created_by": created_by,
            "created_at": now_utc,
            "updated_by": created_by,
            "update_at": now_utc,
            "delete_by": None,
            "delete_at": None,
        }
        return app.supabase.table(AirlineUserModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_airlineusers, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        role = (data.get("role") or "user").strip().lower()
        if role not in ("user", "admin"):
            role = "user"

        airline_ids = [int(x) for x in (data.get("airlines") or []) if str(x).isdigit()]
        is_active = bool(data.get("status", True))

        payload = {
            "email": data["email"].strip().lower(),
            "nama_lengkap": data["nama_lengkap"].strip(),
            "jabatan": data["jabatan"].strip(),
            "role": role,
            "status": is_active,
            "kode_cabang": data["kode_cabang"].strip().upper(),
            "airlines": airline_ids,
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        if data.get("password"):
            payload["password"] = generate_password_hash(data["password"])

        return (
            app.supabase.table(AirlineUserModel.TABLE)
            .update(payload)
            .eq("id_airlineusers", id_airlineusers)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def toggle_status(id_airlineusers, new_status, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": bool(new_status),
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        return (
            app.supabase.table(AirlineUserModel.TABLE)
            .update(payload)
            .eq("id_airlineusers", id_airlineusers)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_airlineusers, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": False,
            "delete_by": deleted_by,
            "delete_at": now_utc,
        }
        return (
            app.supabase.table(AirlineUserModel.TABLE)
            .update(payload)
            .eq("id_airlineusers", id_airlineusers)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_airlineusers, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "status": True,
            "delete_by": None,
            "delete_at": None,
            "updated_by": restored_by,
            "update_at": now_utc,
        }
        return (
            app.supabase.table(AirlineUserModel.TABLE)
            .update(payload)
            .eq("id_airlineusers", id_airlineusers)
            .execute()
        )