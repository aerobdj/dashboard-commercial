from datetime import datetime, timezone
import app


class CoaModel:
    TABLE = "coa_pendapatan"

    @staticmethod
    def get_all(include_deleted=False):
        query = app.supabase.table(CoaModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.order("kode_account", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_coa, include_deleted=False):
        query = app.supabase.table(CoaModel.TABLE).select("*").eq("id_coa", id_coa)
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def get_by_kode(kode_account, include_deleted=False):
        if not kode_account:
            return None
        query = app.supabase.table(CoaModel.TABLE).select("*").eq("kode_account", kode_account.strip())
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def create(kode_account, klasifikasi, sub_klasifikasi, deskripsi_coa, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "kode_account": kode_account.strip(),
            "klasifikasi": klasifikasi.strip(),
            "sub_klasifikasi": sub_klasifikasi.strip(),
            "deskripsi_coa": deskripsi_coa.strip(),
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
        }
        return app.supabase.table(CoaModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_coa, kode_account, klasifikasi, sub_klasifikasi, deskripsi_coa, updated_by=None):
        payload = {
            "kode_account": kode_account.strip(),
            "klasifikasi": klasifikasi.strip(),
            "sub_klasifikasi": sub_klasifikasi.strip(),
            "deskripsi_coa": deskripsi_coa.strip(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        return (
            app.supabase.table(CoaModel.TABLE)
            .update(payload)
            .eq("id_coa", id_coa)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_coa, deleted_by=None):
        """Soft delete: mengisi deleted_at dan deleted_by tanpa menghapus record di database."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }
        return (
            app.supabase.table(CoaModel.TABLE)
            .update(payload)
            .eq("id_coa", id_coa)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_coa, restored_by=None):
        """Mengaktifkan kembali COA yang sudah di-soft delete (khusus superadmin)."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": None,
            "deleted_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(CoaModel.TABLE)
            .update(payload)
            .eq("id_coa", id_coa)
            .execute()
        )