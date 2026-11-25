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
        return bool(row_airlines & allowed_airlines)

    if role in INTERNAL_ROLES or user_type in {"INTERNAL", "STAFF", "EMPLOYEE"} or role:
        is_all, allowed_branches = _get_allowed_branches_from_db(user)
        if is_all:
            return True
        return bool(row_cabang) and row_cabang in allowed_branches

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


def _resolve_record_by_id_and_jenis(id_pjp2u: int, jenis_ba: str, require_verified: bool = True):
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
    if require_verified:
        if jenis == "NORMAL" and not row.get("verification_at"):
            return None, None, None
        if jenis == "OFFLOAD" and not row.get("verification_offload_at"):
            return None, None, None
        if jenis == "ADJUSTMENT" and not row.get("verification_adjustment_at"):
            return None, None, None

    token_col = TOKEN_COL_MAP[jenis]
    token = row.get(token_col)
    if not token and require_verified:
        token = generate_ba_token(jenis)
        app.supabase.table(Pjp2uModel.TABLE).update({token_col: token}).eq("id_pjp2u", id_pjp2u).execute()
        row[token_col] = token

    return row, jenis, (token or "")


def _extract_offload_passengers(row: dict) -> list[dict]:
    raw = row.get("offload_passengers")
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            try:
                raw = ast.literal_eval(raw)
            except Exception:
                return []
    if not isinstance(raw, list):
        return []

    items = []
    for p in raw:
        if not isinstance(p, dict):
            continue
        status = str(p.get("status_offload") or "DITAGIH").strip().upper()
        if status == "DITAGIH":
            items.append({
                "nama_pax": p.get("nama_pax") or p.get("nama") or "-",
                "seat": p.get("seat") or "-",
                "pnr": p.get("pnr") or p.get("no_tiket") or "-",
                "kategori_promo": (p.get("kategori_promo") or "NORMAL").upper(),
                "kategori_tarif": (p.get("kategori_tarif") or "BARU").upper(),
            })
    return items


def _to_int(val, default=0) -> int:
    try:
        if val is None or val == "":
            return default
        return int(float(str(val).strip()))
    except Exception:
        return default


def _load_parent_record_if_needed(row: dict) -> dict:
    if isinstance(row.get("parent_record"), dict) and row["parent_record"]:
        return row["parent_record"]

    parent_id = row.get("parent_id_pjp2u") or row.get("id_pjp2u_parent") or row.get("ref_id_pjp2u")
    if not parent_id:
        return {}

    try:
        res = (
            app.supabase.table(Pjp2uModel.TABLE)
            .select("*")
            .eq("id_pjp2u", parent_id)
            .limit(1)
            .execute()
        )
        if res.data:
            enriched = Pjp2uModel._enrich_rows(res.data)
            return enriched[0] if enriched else res.data[0]
    except Exception as exc:
        current_app.logger.warning("Gagal memuat parent_record PJP2U %s: %s", parent_id, exc)

    return {}


def _build_adjustment_summary(row: dict) -> dict:
    parent = _load_parent_record_if_needed(row)

    raw_flt = str(
        row.get("flight_number_adjustment")
        or row.get("adj_flight_number")
        or row.get("flight_number")
        or ""
    ).strip().upper()
    flt_adj = raw_flt if (not raw_flt or raw_flt.endswith("J")) else f"{raw_flt}J"

    a_base = _to_int(parent.get("adult") if parent else row.get("adult_awal"), _to_int(row.get("adult")))
    c_base = _to_int(parent.get("child") if parent else row.get("child_awal"), _to_int(row.get("child")))
    i_base = _to_int(parent.get("infant") if parent else row.get("infant_awal"), _to_int(row.get("infant")))
    tr_base = _to_int(parent.get("transit") if parent else row.get("transit_awal"), _to_int(row.get("transit")))
    tf_base = _to_int(parent.get("transfer") if parent else row.get("transfer_awal"), _to_int(row.get("transfer")))
    off_base = _to_int(parent.get("offload") if parent else row.get("offload_awal"), _to_int(row.get("offload")))

    if parent:
        a_d = _to_int(row.get("adult"))
        c_d = _to_int(row.get("child"))
        i_d = _to_int(row.get("infant"))
        tr_d = _to_int(row.get("transit"))
        tf_d = _to_int(row.get("transfer"))
        off_d = _to_int(row.get("offload"))
        lama_d = _to_int(row.get("pax_lama"))
        baru_d = _to_int(row.get("pax_baru"))
    else:
        a_d = _to_int(row.get("adult_adjustment") if row.get("adult_adjustment") is not None else row.get("adj_adult"))
        c_d = _to_int(row.get("child_adjustment") if row.get("child_adjustment") is not None else row.get("adj_child"))
        i_d = _to_int(row.get("infant_adjustment") if row.get("infant_adjustment") is not None else row.get("adj_infant"))
        tr_d = _to_int(row.get("transit_adjustment") if row.get("transit_adjustment") is not None else row.get("adj_transit"))
        tf_d = _to_int(row.get("transfer_adjustment") if row.get("transfer_adjustment") is not None else row.get("adj_transfer"))
        off_d = _to_int(row.get("offload_adjustment") if row.get("offload_adjustment") is not None else row.get("adj_offload"))
        lama_d = _to_int(row.get("pax_lama_adjustment") if row.get("pax_lama_adjustment") is not None else row.get("adj_lama"))
        baru_d = _to_int(row.get("pax_baru_adjustment") if row.get("pax_baru_adjustment") is not None else row.get("adj_baru"))

    a_final = _to_int(row.get("final_adult"), a_base + a_d)
    c_final = _to_int(row.get("final_child"), c_base + c_d)
    i_final = _to_int(row.get("final_infant"), i_base + i_d)
    tr_final = _to_int(row.get("final_transit"), tr_base + tr_d)
    tf_final = _to_int(row.get("final_transfer"), tf_base + tf_d)
    off_final = _to_int(row.get("final_offload"), off_base + off_d)

    total_penumpang_final = a_final + c_final + i_final + tr_final + tf_final
    wajib_bayar_psc_final = max(0, a_final + c_final + off_final - tr_final)
    wajib_bayar_counter_final = max(0, a_final + c_final + i_final + off_final)

    prev_paying = _to_int(
        parent.get("total_prod_psc") if parent else row.get("paying_pax_sebelumnya"),
        max(0, a_base + c_base + off_base - tr_base),
    )
    curr_paying = wajib_bayar_psc_final
    selisih_paying = curr_paying - prev_paying

    lama_base = _to_int(parent.get("pax_lama") if parent else row.get("pax_lama_awal"), 0)
    raw_baru_base = parent.get("pax_baru") if parent else row.get("pax_baru_awal")
    baru_base = _to_int(raw_baru_base, max(0, prev_paying - lama_base))

    pax_lama_final = lama_base + lama_d
    if parent:
        # Jika selisih baru & lama dipecah di row, pakai baru_base + baru_d;
        # jika pax_baru di row tidak terisi (0) padahal selisih_paying != lama_d, hitung dari selisih paying.
        effective_baru_d = baru_d if (baru_d != 0 or lama_d == selisih_paying) else (selisih_paying - lama_d)
        pax_baru_final = baru_base + effective_baru_d
    else:
        pax_baru_final = baru_base + (baru_d if baru_d != 0 else (selisih_paying - lama_d))

    # Pastikan IV.a + IV.b konsisten dengan total wajib bayar PSC jika tidak ada nilai negatif yang disengaja
    if pax_lama_final + pax_baru_final != wajib_bayar_psc_final and lama_base == 0 and baru_base == prev_paying:
        pax_baru_final = max(0, wajib_bayar_psc_final - pax_lama_final)

    return {
        "flight_number_adj": flt_adj,
        "adult": a_final,
        "child": c_final,
        "infant": i_final,
        "transit": tr_final,
        "transfer": tf_final,
        "offload": off_final,
        "total_penumpang": total_penumpang_final,
        "wajib_bayar_psc": wajib_bayar_psc_final,
        "wajib_bayar_counter": wajib_bayar_counter_final,
        "pax_lama": pax_lama_final,
        "pax_baru": pax_baru_final,
        "sebelumnya_str": f"{a_base}/{c_base}/{i_base}/{tr_base}",
        "sebelumnya_paying": prev_paying,
        "seharusnya_str": f"{a_final}/{c_final}/{i_final}/{tr_final}",
        "seharusnya_paying": curr_paying,
        "selisih_paying": selisih_paying,
        "keterangan": row.get("justifikasi_adjustment") or "-",
        "detail_justifikasi": row.get("detail_justifikasi_adjustment") or row.get("justifikasi_adjustment") or "-",
        "date_adjustment": row.get("date_adjustment") or row.get("tanggal") or "-",
        "nomor_surat": row.get("adjustment_nomor_surat") or row.get("nomor_surat_adjustment") or "",
    }


def _resolve_airline_logo(row: dict) -> str:
    if row.get("airline_logo"):
        return str(row["airline_logo"]).strip()
    if row.get("logo"):
        return str(row["logo"]).strip()

    try:
        ad_rows = app.supabase.table("airline_data").select("*").execute().data or []
        target_ids = {
            str(row.get("id_airline") or "").strip().upper(),
            str(row.get("airline_id") or "").strip().upper(),
            str(row.get("operator") or "").strip().upper(),
            str(row.get("kode_airline") or "").strip().upper(),
            str(row.get("iata_code") or "").strip().upper(),
            str(row.get("airline_name") or "").strip().upper(),
        } - {""}

        for ad in ad_rows:
            ad_tokens = {
                str(ad.get("id_airline") or "").strip().upper(),
                str(ad.get("kode_airline") or "").strip().upper(),
                str(ad.get("iata_code") or "").strip().upper(),
                str(ad.get("nama_airline") or "").strip().upper(),
                str(ad.get("airline_name") or "").strip().upper(),
            } - {""}
            if ad_tokens & target_ids and ad.get("logo"):
                return str(ad["logo"]).strip()
    except Exception as exc:
        current_app.logger.warning("Gagal mengambil logo airline_data: %s", exc)

    return ""


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
    elif jenis == "ADJUSTMENT" and (row.get("date_adjustment") or row.get("verification_adjustment_at")):
        tgl_ref = str(row.get("date_adjustment") or row.get("verification_adjustment_at"))[:10]

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

    verify_url = url_for("ba_doc.verify_public", token=token, _external=True) if token else ""
    qr_url = build_qr_image_url(verify_url, size=136) if verify_url else ""
    integrity_hash = compute_ba_integrity_hash(row, jenis, token) if token else ""

    adult = int(row.get("adult") or 0)
    child = int(row.get("child") or 0)
    infant = int(row.get("infant") or 0)
    transit = int(row.get("transit") or 0)
    offload = int(row.get("offload") or 0)
    total_pax_bayar_line = adult + child
    total_prod_psc = int(row.get("total_prod_psc") or (adult + child + offload - transit))
    total_prod_counter = int(row.get("total_prod_counter") or (adult + child + infant + offload))

    adj_summary = _build_adjustment_summary(row)
    airline_logo = _resolve_airline_logo(row)

    if jenis == "ADJUSTMENT":
        pax_lama_val = adj_summary["pax_lama"]
        pax_baru_val = adj_summary["pax_baru"]
    else:
        pax_lama_val = int(row.get("pax_lama") or 0)
        pax_baru_val = int(row.get("pax_baru") or 0)

    return {
        "row": row,
        "jenis_ba": jenis,
        "token": token,
        "nomor_ba": build_nomor_ba(row, jenis),
        "cab_info": cab_info,
        "aircraft_type": aircraft_type,
        "airline_logo": airline_logo,
        "adj": adj_summary,
        "kalimat_pembuka": format_kalimat_pembuka_ba(tgl_ref or row.get("tanggal")),
        "tanggal_penerbangan_id": format_tanggal_indonesia(row.get("tanggal")),
        "tanggal_ttd_id": format_tanggal_indonesia(ver_at or tgl_ref or row.get("tanggal")),
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
        "offload_passengers": _extract_offload_passengers(row),
        "total_pax_bayar_line": total_pax_bayar_line,
        "total_prod_psc": total_prod_psc,
        "total_prod_counter": total_prod_counter,
        "pax_lama": pax_lama_val,
        "pax_baru": pax_baru_val,
    }


@ba_doc_bp.route("/ba/<cabang>/<jenis_ba>/<int:id_pjp2u>")
@login_required_ba
def print_ba(cabang, jenis_ba, id_pjp2u):
    row, jenis, token = _resolve_record_by_id_and_jenis(id_pjp2u, jenis_ba, require_verified=True)
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
    if jenis == "OFFLOAD":
        template_name = "aeronautika/report/ba_verifikasi_offload.html"
    elif jenis == "ADJUSTMENT":
        template_name = "aeronautika/report/ba_adjustment.html"
    else:
        template_name = "aeronautika/report/ba_verifikasi.html"
    return render_template(template_name, **ctx)


@ba_doc_bp.route("/ba/<cabang>/ADJUSTMENT/<int:id_pjp2u>/surat")
@ba_doc_bp.route("/ba/ADJUSTMENT/<int:id_pjp2u>/surat")
@login_required_ba
def print_surat_adjustment(id_pjp2u, cabang=None):
    is_blank = str(request.args.get("blank") or "").strip().lower() in {"1", "true", "yes"}
    row, jenis, token = _resolve_record_by_id_and_jenis(
        id_pjp2u,
        "ADJUSTMENT",
        require_verified=not is_blank,
    )
    if not row:
        flash("Surat Adjustment belum tersedia atau belum diverifikasi.", "warning")
        return redirect(request.referrer or "/")

    row_cabang = str(row.get("cabang") or row.get("kode_cabang") or "").strip().upper()
    if cabang and (cabang or "").strip().upper() != row_cabang:
        abort(404)

    user = _current_user()
    if not _can_access_ba_record(row, user):
        abort(403)

    # Jika mode UPLOAD dan bukan format kosong, buka file dari static/uploads/airlines/surat/
    if not is_blank:
        doc_mode = str(row.get("adjustment_doc_mode") or "").strip().upper()
        uploaded_raw = str(
            row.get("adjustment_file_url")
            or row.get("adjusment_file_url")
            or ""
        ).strip()

        if doc_mode == "UPLOAD" and uploaded_raw:
            if uploaded_raw.startswith(("http://", "https://")):
                return redirect(uploaded_raw)

            clean_rel = uploaded_raw.lstrip("/")
            if clean_rel.startswith("static/"):
                clean_rel = clean_rel[len("static/"):]
            elif "/" not in clean_rel:
                clean_rel = f"uploads/airlines/surat/{clean_rel}"

            return redirect(url_for("static", filename=clean_rel))

    ctx = _build_ba_context(row, "ADJUSTMENT", token)
    ctx["blank_format"] = is_blank
    return render_template("aeronautika/report/surat_adjustment.html", **ctx)


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