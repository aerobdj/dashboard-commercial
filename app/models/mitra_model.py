from datetime import datetime, timezone
import app


class MitraModel:
    TABLE = "mitra_usaha"

    @staticmethod
    def get_all(allowed_cabang=None, include_deleted=False):
        query = app.supabase.table(MitraModel.TABLE).select("*")

        if not include_deleted:
            query = query.is_("deleted_at", "null")

        if allowed_cabang is not None:
            if len(allowed_cabang) == 0:
                return []
            query = query.in_("kode_cabang", allowed_cabang)

        res = query.order("id_mitra", desc=True).execute()
        return res.data or []

    @staticmethod
    def get_by_id(id_mitra, include_deleted=False):
        query = app.supabase.table(MitraModel.TABLE).select("*").eq("id_mitra", id_mitra)
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def create(data, created_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "kode_cabang": data.get("kode_cabang") or None,
            "nama_pt": data["nama_pt"].strip(),
            "brand": data["brand"].strip(),
            "type_mitra": data["type_mitra"].strip(),
            "kode_contract": str(data["kode_contract"]).strip(),
            "no_ba": data["no_ba"].strip(),
            "tgl_ba": data["tgl_ba"],
            "kode_ruang": data.get("kode_ruang").strip() if data.get("kode_ruang") else None,
            "luas": float(data["luas"]) if data.get("luas") not in (None, "") else None,
            "tarif_sewa": float(data["tarif_sewa"]) if data.get("tarif_sewa") not in (None, "") else None,
            "pola_kerjasama": data.get("pola_kerjasama", []),
            "type_kerjasama": data["type_kerjasama"].strip(),
            "nominal_kerjasama": float(data["nominal_kerjasama"]) if data.get("nominal_kerjasama") not in (None, "") else None,
            "presentase_rs": float(data["presentase_rs"]) if data.get("presentase_rs") not in (None, "") else None,
            "jangkawaktu_awal": data["jangkawaktu_awal"],
            "jangkawaktu_akhir": data["jangkawaktu_akhir"],
            "status": "Active",
            "file": data.get("file"),
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
        }
        return app.supabase.table(MitraModel.TABLE).insert(payload).execute()

    @staticmethod
    def update(id_mitra, data, updated_by=None):
        payload = {
            "kode_cabang": data.get("kode_cabang") or None,
            "nama_pt": data["nama_pt"].strip(),
            "brand": data["brand"].strip(),
            "type_mitra": data["type_mitra"].strip(),
            "kode_contract": str(data["kode_contract"]).strip(),
            "no_ba": data["no_ba"].strip(),
            "tgl_ba": data["tgl_ba"],
            "kode_ruang": data.get("kode_ruang").strip() if data.get("kode_ruang") else None,
            "luas": float(data["luas"]) if data.get("luas") not in (None, "") else None,
            "tarif_sewa": float(data["tarif_sewa"]) if data.get("tarif_sewa") not in (None, "") else None,
            "pola_kerjasama": data.get("pola_kerjasama", []),
            "type_kerjasama": data["type_kerjasama"].strip(),
            "nominal_kerjasama": float(data["nominal_kerjasama"]) if data.get("nominal_kerjasama") not in (None, "") else None,
            "presentase_rs": float(data["presentase_rs"]) if data.get("presentase_rs") not in (None, "") else None,
            "jangkawaktu_awal": data["jangkawaktu_awal"],
            "jangkawaktu_akhir": data["jangkawaktu_akhir"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        if data.get("file"):
            payload["file"] = data["file"]

        return (
            app.supabase.table(MitraModel.TABLE)
            .update(payload)
            .eq("id_mitra", id_mitra)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def toggle_status(id_mitra, updated_by=None):
        mitra = MitraModel.get_by_id(id_mitra)
        if not mitra:
            return None
        current_status = (mitra.get("status") or "").strip()
        new_status = "Not Active" if current_status == "Active" else "Active"
        app.supabase.table(MitraModel.TABLE).update({
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }).eq("id_mitra", id_mitra).is_("deleted_at", "null").execute()
        return new_status

    @staticmethod
    def delete(id_mitra, deleted_by=None, deleted_reason=None):
        """Soft delete dengan pencatatan actor dan alasan penghapusan."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
            "deleted_reason": deleted_reason.strip() if deleted_reason else None,
        }
        return (
            app.supabase.table(MitraModel.TABLE)
            .update(payload)
            .eq("id_mitra", id_mitra)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(id_mitra, restored_by=None):
        """Mengaktifkan kembali data Mitra Usaha yang terhapus (khusus superadmin)."""
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": None,
            "deleted_by": None,
            "deleted_reason": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(MitraModel.TABLE)
            .update(payload)
            .eq("id_mitra", id_mitra)
            .execute()
        )