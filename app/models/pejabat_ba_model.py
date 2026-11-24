from datetime import datetime, timezone
import app


class PejabatBaModel:
    TABLE = "aeronautika_pejabat_ba"
    CABANG_TABLE = "cabang"
    VALID_JENIS = ("NORMAL", "OFFLOAD", "ADJUSTMENT")

    @staticmethod
    def _now_iso():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _clean_date(val):
        if not val:
            return None
        s = str(val).strip()[:10]
        return s if s else None

    @staticmethod
    def _validate_kode_cabang(kode_cabang):
        cab = (kode_cabang or "").strip().upper()
        if not cab:
            raise ValueError("Kode cabang wajib diisi.")
        res = (
            app.supabase.table(PejabatBaModel.CABANG_TABLE)
            .select("kode_cabang")
            .eq("kode_cabang", cab)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if not res.data:
            raise ValueError(f"Kode cabang '{cab}' tidak ditemukan pada master cabang.")
        return cab

    @staticmethod
    def get_cabang_list(allowed_cabangs=None):
        q = (
            app.supabase.table(PejabatBaModel.CABANG_TABLE)
            .select("kode_cabang, nama_cabang")
            .is_("deleted_at", "null")
            .order("kode_cabang", desc=False)
        )
        if allowed_cabangs is not None:
            if not allowed_cabangs:
                return []
            q = q.in_("kode_cabang", allowed_cabangs)
        res = q.execute()
        return res.data or []

    @staticmethod
    def get_list(allowed_cabangs=None, filter_cabang=None, filter_jenis=None, include_deleted=False):
        q = (
            app.supabase.table(PejabatBaModel.TABLE)
            .select("*")
            .order("kode_cabang", desc=False)
            .order("jenis_ba", desc=False)
            .order("berlaku_mulai", desc=True)
        )
        if not include_deleted:
            q = q.is_("delete_at", "null")

        if filter_cabang:
            q = q.eq("kode_cabang", filter_cabang.strip().upper())
        elif allowed_cabangs is not None:
            if not allowed_cabangs:
                return []
            q = q.in_("kode_cabang", allowed_cabangs)

        if filter_jenis and filter_jenis.strip().upper() in PejabatBaModel.VALID_JENIS:
            q = q.eq("jenis_ba", filter_jenis.strip().upper())

        rows = q.execute().data or []

        cab_res = (
            app.supabase.table(PejabatBaModel.CABANG_TABLE)
            .select("kode_cabang, nama_cabang")
            .execute()
        )
        cab_map = {c["kode_cabang"]: c.get("nama_cabang") for c in (cab_res.data or [])}

        for r in rows:
            r["nama_cabang"] = cab_map.get(r.get("kode_cabang")) or r.get("kode_cabang")
        return rows

    @staticmethod
    def get_by_id(id_pejabat):
        res = (
            app.supabase.table(PejabatBaModel.TABLE)
            .select("*")
            .eq("id_pejabat", id_pejabat)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    @staticmethod
    def resolve_pejabat(kode_cabang, jenis_ba, tanggal_ref):
        """
        Mencari pejabat penanggung jawab Pihak Pertama yang menjabat pada tanggal_ref
        untuk cabang dan jenis_ba ('NORMAL', 'OFFLOAD', 'ADJUSTMENT').
        """
        cab = (kode_cabang or "").strip().upper()
        jenis = (jenis_ba or "NORMAL").strip().upper()
        tgl = PejabatBaModel._clean_date(tanggal_ref)

        res = (
            app.supabase.table(PejabatBaModel.TABLE)
            .select("*")
            .eq("kode_cabang", cab)
            .eq("jenis_ba", jenis)
            .eq("is_active", True)
            .is_("delete_at", "null")
            .order("berlaku_mulai", desc=True)
            .execute()
        )
        candidates = res.data or []
        if not tgl:
            return candidates[0] if candidates else None

        for p in candidates:
            mulai = PejabatBaModel._clean_date(p.get("berlaku_mulai"))
            selesai = PejabatBaModel._clean_date(p.get("berlaku_selesai"))
            if mulai and tgl < mulai:
                continue
            if selesai and tgl > selesai:
                continue
            return p

        return candidates[0] if candidates else None

    @staticmethod
    def create(form_data, actor):
        cab = PejabatBaModel._validate_kode_cabang(form_data.get("kode_cabang"))
        jenis = (form_data.get("jenis_ba") or "").strip().upper()
        nama = (form_data.get("nama_pejabat") or "").strip()
        jabatan = (form_data.get("jabatan") or "").strip()
        nipp = (form_data.get("nipp") or "").strip() or None
        mulai = PejabatBaModel._clean_date(form_data.get("berlaku_mulai"))
        selesai = PejabatBaModel._clean_date(form_data.get("berlaku_selesai"))
        is_active = str(form_data.get("is_active", "1")) in ("1", "true", "True", "on")

        if not cab or jenis not in PejabatBaModel.VALID_JENIS or not nama or not jabatan or not mulai:
            raise ValueError("Cabang, Jenis BA, Nama Pejabat, Jabatan, dan Berlaku Mulai wajib diisi.")
        if selesai and selesai < mulai:
            raise ValueError("Tanggal Berlaku Selesai tidak boleh lebih awal dari Berlaku Mulai.")

        now_str = PejabatBaModel._now_iso()
        payload = {
            "kode_cabang": cab,
            "jenis_ba": jenis,
            "nama_pejabat": nama,
            "jabatan": jabatan,
            "nipp": nipp,
            "berlaku_mulai": mulai,
            "berlaku_selesai": selesai,
            "is_active": is_active,
            "created_at": now_str,
            "created_by": actor,
            "updated_at": now_str,
            "updated_by": actor,
        }
        res = app.supabase.table(PejabatBaModel.TABLE).insert(payload).execute()
        return res.data[0] if res.data else payload

    @staticmethod
    def update(id_pejabat, form_data, actor):
        existing = PejabatBaModel.get_by_id(id_pejabat)
        if not existing:
            raise ValueError("Data pejabat BA tidak ditemukan.")

        cab = PejabatBaModel._validate_kode_cabang(form_data.get("kode_cabang"))
        jenis = (form_data.get("jenis_ba") or existing.get("jenis_ba") or "").strip().upper()
        nama = (form_data.get("nama_pejabat") or "").strip()
        jabatan = (form_data.get("jabatan") or "").strip()
        nipp = (form_data.get("nipp") or "").strip() or None
        mulai = PejabatBaModel._clean_date(form_data.get("berlaku_mulai"))
        selesai = PejabatBaModel._clean_date(form_data.get("berlaku_selesai"))
        is_active = str(form_data.get("is_active", "0")) in ("1", "true", "True", "on")

        if not cab or jenis not in PejabatBaModel.VALID_JENIS or not nama or not jabatan or not mulai:
            raise ValueError("Cabang, Jenis BA, Nama Pejabat, Jabatan, dan Berlaku Mulai wajib diisi.")
        if selesai and selesai < mulai:
            raise ValueError("Tanggal Berlaku Selesai tidak boleh lebih awal dari Berlaku Mulai.")

        payload = {
            "kode_cabang": cab,
            "jenis_ba": jenis,
            "nama_pejabat": nama,
            "jabatan": jabatan,
            "nipp": nipp,
            "berlaku_mulai": mulai,
            "berlaku_selesai": selesai,
            "is_active": is_active,
            "updated_at": PejabatBaModel._now_iso(),
            "updated_by": actor,
        }
        res = (
            app.supabase.table(PejabatBaModel.TABLE)
            .update(payload)
            .eq("id_pejabat", id_pejabat)
            .execute()
        )
        return res.data[0] if res.data else payload

    @staticmethod
    def soft_delete(id_pejabat, actor):
        now_str = PejabatBaModel._now_iso()
        app.supabase.table(PejabatBaModel.TABLE).update({
            "is_active": False,
            "delete_at": now_str,
            "delete_by": actor,
            "updated_at": now_str,
            "updated_by": actor,
        }).eq("id_pejabat", id_pejabat).execute()