from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import app


class UserModel:
    TABLE = "users"

    @staticmethod
    def get_all(include_deleted=False, allowed_cabang_codes=None):
        """
        allowed_cabang_codes:
        - None: tampilkan semua cabang (untuk HO / superadmin)
        - list/set of kode_cabang: filter hanya cabang-cabang yang diizinkan (untuk REG / Cabang)
        """
        query = app.supabase.table(UserModel.TABLE).select("*")
        if not include_deleted:
            query = query.is_("deleted_at", "null")

        if allowed_cabang_codes is not None:
            codes = list(allowed_cabang_codes)
            if not codes:
                return []
            query = query.in_("kode_cabang", codes)

        res = query.order("kd_user", desc=False).execute()
        return res.data or []

    @staticmethod
    def get_by_id(kd_user, include_deleted=False):
        query = app.supabase.table(UserModel.TABLE).select("*").eq("kd_user", kd_user)
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def get_by_email(email, include_deleted=False):
        if not email:
            return None
        query = app.supabase.table(UserModel.TABLE).select("*").eq("email", email.strip().lower())
        if not include_deleted:
            query = query.is_("deleted_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def verify_login(email, password):
        if not email or not password:
            return None

        user = UserModel.get_by_email(email.strip().lower(), include_deleted=False)
        if not user:
            return None

        if check_password_hash(user["password"], password) or user["password"] == password:
            return user
        return None

    @staticmethod
    def create(email, password, nama_lengkap, jabatan, role, kode_cabang=None, created_by=None):
        hashed_pw = generate_password_hash(password.strip())
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "email": email.strip().lower(),
            "password": hashed_pw,
            "nama_lengkap": nama_lengkap.strip(),
            "jabatan": jabatan.strip(),
            "role": role,
            "kode_cabang": kode_cabang if kode_cabang else None,
            "tgl_lahir": None,
            "phone": None,
            "gender": None,
            "imageprofil": None,
            "created_at": now_utc,
            "created_by": created_by,
            "updated_at": now_utc,
            "updated_by": created_by,
            "deleted_at": None,
            "deleted_by": None,
        }
        return app.supabase.table(UserModel.TABLE).insert(payload).execute()

    @staticmethod
    def update_admin(kd_user, email, nama_lengkap, jabatan, role, kode_cabang=None, password=None, updated_by=None):
        payload = {
            "email": email.strip().lower(),
            "nama_lengkap": nama_lengkap.strip(),
            "jabatan": jabatan.strip(),
            "role": role,
            "kode_cabang": kode_cabang if kode_cabang else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        if password and password.strip():
            payload["password"] = generate_password_hash(password.strip())

        return (
            app.supabase.table(UserModel.TABLE)
            .update(payload)
            .eq("kd_user", kd_user)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def update_profile(kd_user, nama_lengkap, email, phone, tgl_lahir, gender, imageprofil=None, password=None, updated_by=None):
        payload = {
            "nama_lengkap": nama_lengkap.strip(),
            "email": email.strip().lower(),
            "phone": phone.strip() if phone and phone.strip() else None,
            "tgl_lahir": tgl_lahir if tgl_lahir else None,
            "gender": gender if gender else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": updated_by,
        }
        if imageprofil is not None:
            payload["imageprofil"] = imageprofil
        if password and password.strip():
            payload["password"] = generate_password_hash(password.strip())

        return (
            app.supabase.table(UserModel.TABLE)
            .update(payload)
            .eq("kd_user", kd_user)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def delete(kd_user, deleted_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": now_utc,
            "deleted_by": deleted_by,
        }
        return (
            app.supabase.table(UserModel.TABLE)
            .update(payload)
            .eq("kd_user", kd_user)
            .is_("deleted_at", "null")
            .execute()
        )

    @staticmethod
    def restore(kd_user, restored_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "deleted_at": None,
            "deleted_by": None,
            "updated_at": now_utc,
            "updated_by": restored_by,
        }
        return (
            app.supabase.table(UserModel.TABLE)
            .update(payload)
            .eq("kd_user", kd_user)
            .execute()
        )