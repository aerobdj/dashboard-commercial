import ast
import json
from collections import deque
from functools import wraps
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, abort, current_app
import app
from app.models.pjp2u_model import Pjp2uModel
from app.models.pejabat_ba_model import PejabatBaModel
from app.utils.ba_verification import (
    compute_ba_integrity_hash,
    format_tanggal_indonesia,
    format_kalimat_pembuka_ba,
    build_nomor_ba,
    build_qr_image_url,
    generate_ba_token,
    parse_date_obj,
)

ba_doc_bp = Blueprint("ba_doc", __name__)

TOKEN_COL_MAP = {
    "NORMAL": "ba_token_normal",
    "OFFLOAD": "ba_token_offload",
    "ADJUSTMENT": "ba_token_adjustment",
}

INTERNAL_ROLES = {"SUPERADMIN", "ADMIN", "PENGAWAS", "USER", "HO", "HEAD_OFFICE", "REGIONAL", "CABANG"}


def _current_user() -> dict:
    for key in ("airline_user", "airline_session", "user", "auth_user"):
        val = session.get(key)
        if isinstance(val, dict) and val:
            merged = dict(val)
            if key in ("airline_user", "airline_session"):
                merged.setdefault("user_type", "AIRLINE")
                merged.setdefault("role", "AIRLINE")
            for extra_key in ("id_airlineusers", "airlines", "airline_ids", "allowed_airlines", "role", "user_type", "kode_cabang", "tipe_unit"):
                if extra_key not in merged and session.get(extra_key) is not None:
                    merged[extra_key] = session.get(extra_key)
            return merged

    if any(session.get(k) is not None for k in ("id_airlineusers", "airlines", "airline_ids", "allowed_airlines", "role", "kode_cabang")):
        return {
            "id_airlineusers": session.get("id_airlineusers"),
            "airlines": session.get("airlines"),
            "airline_ids": session.get("airline_ids"),
            "allowed_airlines": session.get("allowed_airlines"),
            "role": session.get("role"),
            "user_type": session.get("user_type"),
            "kode_cabang": session.get("kode_cabang"),
            "tipe_unit": session.get("tipe_unit"),
            "username": session.get("username"),
        }

    return {}


def _is_authenticated() -> bool:
    return bool(_current_user())


def login_required_ba(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not _is_authenticated():
            flash("Silakan login terlebih dahulu untuk mengakses dokumen Berita Acara.", "warning")
            return redirect(url_for("auth.login"))
        return fn(*args, **kwargs)
    return wrapper


def _extract_dict_airline_tokens(item: dict) -> set[str]:
    tokens = set()
    target_keys = {
        "id_airline", "airline_id", "id",
        "kode_airline", "code_2", "code_3",
        "iata_code", "icao_code",
        "nama_airline", "airline_name",
    }
    for k, v in item.items():
        if v is None or v == "":
            continue
        if str(k).strip().lower() in target_keys:
            if isinstance(v, (int, float)):
                tokens.add(str(int(v)).strip())
            else:
                tokens.add(str(v).strip().upper())
    return tokens


def _parse_airline_ids(raw_val) -> set[str]:
    if raw_val is None or raw_val == "":
        return set()

    if isinstance(raw_val, dict):
        return _extract_dict_airline_tokens(raw_val)

    if isinstance(raw_val, (list, tuple, set)):
        out = set()
        for x in raw_val:
            if isinstance(x, dict):
                out.update(_extract_dict_airline_tokens(x))
            elif x is not None and str(x).strip():
                out.update(_parse_airline_ids(x))
        return out

    if isinstance(raw_val, (int, float)):
        return {str(int(raw_val)).strip()}

    if isinstance(raw_val, str):
        s = raw_val.strip()
        if not s:
            return set()
        for parser in (json.loads, ast.literal_eval):
            try:
                parsed = parser(s)
                if isinstance(parsed, (dict, list, tuple, set)):
                    return _parse_airline_ids(parsed)
                if parsed is not None:
                    return {str(parsed).strip().upper().strip('"').strip("'")}
            except Exception:
                continue
        return {
            part.strip().upper().strip('"').strip("'").lstrip("[").rstrip("]")
            for part in s.split(",")
            if part.strip().strip('"').strip("'").lstrip("[").rstrip("]")
        }

    return {str(raw_val).strip().upper()}


def _get_allowed_branches_from_db(user: dict) -> tuple[bool, set[str]]:
    """
    Mengembalikan (is_all_branches, allowed_kode_cabang_set) berdasarkan tabel `cabang`
    (`kode_cabang`, `nama_cabang`, `tipe_unit`, `parent_kode`).
    """
    res = app.supabase.table("cabang").select("kode_cabang, nama_cabang, tipe_unit, parent_kode").execute()
    rows = res.data or []

    user_cabang = str(user.get("kode_cabang") or user.get("cabang") or "").strip().upper()
    tipe_unit_user = str(user.get("tipe_unit") or "").strip().upper()

    unit_map = {}
    children_map = {}
    for r in rows:
        kc = str(r.get("kode_cabang") or "").strip().upper()
        pk = str(r.get("parent_kode") or "").strip().upper()
        tu = str(r.get("tipe_unit") or "").strip().upper()
        if kc:
            unit_map[kc] = {"kode_cabang": kc, "tipe_unit": tu, "parent_kode": pk}
            if pk:
                children_map.setdefault(pk, []).append(kc)

    if not tipe_unit_user and user_cabang in unit_map:
        tipe_unit_user = unit_map[user_cabang]["tipe_unit"]

    if tipe_unit_user in {"HO", "HEAD_OFFICE", "HEAD OFFICE", "KANTOR PUSAT", "PUSAT"}:
        return True, set(unit_map.keys())

    if not user_cabang:
        return False, set()

    allowed = {user_cabang}
    queue = deque([user_cabang])
    while queue:
        curr = queue.popleft()
        for child in children_map.get(curr, []):
            if child not in allowed:
                allowed.add(child)
                queue.append(child)

    return False, allowed


def _get_allowed_airline_identifiers(user: dict) -> set[str]:
    """
    Mengambil daftar `id_airline` (dan atribut terkait di `airline_data`) milik user
    dari `airline_users.airlines` / session (mendukung list ID maupun list of dict).
    """
    selected_ids = set()
    for src_key in ("airlines", "airline_ids", "allowed_airlines", "airline_code"):
        if user.get(src_key) is not None:
            selected_ids.update(_parse_airline_ids(user.get(src_key)))

    if not selected_ids:
        try:
            au_query = app.supabase.table("airline_users").select("*")
            user_id = (
                user.get("id_airlineusers")
                or user.get("id_airline_user")
                or user.get("id")
                or user.get("id_user")
                or user.get("kd_user")
            )
            username = user.get("username") or user.get("user_name")
            email = user.get("email")

            if user_id is not None:
                au_res = au_query.eq("id_airlineusers", user_id).limit(1).execute()
            elif email:
                au_res = au_query.eq("email", email).limit(1).execute()
            elif username:
                au_res = au_query.eq("username", username).limit(1).execute()
            else:
                au_res = None

            if au_res and au_res.data:
                selected_ids.update(_parse_airline_ids(au_res.data[0].get("airlines")))
        except Exception as exc:
            current_app.logger.warning("Gagal mengambil airline_users: %s", exc)

    if not selected_ids:
        return set()

    allowed_ids = set(selected_ids)

    try:
        ad_res = app.supabase.table("airline_data").select("*").execute()
        for ad in (ad_res.data or []):
            pk_val = str(ad.get("id_airline") or "").strip().upper()
            kode_val = str(ad.get("kode_airline") or ad.get("code_2") or "").strip().upper()
            nama_val = str(ad.get("nama_airline") or ad.get("airline_name") or "").strip().upper()
            if (pk_val and pk_val in selected_ids) or (kode_val and kode_val in selected_ids) or (nama_val and nama_val in selected_ids):
                for extra_col in ("id_airline", "kode_airline", "iata_code", "icao_code", "nama_airline", "airline_name", "code_2"):
                    extra_val = str(ad.get(extra_col) or "").strip().upper()
                    if extra_val:
                        allowed_ids.add(extra_val)
    except Exception as exc:
        current_app.logger.warning("Gagal mengambil airline_data: %s", exc)

    return allowed_ids


def _can_access_ba_record(row: dict, user: dict) -> bool:
    if not user or not row:
        current_app.logger.warning(
            "BA 403: user=%s, row_id=%s",
            bool(user),
            row.get("id_pjp2u") if isinstance(row, dict) else None,
        )
        return False

    user_type = str(user.get("user_type") or user.get("account_type") or "").strip().upper()
    role = str(user.get("role") or "").strip().upper()
    row_cabang = str(row.get("cabang") or row.get("kode_cabang") or "").strip().upper()

    is_airline_user = (
        user_type in {"AIRLINE", "AIRLINE_USER", "MASKAPAI"}
        or role in {"AIRLINE", "MASKAPAI"}
        or bool(user.get("id_airlineusers") or user.get("airlines") or user.get("allowed_airlines"))
    )

    if is_airline_user:
        allowed_airlines = _get_allowed_airline_identifiers(user)
        row_airlines = {
            str(row.get("id_airline") or "").strip().upper(),
            str(row.get("airline_id") or "").strip().upper(),
            str(row.get("operator") or "").strip().upper(),
            str(row.get("kode_airline") or "").strip().upper(),
            str(row.get("iata_code") or "").strip().upper(),
            str(row.get("airline_name") or "").strip().upper(),
        } - {""}
        matched = bool(row_airlines & allowed_airlines)
        if not matched:
            current_app.logger.warning(
                "BA 403 Airline mismatch: id_pjp2u=%s, row_airlines=%s, allowed_airlines=%s, user_keys=%s",
                row.get("id_pjp2u"),
                sorted(row_airlines),
                sorted(allowed_airlines),
                list(user.keys()),
            )
        return matched

    if role in INTERNAL_ROLES or user_type in {"INTERNAL", "STAFF", "EMPLOYEE"} or role:
        is_all, allowed_branches = _get_allowed_branches_from_db(user)
        if is_all:
            return True
        matched = bool(row_cabang) and row_cabang in allowed_branches
        if not matched:
            current_app.logger.warning(
                "BA 403 Internal mismatch: id_pjp2u=%s, row_cabang=%s, allowed_branches=%s, role=%s",
                row.get("id_pjp2u"),
                row_cabang,
                sorted(allowed_branches),
                role,
            )
        return matched

    return False


def _find_record_by_token(token: str):
    clean_token = (token or "").strip()
    if not clean_token:
        return None, None

    for jenis, col in TOKEN_COL_MAP.items():
        res = (
            app.supabase.table(Pjp2uModel.TABLE)
            .select("*")
            .eq(col, clean_token)
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
        )
        if res.data:
            enriched = Pjp2uModel._enrich_rows(res.data)
            return enriched[0], jenis

    return None, None


def _resolve_record_by_id_and_jenis(id_pjp2u: int, jenis_ba: str):
    jenis = (jenis_ba or "NORMAL").strip().upper()
    if jenis not in TOKEN_COL_MAP:
        return None, None, None

    rows = Pjp2uModel._enrich_rows(
        app.supabase.table(Pjp2uModel.TABLE)
        .select("*")
        .eq("id_pjp2u", id_pjp2u)
        .is_("deleted_at", "null")
        .limit(1)
        .execute()
        .data or []
    )
    if not rows:
        return None, None, None

    row = rows[0]
    if jenis == "NORMAL" and not row.get("verification_at"):
        return None, None, None
    if jenis == "OFFLOAD" and not row.get("verification_offload_at"):
        return None, None, None
    if jenis == "ADJUSTMENT" and not row.get("verification_adjustment_at"):
        return None, None, None

    token_col = TOKEN_COL_MAP[jenis]
    token = row.get(token_col)
    if not token:
        token = generate_ba_token(jenis)
        app.supabase.table(Pjp2uModel.TABLE).update({token_col: token}).eq("id_pjp2u", id_pjp2u).execute()
        row[token_col] = token

    return row, jenis, token


def _build_ba_context(row: dict, jenis_ba: str, token: str):
    jenis = (jenis_ba or "NORMAL").upper()
    cab_code = (row.get("cabang") or "").strip().upper()

    cab_res = (
        app.supabase.table("cabang")
        .select("*")
        .eq("kode_cabang", cab_code)
        .limit(1)
        .execute()
    )
    cab_info = cab_res.data[0] if cab_res.data else {
        "kode_cabang": cab_code,
        "nama_cabang": cab_code,
        "kota": cab_code,
    }

    aircraft_type = "-"
    reg_code = (row.get("registration") or "").strip()
    if reg_code:
        reg_res = (
            app.supabase.table("airline_registration")
            .select("type_flight, scope, seat")
            .eq("registration", reg_code)
            .limit(1)
            .execute()
        )
        if reg_res.data:
            aircraft_type = reg_res.data[0].get("type_flight") or "-"

    tgl_ref = row.get("tanggal")
    if jenis == "OFFLOAD" and row.get("verification_offload_at"):
        tgl_ref = str(row.get("verification_offload_at"))[:10]
    elif jenis == "ADJUSTMENT" and row.get("verification_adjustment_at"):
        tgl_ref = str(row.get("verification_adjustment_at"))[:10]

    pejabat_1 = PejabatBaModel.resolve_pejabat(cab_code, jenis, row.get("tanggal") or tgl_ref) or {
        "nama_pejabat": "Pejabat Aero Commercial",
        "jabatan": "Aero Commercial Officer",
        "nipp": None,
    }

    if jenis == "OFFLOAD":
        pihak_2_nama = row.get("name_verification_offload") or row.get("name_verification") or "-"
        pihak_2_jabatan = row.get("jabatan_verification_offload") or row.get("jabatan_verification") or "Airline Representative"
        ver_at = row.get("verification_offload_at")
    elif jenis == "ADJUSTMENT":
        pihak_2_nama = row.get("name_verification_adjustment") or "-"
        pihak_2_jabatan = row.get("jabatan_verification_adjustment") or "Station Manager"
        ver_at = row.get("verification_adjustment_at")
    else:
        pihak_2_nama = row.get("name_verification") or "-"
        pihak_2_jabatan = row.get("jabatan_verification") or "Airline Representative"
        ver_at = row.get("verification_at")

    tarif_res = (
        app.supabase.table("tarif_aeronautika")
        .select("berlaku_mulai")
        .eq("kode_cabang", cab_code)
        .eq("jenis_jasa", "PJP2U")
        .is_("delete_at", "null")
        .order("berlaku_mulai", desc=True)
        .limit(1)
        .execute()
    )
    tgl_batas_tarif = "16 Jul 2022"
    if tarif_res.data and tarif_res.data[0].get("berlaku_mulai"):
        dt_tarif = parse_date_obj(tarif_res.data[0]["berlaku_mulai"])
        if dt_tarif:
            tgl_batas_tarif = dt_tarif.strftime("%d %b %Y")

    verify_url = url_for("ba_doc.verify_public", token=token, _external=True)
    qr_url = build_qr_image_url(verify_url, size=136)
    integrity_hash = compute_ba_integrity_hash(row, jenis, token)

    adult = int(row.get("adult") or 0)
    child = int(row.get("child") or 0)
    infant = int(row.get("infant") or 0)
    transit = int(row.get("transit") or 0)
    offload = int(row.get("offload") or 0)
    total_pax_bayar_line = adult + child
    total_prod_psc = int(row.get("total_prod_psc") or (adult + child + offload - transit))
    total_prod_counter = int(row.get("total_prod_counter") or (adult + child + infant + offload))

    return {
        "row": row,
        "jenis_ba": jenis,
        "token": token,
        "nomor_ba": build_nomor_ba(row, jenis),
        "cab_info": cab_info,
        "aircraft_type": aircraft_type,
        "kalimat_pembuka": format_kalimat_pembuka_ba(ver_at or row.get("tanggal")),
        "tanggal_penerbangan_id": format_tanggal_indonesia(row.get("tanggal")),
        "tanggal_ttd_id": format_tanggal_indonesia(ver_at or row.get("tanggal")),
        "tgl_batas_tarif": tgl_batas_tarif,
        "pejabat_1": pejabat_1,
        "pihak_2_nama": pihak_2_nama,
        "pihak_2_jabatan": pihak_2_jabatan,
        "ver_at": ver_at,
        "verify_url": verify_url,
        "qr_url": qr_url,
        "integrity_hash": integrity_hash,
        "adult": adult,
        "child": child,
        "infant": infant,
        "transit": transit,
        "offload": offload,
        "total_pax_bayar_line": total_pax_bayar_line,
        "total_prod_psc": total_prod_psc,
        "total_prod_counter": total_prod_counter,
        "pax_lama": int(row.get("pax_lama") or 0),
        "pax_baru": int(row.get("pax_baru") or 0),
    }


@ba_doc_bp.route("/ba/<cabang>/<jenis_ba>/<int:id_pjp2u>")
@login_required_ba
def print_ba(cabang, jenis_ba, id_pjp2u):
    row, jenis, token = _resolve_record_by_id_and_jenis(id_pjp2u, jenis_ba)
    if not row:
        flash("Berita Acara belum tersedia atau data penerbangan belum diverifikasi.", "warning")
        return redirect(request.referrer or "/")

    row_cabang = str(row.get("cabang") or row.get("kode_cabang") or "").strip().upper()
    if (cabang or "").strip().upper() != row_cabang:
        abort(404)

    user = _current_user()
    if not _can_access_ba_record(row, user):
        abort(403)

    ctx = _build_ba_context(row, jenis, token)
    return render_template("aeronautika/report/ba_verifikasi.html", **ctx)


@ba_doc_bp.route("/verify-ba/<token>")
@ba_doc_bp.route("/verify-ba")
def verify_public(token=None):
    lookup_token = (token or request.args.get("token") or "").strip()
    if not lookup_token:
        return render_template(
            "aeronautika/report/verify_ba_public.html",
            found=False,
            lookup_token="",
            ctx=None,
        )

    row, jenis = _find_record_by_token(lookup_token)
    if not row:
        return render_template(
            "aeronautika/report/verify_ba_public.html",
            found=False,
            lookup_token=lookup_token,
            ctx=None,
        )

    ctx = _build_ba_context(row, jenis, lookup_token)
    return render_template(
        "aeronautika/report/verify_ba_public.html",
        found=True,
        lookup_token=lookup_token,
        ctx=ctx,
    )