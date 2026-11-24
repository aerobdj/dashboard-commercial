import hashlib
import secrets
from datetime import datetime, timezone
from urllib.parse import quote


HARI_ID = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

BULAN_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

ROMAWI_BULAN = {
    1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI",
    7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI", 12: "XII",
}


def generate_ba_token(jenis_ba: str) -> str:
    prefix_map = {
        "NORMAL": "NRM",
        "OFFLOAD": "OFL",
        "ADJUSTMENT": "ADJ",
    }
    prefix = prefix_map.get((jenis_ba or "NORMAL").upper(), "NRM")
    return f"{prefix}-{secrets.token_hex(12).upper()}"


def compute_ba_integrity_hash(row: dict, jenis_ba: str, token: str) -> str:
    """
    Menghasilkan SHA-256 checksum atas field kunci penerbangan & pax
    sehingga integritas angka pada dokumen BA dapat diverifikasi.
    """
    jenis = (jenis_ba or "NORMAL").upper()
    if jenis == "OFFLOAD":
        ver_name = row.get("name_verification_offload") or ""
        ver_at = row.get("verification_offload_at") or ""
        key_pax = str(row.get("offload") or 0)
    elif jenis == "ADJUSTMENT":
        ver_name = row.get("name_verification_adjustment") or ""
        ver_at = row.get("verification_adjustment_at") or ""
        key_pax = str(row.get("total_prod_psc") or 0)
    else:
        ver_name = row.get("name_verification") or ""
        ver_at = row.get("verification_at") or ""
        key_pax = str(row.get("total_prod_psc") or 0)

    raw_payload = "|".join([
        token or "",
        jenis,
        str(row.get("id_pjp2u") or ""),
        str(row.get("cabang") or ""),
        str(row.get("tanggal") or "")[:10],
        str(row.get("flight_number") or ""),
        str(row.get("registration") or ""),
        str(row.get("origin") or ""),
        str(row.get("destination") or ""),
        str(row.get("adult") or 0),
        str(row.get("child") or 0),
        str(row.get("infant") or 0),
        str(row.get("transit") or 0),
        key_pax,
        str(ver_name),
        str(ver_at),
    ])
    return hashlib.sha256(raw_payload.encode("utf-8")).hexdigest()


def _terbilang_satuan(n: int) -> str:
    angka = [
        "", "satu", "dua", "tiga", "empat", "lima",
        "enam", "tujuh", "delapan", "sembilan", "sepuluh", "sebelas",
    ]
    n = int(n)
    if n < 12:
        return angka[n]
    if n < 20:
        return f"{angka[n - 10]} belas"
    if n < 100:
        return f"{angka[n // 10]} puluh {angka[n % 10]}".strip()
    if n < 200:
        return f"seratus {_terbilang_satuan(n - 100)}".strip()
    if n < 1000:
        return f"{angka[n // 100]} ratus {_terbilang_satuan(n % 100)}".strip()
    if n < 2000:
        return f"seribu {_terbilang_satuan(n - 1000)}".strip()
    if n < 1000000:
        return f"{_terbilang_satuan(n // 1000)} ribu {_terbilang_satuan(n % 1000)}".strip()
    return str(n)


def parse_date_obj(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def format_tanggal_indonesia(val):
    dt = parse_date_obj(val)
    if not dt:
        return str(val or "-")
    hari = HARI_ID.get(dt.weekday(), "")
    bulan = BULAN_ID.get(dt.month, "")
    return f"{hari}, {dt.day} {bulan} {dt.year}"


def format_kalimat_pembuka_ba(val):
    dt = parse_date_obj(val)
    if not dt:
        return "-"
    hari = HARI_ID.get(dt.weekday(), "")
    tgl_kata = _terbilang_satuan(dt.day)
    bulan_kata = BULAN_ID.get(dt.month, "")
    tahun_kata = _terbilang_satuan(dt.year)
    dd_mm_yyyy = dt.strftime("%d-%m-%Y")
    return (
        f"Pada hari ini {hari} tanggal {tgl_kata} bulan {bulan_kata} "
        f"tahun {tahun_kata}, ({dd_mm_yyyy})"
    )


def build_nomor_ba(row: dict, jenis_ba: str) -> str:
    dt = parse_date_obj(row.get("tanggal")) or datetime.now(timezone.utc).date()
    cab = (row.get("cabang") or "CAB").strip().upper()
    code2 = (row.get("airline_code_2") or "AL").strip().upper()
    rom = ROMAWI_BULAN.get(dt.month, "I")
    kode_jenis = {"NORMAL": "NRM", "OFFLOAD": "OFL", "ADJUSTMENT": "ADJ"}.get((jenis_ba or "NORMAL").upper(), "NRM")
    return f"BA.{kode_jenis}/{cab}/{code2}/{rom}/{dt.year}/{row.get('id_pjp2u')}"


def build_qr_image_url(verify_url: str, size: int = 132) -> str:
    encoded = quote(verify_url or "", safe="")
    return f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&margin=4&data={encoded}"