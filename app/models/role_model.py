from datetime import datetime, timezone
import app


class RoleModel:
    TABLE = "roles"

    @staticmethod
    def get_all():
        res = app.supabase.table(RoleModel.TABLE).select("*").order("id_role", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_role):
        res = app.supabase.table(RoleModel.TABLE).select("*").eq("id_role", id_role).single().execute()
        return res.data

    @staticmethod
    def get_by_name(nama_role):
        if not nama_role:
            return None
        res = app.supabase.table(RoleModel.TABLE).select("*").eq("nama_role", nama_role.strip().lower()).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def create(nama_role, deskripsi, allowed_menus):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "nama_role": nama_role.strip().lower(),
            "deskripsi": deskripsi.strip() if deskripsi else "",
            "allowed_menus": allowed_menus,
            "created_at": now_utc,
            "updated_at": now_utc
        }
        return app.supabase.table(RoleModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_role, nama_role, deskripsi, allowed_menus):
        payload = {
            "nama_role": nama_role.strip().lower(),
            "deskripsi": deskripsi.strip() if deskripsi else "",
            "allowed_menus": allowed_menus,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        return app.supabase.table(RoleModel.TABLE).update(payload).eq("id_role", id_role).execute()

    @staticmethod
    def delete(id_role):
        return app.supabase.table(RoleModel.TABLE).delete().eq("id_role", id_role).execute()