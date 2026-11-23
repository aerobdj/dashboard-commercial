import json
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
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
    def get_by_email(email, include_deleted=False):
        if not email:
            return None
        query = (
            app.supabase.table(AirlineUserModel.TABLE)
            .select("*")
            .ilike("email", email.strip())
        )
        if not include_deleted:
            query = query.is_("delete_at", "null")
        res = query.limit(1).execute()
        return res.data[0] if res.data else None

    @staticmethod
    def verify_login(email, password):
        """
        Mengecek keberadaan email (delete_at is null), status aktif (True/False), dan password.
        Mengembalikan tuple: (user_dict, error_message)
        """
        if not email or not password:
            return None, "Email dan password wajib diisi."

        user = AirlineUserModel.get_by_email(email.strip(), include_deleted=False)
        if not user:
            return None, None  # Tidak ditemukan di tabel airline_users

        if not bool(user.get("status", False)):
            return None, "Akun maskapai Anda sedang dinonaktifkan. Hubungi administrator InJourney Airports."

        if check_password_hash(user["password"], password) or user["password"] == password:
            return user, None

        return None, "Email atau password salah!"

    @staticmethod
    def get_authorized_airlines(raw_airlines, allowed_cabang_codes=None):
        """
        Mengurai kolom 'airlines' (format JSON list seperti ["2", "1"], [2, 1], atau JSON string '["2","1"]')
        lalu mencocokkannya dengan tabel 'airlines_data' berdasarkan id_airline dan allowed_cabang_codes.
        """
        if not raw_airlines:
            return []

        parsed_list = raw_airlines
        if isinstance(raw_airlines, str):
            raw_str = raw_airlines.strip()
            if raw_str.startswith("["):
                try:
                    parsed_list = json.loads(raw_str)
                except Exception:
                    parsed_list = []
            else:
                parsed_list = [x.strip() for x in raw_str.split(",") if x.strip()]

        airline_ids = []
        if isinstance(parsed_list, list):
            for x in parsed_list:
                val = str(x).strip()
                if val.isdigit():
                    airline_ids.append(int(val))

        if not airline_ids:
            return []

        query = app.supabase.table("airline_data").select("*").in_("id_airline", airline_ids)
        res = query.execute()
        airlines_list = res.data or []

        # Filter berdasarkan cabang jika tabel airlines_data memiliki kolom kode_cabang
        if allowed_cabang_codes is not None:
            allowed_set = set(allowed_cabang_codes)
            filtered = []
            for item in airlines_list:
                item_cabang = item.get("kode_cabang")
                if not item_cabang or item_cabang in allowed_set:
                    filtered.append(item)
            return filtered

        return airlines_list

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

    @staticmethod
    def update_profile(id_airlineusers, nama_lengkap, email, jabatan, password=None, updated_by=None):
        now_utc = datetime.now(timezone.utc).isoformat()
        payload = {
            "nama_lengkap": nama_lengkap.strip(),
            "email": email.strip().lower(),
            "jabatan": jabatan.strip(),
            "updated_by": updated_by,
            "update_at": now_utc,
        }
        if password and password.strip():
            payload["password"] = generate_password_hash(password.strip())

        return (
            app.supabase.table(AirlineUserModel.TABLE)
            .update(payload)
            .eq("id_airlineusers", id_airlineusers)
            .is_("delete_at", "null")
            .execute()
        )