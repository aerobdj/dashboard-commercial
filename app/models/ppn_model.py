from datetime import datetime, timezone
import app


class PpnModel:
    TABLE = "master_ppn"

    @staticmethod
    def get_all(include_deleted=False):
        query = app.supabase.table(PpnModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.order("berlaku_mulai", desc=True).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_ppn, include_deleted=False):
        query = app.supabase.table(PpnModel.TABLE).select("*").eq("id_ppn", id_ppn)
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def get_active_rate_for_date(target_date):
        """Ambil tarif PPN yang berlaku pada tanggal tertentu (berlaku_mulai <= target_date)."""
        res = (
            app.supabase.table(PpnModel.TABLE)
            .select("*")
            .is_("delete_at", "null")
            .lte("berlaku_mulai", str(target_date))
            .order("berlaku_mulai", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "nama_ppn": (data.get("nama_ppn") or "").strip(),
            "persentase": float(data.get("persentase") or 0),
            "berlaku_mulai": data["berlaku_mulai"],
            "keterangan": (data.get("keterangan") or "").strip() or None,
            "created_by": created_by,
            "created_at": now_utc,
            "updated_by": created_by,
            "update_at": now_utc,
            "delete_by": None,
            "delete_at": None,
        }
        return app.supabase.table(PpnModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_ppn, data, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "nama_ppn": (data.get("nama_ppn") or "").strip(),
            "persentase": float(data.get("persentase") or 0),
            "berlaku_mulai": data["berlaku_mulai"],
            "keterangan": (data.get("keterangan") or "").strip() or None,
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        return (
            app.supabase.table(PpnModel.TABLE)
            .update(payload)
            .eq("id_ppn", id_ppn)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def delete(id_ppn, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(PpnModel.TABLE)
            .update({"delete_by": deleted_by, "delete_at": now_utc})
            .eq("id_ppn", id_ppn)
            .is_("delete_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_ppn, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        return (
            app.supabase.table(PpnModel.TABLE)
            .update({
                "delete_by": None,
                "delete_at": None,
                "updated_by": restored_by,
                "update_at": now_utc,
            })
            .eq("id_ppn", id_ppn)
            .execute()
        )