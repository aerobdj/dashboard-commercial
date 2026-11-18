from datetime import datetime, timezone
import app


class CabangModel:
    TABLE = "cabang"

    @staticmethod
    def get_all(include_deleted=False, allowed_cabang_codes=None):
        query = app.supabase.table(CabangModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")

        if allowed_cabang_codes is not None:
            codes = list(allowed_cabang_codes)
            if not codes:
                return []
            query = query.in_("kode_cabang", codes)

        res = (
            query.order("tipe_unit", desc=False)
            .order("kode_cabang", desc=False)
            .execute()
        )
        return res.data or []

    @staticmethod
    def get_active():
        res = (
            app.supabase.table(CabangModel.TABLE)
            .select("*")
            .eq("status_aktif", True)
            .is_("deleted_at", "null")
            .order("kode_cabang", desc=False)
            .execute()
        )
        return res.data or []

    @staticmethod
    def get_by_kode(kode_cabang, include_deleted=False):
        if not kode_cabang:
            return None
        query = (
            app.supabase.table(CabangModel.TABLE)
            .select("*")
            .eq("kode_cabang", kode_cabang.strip().upper())
        )
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def get_parents():
        """Mengambil daftar unit aktif yang bisa menjadi induk (HO dan REGIONAL)."""
        res = (
            app.supabase.table(CabangModel.TABLE)
            .select("*")
            .in_("tipe_unit", ["HO", "REGIONAL"])
            .is_("deleted_at", "null")
            .order("kode_cabang", desc=False)
            .execute()
        )
        return res.data or []

    @staticmethod
    def get_allowed_cabang_codes(kode_cabang):
        """
        Menghasilkan daftar kode_cabang yang boleh dilihat oleh user:
        - HO       -> None (semua cabang boleh diakses tanpa filter)
        - REGIONAL -> list kode unit regional itu sendiri + cabang di bawahnya
        - CABANG   -> list berisi 1 kode cabang dirinya sendiri
        """
        unit = CabangModel.get_by_kode(kode_cabang)
        if not unit:
            return []

        tipe = (unit.get("tipe_unit") or "").strip().upper()
        if tipe == "HO":
            return None
        elif tipe in ("REGIONAL", "REGION"):
            res = (
                app.supabase.table(CabangModel.TABLE)
                .select("kode_cabang")
                .eq("parent_kode", unit["kode_cabang"])
                .is_("deleted_at", "null")
                .execute()
            )
            child_codes = [row["kode_cabang"] for row in (res.data or [])]
            return list({unit["kode_cabang"], *child_codes})
        else:
            return [unit["kode_cabang"]]

    @staticmethod
    def has_active_children(kode_cabang):
        """Mengecek apakah masih ada sub-unit aktif yang menginduk ke cabang ini."""
        res = (
            app.supabase.table(CabangModel.TABLE)
            .select("kode_cabang")
            .eq("parent_kode", kode_cabang.strip().upper())
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        return bool(res.data)

    @staticmethod
    def has_active_users(kode_cabang):
        """Mengecek apakah masih ada user aktif yang terdaftar pada cabang ini."""
        res = (
            app.supabase.table("users")
            .select("kd_user")
            .eq("kode_cabang", kode_cabang.strip().upper())
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        return bool(res.data)

    @staticmethod
    def create(kode_cabang, nama_cabang, tipe_unit, parent_kode, kota, status_aktif=True, status=None, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "kode_cabang": kode_cabang.strip().upper(),
            "nama_cabang": nama_cabang.strip(),
            "tipe_unit": tipe_unit,
            "parent_kode": parent_kode.strip().upper() if parent_kode else None,
            "kota": kota.strip() if kota else None,
            "status_aktif": bool(status_aktif),
            "status": status if status is not None else [],
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
        }
        return app.supabase.table(CabangModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(old_kode_cabang, kode_cabang, nama_cabang, tipe_unit, parent_kode, kota, status_aktif=True, status=None, updated_by=None):
        payload = {
            "kode_cabang": kode_cabang.strip().upper(),
            "nama_cabang": nama_cabang.strip(),
            "tipe_unit": tipe_unit,
            "parent_kode": parent_kode.strip().upper() if parent_kode else None,
            "kota": kota.strip() if kota else None,
            "status_aktif": bool(status_aktif),
            "status": status if status is not None else [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        return (
            app.supabase.table(CabangModel.TABLE)
            .update(payload)
            .eq("kode_cabang", old_kode_cabang.strip().upper())
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(kode_cabang, deleted_by=None):
        """Soft delete: mengisi deleted_at dan deleted_by tanpa menghapus record di database."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }
        return (
            app.supabase.table(CabangModel.TABLE)
            .update(payload)
            .eq("kode_cabang", kode_cabang.strip().upper())
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(kode_cabang, restored_by=None):
        """Mengaktifkan kembali cabang yang sudah di-soft delete (khusus superadmin)."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": None,
            "deleted_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(CabangModel.TABLE)
            .update(payload)
            .eq("kode_cabang", kode_cabang.strip().upper())
            .execute()
        )