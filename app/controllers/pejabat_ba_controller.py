from datetime import date
from functools import wraps
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import app
from app.utils.decorators import menu_required
from app.models.pejabat_ba_model import PejabatBaModel

pejabat_ba_bp = Blueprint(
    "pejabat_ba",
    __name__,
    url_prefix="/aeronautika/master/pejabat-ba",
)

ALLOWED_PEJABAT_ROLES = ("admin", "pengawas", "superadmin")


def _get_role(user):
    if not isinstance(user, dict):
        user = {}
    raw_role = user.get("role") or user.get("user_role") or session.get("role") or ""
    return str(raw_role).strip().lower()


def _get_actor(user):
    if not isinstance(user, dict):
        user = {}
    nama = user.get("nama_lengkap")
    email = user.get("email")
    if nama and email:
        return f"{nama} ({email})"
    return email or nama or "System"


def _get_accessible_cabangs(user):
    """
    Mengikuti pola session user['allowed_cabang'] dan struktur tabel cabang
    (kode_cabang, nama_cabang, tipe_unit, parent_kode, kota):
      - None          : HO / Superadmin -> semua cabang
      - List > 1 item : Regional (misal REG6 -> ['BDJ', 'PKY', 'BPN', 'PNK'])
      - List 1 item   : Cabang tunggal (misal ['BDJ'])
    """
    role = _get_role(user)
    query = (
        app.supabase.table("cabang")
        .select("kode_cabang, nama_cabang, tipe_unit, parent_kode, kota")
        .is_("deleted_at", "null")
    )

    if role == "superadmin":
        res = query.order("kode_cabang", desc=False).execute()
        return None, (res.data or [])

    if "allowed_cabang" in user:
        allowed_cabang = user.get("allowed_cabang")
        if allowed_cabang is None:
            res = query.order("kode_cabang", desc=False).execute()
            return None, (res.data or [])
        if not allowed_cabang:
            return [], []
        clean_allowed = [c.strip().upper() for c in allowed_cabang if c and c.strip()]
        res = query.in_("kode_cabang", clean_allowed).order("kode_cabang", desc=False).execute()
        return clean_allowed, (res.data or [])

    user_cabang = (user.get("kode_cabang") or "").strip().upper()
    if not user_cabang:
        return [], []
    if user_cabang in ("HO", "KANTOR PUSAT"):
        res = query.order("kode_cabang", desc=False).execute()
        return None, (res.data or [])

    all_cabs = (query.order("kode_cabang", desc=False).execute()).data or []
    reg_cabs = [c for c in all_cabs if (c.get("parent_kode") or "").strip().upper() == user_cabang]
    if reg_cabs:
        return [c["kode_cabang"] for c in reg_cabs], reg_cabs

    single = [c for c in all_cabs if (c.get("kode_cabang") or "").strip().upper() == user_cabang]
    return [user_cabang], single


def pejabat_ba_role_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user") or {}
        if _get_role(user) not in ALLOWED_PEJABAT_ROLES:
            flash("Akses ditolak. Menu Master Pejabat BA hanya untuk role Admin dan Pengawas.", "danger")
            return redirect(url_for("dashboard.index"))
        return f(*args, **kwargs)
    return decorated


def _resolve_kode_cabang(raw_cabang, allowed_cabangs, cabang_list):
    cab = (raw_cabang or "").strip().upper()
    if allowed_cabangs is not None:
        if not allowed_cabangs:
            return ""
        if len(allowed_cabangs) == 1:
            return allowed_cabangs[0]
        if cab and cab in allowed_cabangs:
            return cab
        return cabang_list[0]["kode_cabang"] if cabang_list else allowed_cabangs[0]

    if cab:
        return cab
    return cabang_list[0]["kode_cabang"] if cabang_list else ""


@pejabat_ba_bp.route("/")
@menu_required("pejabat_ba")
@pejabat_ba_role_required
def index():
    user = session.get("user") or {}
    allowed_cabangs, cabang_list = _get_accessible_cabangs(user)

    filter_cabang = (request.args.get("cabang") or "").strip().upper()
    filter_jenis = (request.args.get("jenis_ba") or "").strip().upper()

    if filter_cabang and allowed_cabangs is not None and filter_cabang not in allowed_cabangs:
        filter_cabang = ""

    rows = PejabatBaModel.get_list(
        allowed_cabangs=allowed_cabangs,
        filter_cabang=filter_cabang or None,
        filter_jenis=filter_jenis or None,
        include_deleted=False,
    )

    today_str = date.today().isoformat()
    is_single_cabang = allowed_cabangs is not None and len(allowed_cabangs) <= 1
    default_cabang = _resolve_kode_cabang(
        filter_cabang or (user.get("kode_cabang") or ""),
        allowed_cabangs,
        cabang_list,
    )

    return render_template(
        "aeronautika/pejabat_ba.html",
        rows=rows,
        cabang_list=cabang_list,
        is_single_cabang=is_single_cabang,
        default_cabang=default_cabang,
        filter_cabang=filter_cabang,
        filter_jenis=filter_jenis,
        today_str=today_str,
        active_count=sum(1 for r in rows if r.get("is_active")),
        normal_count=sum(1 for r in rows if r.get("jenis_ba") == "NORMAL"),
        offload_count=sum(1 for r in rows if r.get("jenis_ba") == "OFFLOAD"),
        adj_count=sum(1 for r in rows if r.get("jenis_ba") == "ADJUSTMENT"),
    )


@pejabat_ba_bp.route("/create", methods=["POST"])
@menu_required("pejabat_ba")
@pejabat_ba_role_required
def create():
    user = session.get("user") or {}
    allowed_cabangs, cabang_list = _get_accessible_cabangs(user)
    form = request.form.to_dict()

    kode_cabang = _resolve_kode_cabang(form.get("kode_cabang"), allowed_cabangs, cabang_list)
    if not kode_cabang:
        flash("Kode cabang wajib dipilih atau tersedia pada akun Anda.", "warning")
        return redirect(url_for("pejabat_ba.index"))

    if allowed_cabangs is not None and kode_cabang not in allowed_cabangs:
        flash("Cabang tidak berada dalam cakupan akses Anda.", "danger")
        return redirect(url_for("pejabat_ba.index"))

    form["kode_cabang"] = kode_cabang

    try:
        PejabatBaModel.create(form, actor=_get_actor(user))
        flash(f"Pejabat Berita Acara untuk cabang {kode_cabang} berhasil ditambahkan.", "success")
    except Exception as e:
        flash(f"Gagal menambah pejabat BA: {str(e)}", "danger")

    return redirect(url_for("pejabat_ba.index"))


@pejabat_ba_bp.route("/update/<int:id_pejabat>", methods=["POST"])
@menu_required("pejabat_ba")
@pejabat_ba_role_required
def update(id_pejabat):
    user = session.get("user") or {}
    allowed_cabangs, cabang_list = _get_accessible_cabangs(user)
    existing = PejabatBaModel.get_by_id(id_pejabat)
    if not existing:
        flash("Data pejabat BA tidak ditemukan.", "danger")
        return redirect(url_for("pejabat_ba.index"))

    existing_cab = (existing.get("kode_cabang") or "").strip().upper()
    if allowed_cabangs is not None and existing_cab not in allowed_cabangs:
        flash("Akses ditolak untuk cabang ini.", "danger")
        return redirect(url_for("pejabat_ba.index"))

    form = request.form.to_dict()
    kode_cabang = _resolve_kode_cabang(
        form.get("kode_cabang") or existing_cab,
        allowed_cabangs,
        cabang_list,
    )
    if not kode_cabang:
        flash("Kode cabang wajib diisi.", "warning")
        return redirect(url_for("pejabat_ba.index"))

    form["kode_cabang"] = kode_cabang

    try:
        PejabatBaModel.update(id_pejabat, form, actor=_get_actor(user))
        flash("Data pejabat BA berhasil diperbarui.", "success")
    except Exception as e:
        flash(f"Gagal memperbarui pejabat BA: {str(e)}", "danger")

    return redirect(url_for("pejabat_ba.index"))


@pejabat_ba_bp.route("/delete/<int:id_pejabat>", methods=["POST"])
@menu_required("pejabat_ba")
@pejabat_ba_role_required
def delete(id_pejabat):
    user = session.get("user") or {}
    allowed_cabangs, _ = _get_accessible_cabangs(user)
    existing = PejabatBaModel.get_by_id(id_pejabat)
    if not existing:
        flash("Data pejabat BA tidak ditemukan.", "danger")
        return redirect(url_for("pejabat_ba.index"))

    if allowed_cabangs is not None and (existing.get("kode_cabang") or "").strip().upper() not in allowed_cabangs:
        flash("Akses ditolak untuk cabang ini.", "danger")
        return redirect(url_for("pejabat_ba.index"))

    try:
        PejabatBaModel.soft_delete(id_pejabat, actor=_get_actor(user))
        flash("Data pejabat BA berhasil dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus pejabat BA: {str(e)}", "danger")

    return redirect(url_for("pejabat_ba.index"))