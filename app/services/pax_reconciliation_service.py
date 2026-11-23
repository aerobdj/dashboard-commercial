import io
import re
import pandas as pd
import pdfplumber
from rapidfuzz import fuzz

SUPPORTED_AIRLINES_LIST = [
    ("Fly Jaya (KS)", "Fly Jaya Manifest"),
    ("Lion Air Group (ID / IU / IW / JT / OD / SL)", "Lion Systems Report"),
    ("Pelita Air (IP)", "Pelita DCS Report"),
    ("Royal Brunei Airlines (BI)", "Royal Brunei DCS"),
    ("AirAsia (AK / FD / QZ)", "AirAsia DCS / Navitaire Report"),
    ("Citilink (QG)", "Citilink DCS / Navitaire Report"),
    ("Cebu Pacific (5J)", "Navitaire Flight Close Report"),
    ("Eastar Jet (ZE)", "Navitaire Flight Close Report"),
    ("IndiGo (6E)", "Navitaire Flight Close Report"),
    ("Jetstar Airways (JQ)", "Navitaire Flight Close Report"),
    ("Jeju Air Co. Ltd. (7C)", "Navitaire Flight Close Report"),
    ("Scoot (TR)", "Scoot DCS / Navitaire Report"),
    ("Air India (AI)", "Amadeus Generic Report"),
    ("Cathay Pacific (CX)", "Amadeus Generic Report"),
    ("Etihad Airways (EY)", "Amadeus Generic Report"),
    ("EVA Air (BR)", "Amadeus Generic Report"),
    ("Garuda Indonesia (GA)", "Amadeus Generic Report"),
    ("KLM Royal Dutch Airlines (KL)", "Amadeus Generic Report"),
    ("Malaysia Airlines (MH)", "Amadeus Generic Report"),
    ("Philippine Airlines (PR)", "Amadeus Generic Report"),
    ("Qantas Airways (QF)", "Amadeus Generic Report"),
    ("Qatar Airways (QR)", "Amadeus Generic Report"),
    ("Saudia (SV)", "Amadeus Generic Report"),
    ("Singapore Airlines (SQ)", "Amadeus Generic Report"),
    ("STARLUX Airlines (JX)", "Amadeus Generic Report"),
    ("Thai Airways (TG)", "Amadeus Generic Report"),
    ("Vietnam Airlines (VN)", "Amadeus Generic Report"),
    ("Sriwijaya Air / NAM Air (SJ / IN)", "Sriwijaya / NAM Air Pax Manifest"),
    ("China Airlines (CI)", "China Airlines Pax Manifest"),
    ("Korean Air (KE)", "Korean Air Pax Manifest"),
    ("Juneyao Airlines (HO)", "Multi-Column Columnar Manifest"),
    ("China Eastern Airlines (MU)", "Multi-Column Columnar Manifest"),
    ("China Southern Airlines (CZ)", "Multi-Column Columnar Manifest"),
    ("Hong Kong Airlines (HX)", "Multi-Column Columnar Manifest"),
]

AMADEUS_AIRLINES = {
    "AI": "Air India (AI)",
    "CX": "Cathay Pacific (CX)",
    "EY": "Etihad Airways (EY)",
    "BR": "EVA Air (BR)",
    "GA": "Garuda Indonesia (GA)",
    "KL": "KLM Royal Dutch Airlines (KL)",
    "MH": "Malaysia Airlines (MH)",
    "PR": "Philippine Airlines (PR)",
    "QF": "Qantas Airways (QF)",
    "QR": "Qatar Airways (QR)",
    "SV": "Saudi Arabian Airlines (SV)",
    "SQ": "Singapore Airlines (SQ)",
    "JX": "STARLUX Airlines (JX)",
    "TG": "Thai Airways International (TG)",
    "VN": "Vietnam Airlines (VN)"
}


def clean_passenger_name(name):
    if not name or name == "-":
        return ""
    name_str = str(name).upper().strip()
    name_str = name_str.replace("'", "").replace('"', "")

    if "/" in name_str:
        parts = name_str.split("/")
        if len(parts) >= 2 and re.match(r"^\s*[A-Z0-9]{5,7}\b", parts[1]):
            name_str = parts[0].strip()
        else:
            lname = parts[0].strip()
            fname = parts[1].strip()
            name_str = f"{fname} {lname}"

    if "," in name_str:
        parts = name_str.split(",")
        if len(parts) >= 2:
            lname = parts[0].strip()
            fname = parts[1].strip()
            name_str = f"{fname} {lname}"

    name_str = re.sub(r"\bMUHAMMAD([A-Z]+)\b", r"MUHAMMAD \1", name_str)
    name_str = re.sub(r"\bMOHAMMAD([A-Z]+)\b", r"MOHAMMAD \1", name_str)
    name_str = re.sub(r"\bMUHAMAD([A-Z]+)\b", r"MUHAMAD \1", name_str)
    name_str = re.sub(r"\bMUHMR\b", "MUHAMMAD", name_str)
    name_str = re.sub(r"\b([A-Z]{3,})(MR|MRS|MS|MSTR|MISS|MAST)\b", r"\1", name_str)
    name_str = re.sub(r"\b(MR|MRS|MS|MSTR|MISS|MAST|MR\.|MRS\.|MS\.)\b", " ", name_str)
    name_str = re.sub(r"\b(HJ|HJJ|H|RR|RRA|R\.|R\.R\.)\b", " ", name_str)
    name_str = re.sub(r"[^A-Z\s]", "", name_str)

    words = name_str.split()
    if words:
        if words[0] == "ABDU":
            words[0] = "ABDUL"
        elif words[0] in ["MUH", "MHA"]:
            words[0] = "MUHAMMAD"
        name_str = " ".join(words)

    return " ".join(name_str.split())


def clean_amadeus_name(raw_name):
    if not raw_name or raw_name == "-":
        return ""
    name_str = str(raw_name).upper().strip()

    if "/" in name_str:
        parts = name_str.split("/")
        lname = parts[0].strip()
        rest = parts[1].strip() if len(parts) > 1 else ""
        rest = re.sub(r"\b(MR|MRS|MS|MISS|MSTR|MR\.|MRS\.|MS\.)\b", " ", rest)
        rest = re.sub(r"\b([MFC])\b$", " ", rest)
        fname = rest.strip()
        name_str = f"{fname} {lname}" if fname else lname
    else:
        name_str = re.sub(r"\b(MR|MRS|MS|MSTR|MISS|MAST|MR\.|MRS\.|MS\.)\b", " ", name_str)

    name_str = re.sub(r"\bMUHAMMAD([A-Z]+)\b", r"MUHAMMAD \1", name_str)
    name_str = re.sub(r"\bMOHAMMAD([A-Z]+)\b", r"MOHAMMAD \1", name_str)
    name_str = re.sub(r"\bMUHAMAD([A-Z]+)\b", r"MUHAMAD \1", name_str)
    name_str = re.sub(r"\bMUHMR\b", "MUHAMMAD", name_str)
    name_str = re.sub(r"\b(HJ|HJJ|H)\b", " ", name_str)
    name_str = re.sub(r"[^A-Z\s]", "", name_str)

    words = name_str.split()
    if words:
        if words[0] == "ABDU":
            words[0] = "ABDUL"
        elif words[0] in ["MUH", "MHA"]:
            words[0] = "MUHAMMAD"
        name_str = " ".join(words)

    return " ".join(name_str.split())


def determine_pax_type(type_val, is_transit=False):
    t = str(type_val).strip().upper()
    if t in ["I", "INF", "INFANT"]:
        return "Infant (Transit)" if is_transit else "Infant"
    elif t in ["C", "CHD", "CHILD"]:
        return "Child (Transit)" if is_transit else "Child"
    elif t in ["M", "F", "ADULT", "ADT"]:
        return "Adult (Transit)" if is_transit else "Adult"
    else:
        return "Adult (Transit)" if is_transit else "Adult"


def clean_seat_number(seat_raw):
    if not seat_raw or str(seat_raw).strip() in ["-", "", "NAN", "NONE", "0CGK", "0"]:
        return "-"
    seat_clean = str(seat_raw).strip().upper().replace(" ", "")
    if seat_clean in ["INF", "INFT"]:
        return "INF"
    if seat_clean.startswith("0") and len(seat_clean) > 3 and seat_clean[1:].isalpha():
        return "-"

    match = re.search(r"^0*([1-9]\d*[A-Z])$", seat_clean)
    if match:
        return match.group(1)
    match_any = re.search(r"([1-9]\d*[A-Z])", seat_clean)
    if match_any:
        return match_any.group(1)
    match_num = re.search(r"0*([1-9]\d*)", seat_clean)
    if match_num:
        return match_num.group(1)
    return seat_clean


def seat_sort_key(seat_str):
    if not seat_str or seat_str in ["-", "INF"]:
        return (999, "Z")
    match = re.match(r"^(\d+)([A-Z]?)$", str(seat_str).upper())
    if match:
        num = int(match.group(1))
        letter = match.group(2) if match.group(2) else "A"
        return (num, letter)
    return (998, str(seat_str))


def load_single_tapping_bytes(filename, file_bytes):
    if not file_bytes:
        return pd.DataFrame(), "-", "-"

    fname_lower = filename.lower()
    df = None
    flight_no = "-"
    route = "-"

    if fname_lower.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception:
            df = None

    if df is None or df.empty:
        try:
            tables = pd.read_html(io.BytesIO(file_bytes))
            if tables and len(tables) > 0:
                df = tables[0]
        except Exception:
            df = None

    if df is None or df.empty:
        for enc in ["utf-8", "latin1", "iso-8859-1", "cp1252", "utf-16"]:
            for sep in ["\t", ",", ";", "|"]:
                try:
                    temp_df = pd.read_csv(io.BytesIO(file_bytes), sep=sep, encoding=enc, on_bad_lines="skip")
                    if temp_df is not None and len(temp_df.columns) > 1 and len(temp_df) > 0:
                        df = temp_df
                        break
                except Exception:
                    continue
            if df is not None and not df.empty:
                break

    if df is not None and not df.empty:
        df.columns = [str(col).strip().upper() for col in df.columns]
        for col in ["FLIGHT", "FLIGHT NO", "FLIGHT_NO", "FLIGHTNO", "NO FLIGHT"]:
            if col in df.columns:
                val = str(df[col].dropna().iloc[0]).strip() if not df[col].dropna().empty else "-"
                if val != "-":
                    flight_no = val
                    break

        for col in ["ROUTE", "FLIGHT ROUTE", "RUTE", "DESTINATION", "SECTOR"]:
            if col in df.columns:
                val_r = str(df[col].dropna().iloc[0]).strip() if not df[col].dropna().empty else "-"
                if val_r != "-":
                    route = val_r
                    break

        return df, flight_no, route
    return pd.DataFrame(), "-", "-"


def load_multiple_tapping_files(tapping_items):
    """tapping_items: list of tuple (filename, bytes)"""
    if not tapping_items:
        return pd.DataFrame(), "Tidak ada scan"

    combined_dfs = []
    scan_summaries = []

    for fname, fbytes in tapping_items:
        df, fl_no, fl_route = load_single_tapping_bytes(fname, fbytes)
        if not df.empty:
            combined_dfs.append(df)
            if fl_route != "-":
                scan_summaries.append(f"{fl_no} ({fl_route})")
            else:
                scan_summaries.append(f"{fl_no}")

    if combined_dfs:
        final_df = pd.concat(combined_dfs, ignore_index=True)
        scan_text = " | ".join(scan_summaries)
        return final_df, scan_text
    return pd.DataFrame(), "Data Scan Kosong"


def detect_and_parse_manifest(filename, file_bytes):
    full_text = ""
    if filename.lower().endswith(".txt"):
        full_text = file_bytes.decode("utf-8", errors="ignore")
    else:
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        full_text += text + "\n"
        except Exception:
            full_text = file_bytes.decode("utf-8", errors="ignore")

    full_text_upper = full_text.upper()

    # 1. AMADEUS GENERIC REPORT ROUTER
    if "LIST OF:" in full_text_upper or "GENERIC REPORT" in full_text_upper or "ACCEPTANCECUSTOMER" in full_text_upper:
        fl_detect = re.search(r"\b([A-Z0-9]{2})\s*\d{1,4}\s+\d{1,2}[A-Z]{3}\b", full_text_upper)
        if fl_detect:
            airline_code = fl_detect.group(1).upper()
        else:
            fl_fallback = re.search(r"\b(AI|CX|EY|BR|GA|KL|MH|PR|QF|QR|SV|SQ|JX|TG|VN)\s*\d{1,4}\b", full_text_upper)
            airline_code = fl_fallback.group(1).upper() if fl_fallback else ""
        airline_label = AMADEUS_AIRLINES.get(airline_code, f"Amadeus Generic Report ({airline_code})")
        return parse_manifest_amadeus_generic_report_from_text(full_text), airline_label

    # 2. NAVITAIRE REPORT ROUTER
    if "AirAsia" in full_text or "AIRASIA" in full_text_upper or re.search(r"\b(AK|QZ|FD)\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_airasia_from_text(full_text), "AirAsia (AK/QZ/FD)"
    if "CITILINK" in full_text_upper or "BDJJOG" in full_text_upper or re.search(r"\bQG\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_citilink_from_text(full_text), "Citilink (QG)"
    if "IndiGo" in full_text or re.search(r"\b6E[\.\s]*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_navitaire_from_text(full_text, "6E"), "IndiGo (6E)"
    if "Cebu Pacific" in full_text or "Cebu" in full_text or re.search(r"\b5J\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_navitaire_from_text(full_text, "5J"), "Cebu Pacific (5J)"
    if "Jetstar" in full_text or re.search(r"\bJQ\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_navitaire_from_text(full_text, "JQ"), "Jetstar Airways (JQ)"
    if "Jeju Air" in full_text or re.search(r"\b7C\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_navitaire_from_text(full_text, "7C"), "Jeju Air (7C)"
    if "Eastar Jet" in full_text or re.search(r"\bZE\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_navitaire_from_text(full_text, "ZE"), "Eastar Jet (ZE)"
    if "Scoot" in full_text or re.search(r"\bTR\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_scoot_from_text(full_text), "Scoot (TR)"

    # 3. PELITA / FLY JAYA
    if "MANIFEST LIST" in full_text or "CONFIDENTIAL" in full_text or "SEATOPTION" in full_text:
        if re.search(r"\bKS\s*\d{3,4}\b", full_text, re.IGNORECASE):
            return parse_manifest_pelita_from_text(full_text), "Fly Jaya (KS)"
        return parse_manifest_pelita_from_text(full_text), "Pelita Air (IP)"

    # 4. OTHER INDIVIDUAL AIRLINES
    if "SRIWIJAYA" in full_text_upper or "NAM AIR" in full_text_upper or re.search(r"\b(SJ|IN)\d{2,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_sriwijaya_from_text(full_text), "Sriwijaya / NAM Air (SJ/IN)"
    if "CHINA AIRLINES" in full_text_upper or re.search(r"\bCI\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_china_airlines_from_text(full_text), "China Airlines (CI)"
    if "KOREAN AIR" in full_text_upper or re.search(r"\bKE\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_korean_air_from_text(full_text), "Korean Air (KE)"
    if "Royal Brunei" in full_text or re.search(r"\bBI\s*\d{3,4}\b", full_text, re.IGNORECASE):
        return parse_manifest_royal_brunei_from_text(full_text), "Royal Brunei (BI)"
    if "HONG KONG" in full_text_upper or "JUNEYAO" in full_text_upper or "CHINA EASTERN" in full_text_upper or "CHINA SOUTHERN" in full_text_upper or re.search(r"\b(HX|HO|H0|MU|CZ)\s*\d{3,4}\b", full_text_upper):
        if "HONG KONG" in full_text_upper or re.search(r"\bHX\s*\d{3,4}\b", full_text_upper):
            return parse_manifest_chinese_hk_from_text(full_text, "HX"), "Hong Kong Airlines (HX)"
        elif "CHINA SOUTHERN" in full_text_upper or re.search(r"\bCZ\s*\d{3,4}\b", full_text_upper):
            return parse_manifest_chinese_hk_from_text(full_text, "CZ"), "China Southern Airlines (CZ)"
        elif "CHINA EASTERN" in full_text_upper or re.search(r"\bMU\s*\d{3,4}\b", full_text_upper):
            return parse_manifest_chinese_hk_from_text(full_text, "MU"), "China Eastern Airlines (MU)"
        return parse_manifest_chinese_hk_from_text(full_text, "HO"), "Juneyao Airlines (HO)"

    # 5. LION GROUP
    return parse_manifest_lion_group_from_text(full_text), "Lion Group (JT/IW/ID/IU)"


def parse_manifest_lion_group_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"FLIGHT\s*[:\.-]?\s*([A-Z0-9]{2,3}\s*\d{3,4})", full_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", " ", fl_match.group(1).upper().strip())

    date_match = re.search(r"DATE\s*[:\.-]?\s*(\d{1,2}[A-Z]{3}\d{2})", full_text, re.IGNORECASE)
    if date_match:
        flight_date_mnf = date_match.group(1).strip()

    emb_match = re.search(r"PT\.OF\s*EMBARKATION\s*[:\.-]?\s*([A-Z]{3})", full_text, re.IGNORECASE)
    if emb_match:
        origin = emb_match.group(1).strip()

    dest_match = re.search(r"PT\.OF\s*DEST\s*[:\.-]?\s*([A-Z]{3})", full_text, re.IGNORECASE)
    if dest_match:
        destination = dest_match.group(1).strip()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"

    for line in full_text.split("\n"):
        line_str = line.strip()
        parts = line_str.split("/")
        if len(parts) >= 8:
            part0 = re.sub(r"^[0-9\s]+", "", parts[0]).strip()
            part1 = parts[1].strip() if len(parts) > 1 else ""

            gender_or_titles = ["M.", "F.", "M", "F", "MR", "MRS", "MS", "MISS", "MSTR"]
            titles_prefix = ["ST", "SE", "HJ", "HJJ", "H", "DR", "DARS"]

            if part1 in gender_or_titles or not part1:
                raw_full_name = part0
            elif part0 in titles_prefix:
                raw_full_name = f"{part1} {part0}".strip()
            else:
                raw_full_name = f"{part1} {part0}".strip()

            if "FNAME" in part1.upper() or "LNAME" in part0.upper() or "TYPE" in line_str.upper() or "TOTALS" in line_str.upper() or "Y CLASS" in line_str.upper():
                continue

            clean_name = clean_passenger_name(raw_full_name)

            seat = "-"
            for part in parts:
                p_str = part.strip().replace(".", "")
                if re.match(r"^[0-9]{1,2}[A-F]$", p_str):
                    seat = p_str
                    break

            tkt_no = "NO_PNR_LION"
            tkt_idx = -1
            for idx_p, part in enumerate(parts):
                part_clean = part.strip()
                if part_clean.isdigit() and len(part_clean) >= 10:
                    tkt_no = part_clean
                    tkt_idx = idx_p
                    break

            special_val = parts[-1].strip() if len(parts) > 0 else ""

            is_transit = False
            if tkt_idx != -1 and len(parts) > tkt_idx + 2:
                in_flt_raw = parts[tkt_idx + 1].strip()
                tr_org_raw = parts[tkt_idx + 2].strip()
                if len(re.sub(r"[^\w]", "", in_flt_raw)) > 0 or len(re.sub(r"[^\w]", "", tr_org_raw)) > 0:
                    is_transit = True

            pax_code_field = parts[2].upper() if len(parts) > 2 else ""
            line_upper = line_str.upper()

            is_standalone_infant = (
                pax_code_field in ["INF", "INFT"] or
                "/INFT/" in line_upper or
                "/INF/" in line_upper or
                seat.upper() == "INF"
            )
            is_infant_attached = ("INF" in special_val or "INFANT" in line_upper) and not is_standalone_infant

            if is_standalone_infant:
                base_type = "Infant"
                seat = "INF"
            elif "CHD" in special_val or "CHILD" in line_upper or pax_code_field == "CHD":
                base_type = "Child"
            else:
                base_type = "Adult"

            type_pax_final = determine_pax_type(base_type, is_transit)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_full_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": clean_seat_number(seat),
                    "pnr_manifest": tkt_no,
                    "type_manifest": type_pax_final,
                    "section": "BOARDED",
                    "is_matched": False
                })

                if is_infant_attached:
                    inf_type_final = determine_pax_type("Infant", is_transit)
                    manifest_data.append({
                        "raw_nama_manifest": f"INFANT ({raw_full_name})",
                        "clean_nama_manifest": f"INFANT OF {clean_name}",
                        "seat_manifest": "INF",
                        "pnr_manifest": tkt_no,
                        "type_manifest": inf_type_final,
                        "section": "BOARDED",
                        "is_matched": False
                    })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_amadeus_generic_report_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    working_text = full_text.upper().split("LIST OF: PDF-INFANT")[0] if "LIST OF: PDF-INFANT" in full_text.upper() else full_text

    fl_match = re.search(r"\b([A-Z0-9]{2}\s*\d{2,4})\s+(\d{1,2}[A-Za-z]{3})(?:\s+([A-Z]{3}))?", working_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", "", fl_match.group(1).upper().strip())
        flight_date_mnf = fl_match.group(2).upper()
        if fl_match.group(3):
            origin = fl_match.group(3).upper()

    pattern_pax = re.compile(
        r"^\s*\d+\.\s*([A-Za-z0-9\/\+\s\.-]+?)\s+\b([AMFCI])\b\s+([A-Z]{3})\s+([A-Z]{3})\s+.*?\s+\b([BN])\b\s+([0-9]{1,3}[A-Za-z]|\d+|INF|-)?(?:\s+(\d{10,14}))?",
        re.IGNORECASE
    )

    for line in working_text.split("\n"):
        line_clean = re.sub(r"^[\*\s]+", "", line.strip())
        if not line_clean or line_clean.startswith("Generic Report") or line_clean.startswith("Report content") or "FLIGHT RELATED COMMENTS" in line_clean or line_clean.startswith("LIST OF"):
            continue

        match = pattern_pax.search(line_clean)
        if match:
            raw_name = match.group(1).strip()
            pax_code = match.group(2).upper()
            orig_pax = match.group(3).upper()
            dest_pax = match.group(4).upper()
            board_status = match.group(5).upper()
            seat_raw = match.group(6) if match.group(6) else "-"
            tkt_no_raw = match.group(7) if match.group(7) else "-"

            if origin == "-":
                origin = orig_pax
            destination = dest_pax

            clean_name = clean_amadeus_name(raw_name)
            section_val = "NO_SHOW" if board_status == "N" else "BOARDED"
            pnr_val = tkt_no_raw if (tkt_no_raw != "-" and re.match(r"^\d{10,14}$", tkt_no_raw)) else "-"

            if pax_code == "C":
                pax_type = "Child"
                seat_val = clean_seat_number(seat_raw)
            elif pax_code == "I":
                pax_type = "Infant"
                seat_val = "INF"
            else:
                pax_type = "Adult"
                seat_val = clean_seat_number(seat_raw)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": section_val,
                    "is_matched": False
                })

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_navitaire_from_text(full_text, default_code="JQ"):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"Flight\s*:\s*(?:[A-Z0-9]{2}\s*)?(\d{2,4})\s+([A-Z]{6})", full_text, re.IGNORECASE)
    if fl_match:
        fl_num = fl_match.group(1).strip()
        flight_no_mnf = f"{default_code} {fl_num}"
        route_raw = fl_match.group(2).upper().strip()
        if len(route_raw) == 6:
            origin = route_raw[:3]
            destination = route_raw[3:]

    date_match = re.search(r"Date\s*:\s*(\d{1,2}[A-Za-z]{3,4}\d{2})", full_text, re.IGNORECASE)
    if date_match:
        flight_date_mnf = date_match.group(1).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    current_section = "BOARDED"
    last_parent_pnr = f"NO_PNR_{default_code}"

    for line in full_text.split("\n"):
        line_str = line.strip()
        if not line_str or line_str.startswith("Weight") or "Flight Close" in line_str or line_str.startswith("Totals") or line_str.startswith("---") or line_str.startswith("Cnt Name") or line_str.startswith("TKT:") or line_str.startswith("="):
            continue

        line_upper = line_str.upper()
        if "THRU NO SHOW" in line_upper:
            current_section = "THRU_NO_SHOW"
            continue
        elif "THRU CHECKED-IN" in line_upper or "THRU BOARDED" in line_upper:
            current_section = "THRU_BOARDED"
            continue
        elif "NO SHOWS" in line_upper or "NO SHOW" in line_upper:
            current_section = "NO_SHOW"
            continue
        elif "UNCONFIRMED" in line_upper or "STAND-BY" in line_upper or "FARE PRIORITY" in line_upper or "UNAPPROVED STAND" in line_upper:
            current_section = "IGNORE"
            continue
        elif "CHECKED-IN/BOARDED:" in line_upper or "CHECKED-IN" in line_upper or "PAX CHECKED-IN" in line_upper:
            current_section = "BOARDED"
            continue

        if current_section == "IGNORE":
            continue

        if "INFT:" in line_str:
            infant_raw = line_str.replace("INFT:", "").strip()
            clean_name = clean_passenger_name(infant_raw)
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Infant", is_transit)
            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": infant_raw,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": "INF",
                    "pnr_manifest": last_parent_pnr,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })
            continue

        match_pax = re.search(
            r"^\s*\d+\s+([A-Za-z\s,\.-]+?)\s+([A-Z0-9]{6})\s+([A-Z0-9]{1,3})\s+\d+\s+\d{1,2}[A-Za-z]{3,4}\d{2}\b",
            line_str
        )
        if match_pax:
            raw_name = match_pax.group(1).strip()
            pnr_val = match_pax.group(2).strip()
            rest_line = line_str[match_pax.end():]
            seat_search = re.search(r"\b([1-9]\d{0,2}[A-Z])\b", rest_line)
            seat_raw = seat_search.group(1) if seat_search else "-"

            clean_name = clean_passenger_name(raw_name)
            seat_val = clean_seat_number(seat_raw) if seat_raw != "-" else "-"
            last_parent_pnr = pnr_val
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Adult", is_transit)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_citilink_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"Flight\s*[:\.-]?\s*(?:QG\s*)?(\d{3,4})\s*([A-Z]{3})?([A-Z]{3})?", full_text, re.IGNORECASE)
    if fl_match:
        fl_num = fl_match.group(1).strip()
        flight_no_mnf = f"QG {fl_num}"
        if fl_match.group(2) and fl_match.group(3):
            origin = fl_match.group(2).upper()
            destination = fl_match.group(3).upper()

    date_match = re.search(r"Date\s*[:\.-]?\s*(\d{1,2}[A-Za-z]{3}\d{2})", full_text, re.IGNORECASE)
    if date_match:
        flight_date_mnf = date_match.group(1).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    current_section = "BOARDED"
    last_parent_name = ""
    last_parent_pnr = "NO_PNR_CITILINK"

    for line in full_text.split("\n"):
        line_str = line.strip()
        if not line_str:
            continue
        line_upper = line_str.upper()

        if "THRU NO SHOW" in line_upper:
            current_section = "THRU_NO_SHOW"
            continue
        elif "THRU CHECKED-IN" in line_upper or "THRU BOARDED" in line_upper:
            current_section = "THRU_BOARDED"
            continue
        elif "NO SHOWS" in line_upper or "NO SHOW" in line_upper:
            current_section = "NO_SHOW"
            continue
        elif "UNCONFIRMED" in line_upper:
            current_section = "IGNORE"
            continue
        elif "STAND-BY" in line_upper or "CHECKED-IN/BOARDED:" in line_upper or "CHECKED-IN" in line_upper or "PAX CHECKED-IN" in line_upper:
            current_section = "BOARDED"
            continue

        if current_section == "IGNORE":
            continue

        if "INFT:" in line_str:
            infant_raw = line_str.replace("INFT:", "").strip()
            clean_infant = clean_passenger_name(infant_raw)
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Infant", is_transit)
            full_infant_display = f"INFANT OF {last_parent_name} ({clean_infant})" if last_parent_name else clean_infant

            if len(clean_infant) > 2:
                manifest_data.append({
                    "raw_nama_manifest": infant_raw,
                    "clean_nama_manifest": full_infant_display,
                    "seat_manifest": "INF",
                    "pnr_manifest": last_parent_pnr,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })
            continue

        match_pax = re.search(
            r"^\d+\s+([A-Za-z\s,\.\/'\-]+?)\s+([A-Z0-9]{6})\s+[A-Z0-9]+\s+\d+\s+\d+[A-Za-z]{3}\d{2}\s*([0-9]{1,3}[A-Za-z]+)?",
            line_str,
            re.IGNORECASE
        )
        if match_pax:
            raw_name = match_pax.group(1).strip()
            pnr_val = match_pax.group(2).strip()
            seat_raw = match_pax.group(3).strip() if match_pax.group(3) else "-"

            clean_name = clean_passenger_name(raw_name)
            seat_val = clean_seat_number(seat_raw)
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Adult", is_transit)

            last_parent_name = clean_name
            last_parent_pnr = pnr_val

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_airasia_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"Flight\s*:\s*([A-Z0-9]{2}\s*\d{3,4})\s+([A-Z]{6})", full_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", " ", fl_match.group(1).upper().strip())
        route_raw = fl_match.group(2).upper().strip()
        if len(route_raw) == 6:
            origin = route_raw[:3]
            destination = route_raw[3:]

    date_match = re.search(r"Date\s*:\s*(\d{1,2}[A-Za-z]{3,4}\d{2})", full_text, re.IGNORECASE)
    if date_match:
        flight_date_mnf = date_match.group(1).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    current_section = "BOARDED"
    last_parent_pnr = "NO_PNR_AIRASIA"

    for line in full_text.split("\n"):
        line_str = line.strip()
        if not line_str or line_str.startswith("Weight") or "Flight Close" in line_str or line_str.startswith("Totals") or line_str.startswith("---") or line_str.startswith("Cnt Name") or line_str.startswith("TKT:") or line_str.startswith("="):
            continue

        line_upper = line_str.upper()
        if "THRU NO SHOW" in line_upper:
            current_section = "THRU_NO_SHOW"
            continue
        elif "THRU CHECKED-IN" in line_upper or "THRU BOARDED" in line_upper:
            current_section = "THRU_BOARDED"
            continue
        elif "NO SHOWS" in line_upper or "NO SHOW" in line_upper:
            current_section = "NO_SHOW"
            continue
        elif "UNCONFIRMED" in line_upper or "STAND-BY" in line_upper or "FARE PRIORITY" in line_upper or "UNAPPROVED STAND" in line_upper:
            current_section = "IGNORE"
            continue
        elif "CHECKED-IN/BOARDED:" in line_upper or "CHECKED-IN" in line_upper or "PAX CHECKED-IN" in line_upper:
            current_section = "BOARDED"
            continue

        if current_section == "IGNORE":
            continue

        if "INFT:" in line_str:
            infant_raw = line_str.replace("INFT:", "").strip()
            clean_name = clean_passenger_name(infant_raw)
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Infant", is_transit)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": infant_raw,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": "INF",
                    "pnr_manifest": last_parent_pnr,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })
            continue

        match_pax = re.search(
            r"^\s*\d+\s+([A-Za-z\s,\.-]+?)\s+([A-Z0-9]{6})\s+([A-Z0-9]{1,3})\s+\d+\s+\d{1,2}[A-Za-z]{3,4}\d{2}\b",
            line_str
        )
        if match_pax:
            raw_name = match_pax.group(1).strip()
            pnr_val = match_pax.group(2).strip()
            rest_line = line_str[match_pax.end():]
            seat_search = re.search(r"\b([1-9]\d{0,2}[A-Z])\b", rest_line)
            seat_raw = seat_search.group(1) if seat_search else "-"

            clean_name = clean_passenger_name(raw_name)
            seat_val = clean_seat_number(seat_raw) if seat_raw != "-" else "-"
            last_parent_pnr = pnr_val
            is_transit = current_section in ["THRU_BOARDED", "THRU_NO_SHOW"]
            pax_type = determine_pax_type("Adult", is_transit)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": current_section,
                    "is_matched": False
                })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_sriwijaya_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"\b((?:SJ|IN)\s*\d{2,4})\s*/\s*([A-Z]{3})-([A-Z]{3})\b", full_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", " ", fl_match.group(1).upper().strip())
        origin = fl_match.group(2).upper()
        destination = fl_match.group(3).upper()
    else:
        fl_simple = re.search(r"\b((?:SJ|IN)\s*\d{2,4})\b", full_text, re.IGNORECASE)
        if fl_simple:
            flight_no_mnf = re.sub(r"\s+", " ", fl_simple.group(1).upper().strip())
        route_simple = re.search(r"\b([A-Z]{3})-([A-Z]{3})\b", full_text)
        if route_simple:
            origin = route_simple.group(1).upper()
            destination = route_simple.group(2).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"

    date_match = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{1,2}-[A-Za-z]{3}-\d{2,4})", full_text, re.IGNORECASE)
    if date_match:
        raw_d = date_match.group(1).upper().replace("-", " ")
        parts_d = raw_d.split()
        flight_date_mnf = f"{parts_d[0]}{parts_d[1]}{parts_d[2][-2:]}" if len(parts_d) == 3 else raw_d

    pax_pattern = re.compile(
        r"^\s*\d+\s*\|\s*([^|]+?)\s*\|\s*(\d{10,14})\s*\|\s*([A-Z0-9]{6})\s*\|\s*([ACIT](?:\+[I])?)\s*\|\s*(?:SN)?([0-9]{1,3}[A-Z]|INF|-)?",
        re.MULTILINE | re.IGNORECASE
    )

    def process_pax_entry(raw_name, bcode_pnr, status_code, seat_raw):
        status_code = status_code.upper().strip()
        if "~" in raw_name or "+I" in status_code:
            parts = raw_name.split("~")
            parent_raw = parts[0].strip()
            infant_raw = parts[1].strip() if len(parts) > 1 else "INFANT"

            parent_clean = clean_passenger_name(parent_raw)
            seat_clean_parent = clean_seat_number(seat_raw)
            base_type_parent = "Child" if status_code.startswith("C") else "Adult"
            type_parent_final = determine_pax_type(base_type_parent, is_transit=("T" in status_code))

            if len(parent_clean) > 2:
                manifest_data.append({
                    "raw_nama_manifest": parent_raw,
                    "clean_nama_manifest": parent_clean,
                    "seat_manifest": seat_clean_parent,
                    "pnr_manifest": bcode_pnr,
                    "type_manifest": type_parent_final,
                    "section": "BOARDED",
                    "is_matched": False
                })

            infant_clean = clean_passenger_name(infant_raw)
            type_infant_final = determine_pax_type("Infant", is_transit=("T" in status_code))
            if len(infant_clean) > 2:
                manifest_data.append({
                    "raw_nama_manifest": infant_raw,
                    "clean_nama_manifest": infant_clean,
                    "seat_manifest": "INF",
                    "pnr_manifest": bcode_pnr,
                    "type_manifest": type_infant_final,
                    "section": "BOARDED",
                    "is_matched": False
                })
        else:
            clean_name = clean_passenger_name(raw_name)
            seat_clean = clean_seat_number(seat_raw)
            is_transit = (status_code == "T")
            if status_code == "I" or seat_clean == "INF":
                base_type = "Infant"
            elif status_code == "C":
                base_type = "Child"
            else:
                base_type = "Adult"

            type_pax_final = determine_pax_type(base_type, is_transit)
            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_clean,
                    "pnr_manifest": bcode_pnr,
                    "type_manifest": type_pax_final,
                    "section": "BOARDED",
                    "is_matched": False
                })

    matches = pax_pattern.findall(full_text)
    if matches:
        for m in matches:
            process_pax_entry(m[0].strip(), m[2].strip(), m[3].strip(), m[4].strip() if m[4] else "-")
    else:
        cleaned_text = re.sub(r"\n\s*", " ", full_text)
        for entry in re.split(r"(?=\b\d+\s*\|\s*[A-Za-z])", cleaned_text):
            m = pax_pattern.search(entry)
            if m:
                process_pax_entry(m.group(1).strip(), m.group(3).strip(), m.group(4).strip(), m.group(5).strip() if m.group(5) else "-")

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_scoot_from_text(full_text):
    return parse_manifest_navitaire_from_text(full_text, "TR")


def parse_manifest_royal_brunei_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    head_match = re.search(r"(\d{1,2}/[A-Za-z]{3}/\d{4})\s+([A-Z0-9]{2}\d{3,4})\s+([A-Z]{3})\s*-\s*([A-Z]{3})", full_text, re.IGNORECASE)
    if head_match:
        raw_d = head_match.group(1).upper().split("/")
        flight_date_mnf = f"{raw_d[0]}{raw_d[1]}{raw_d[2][-2:]}" if len(raw_d) == 3 else head_match.group(1)
        flight_no_mnf = re.sub(r"([A-Z]+)(\d+)", r"\1 \2", head_match.group(2).upper())
        origin = head_match.group(3).upper()
        destination = head_match.group(4).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"

    for line in full_text.split("\n"):
        line_str = line.strip()
        if not line_str or "Check-In List" in line_str or "Total Pax" in line_str or "END LIST" in line_str or line_str.startswith("No Surname"):
            continue

        match_pax = re.search(r"^\d+\s+([A-Za-z\s]+?)\s+([M|F|C|I])\s+([0-9]{1,3}[A-Z]|INF)\s+([A-Z0-9]{6})", line_str)
        if match_pax:
            raw_name = match_pax.group(1).strip()
            gender_code = match_pax.group(2).strip()
            seat_raw = match_pax.group(3).strip()
            pnr_val = match_pax.group(4).strip()

            clean_name = clean_passenger_name(raw_name)
            pax_type = determine_pax_type(gender_code)

            if gender_code == "I" or seat_raw == "INF":
                seat_val = "INF"
                pax_type = "Infant"
            else:
                seat_val = clean_seat_number(seat_raw)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": "BOARDED",
                    "is_matched": False
                })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_pelita_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}|\d{1,2}[A-Za-z]{3}\d{2})?\s*[\d:]*\s*([A-Z0-9]{2}\s*\d{3,4})\s+([A-Z]{3})-([A-Z]{3})", full_text, re.IGNORECASE)
    if fl_match:
        if fl_match.group(1):
            raw_d = fl_match.group(1).upper()
            d_sub = re.search(r"(\d{1,2})\s*([A-Z]{3})", raw_d)
            flight_date_mnf = f"{d_sub.group(1)}{d_sub.group(2)}" if d_sub else raw_d
        fl_prefix = re.search(r"([A-Z]+)", fl_match.group(2), re.I).group(1).upper()
        fl_num = re.sub(r"[^0-9]", "", fl_match.group(2))
        flight_no_mnf = f"{fl_prefix} {fl_num}"
        origin = fl_match.group(3).upper()
        destination = fl_match.group(4).upper()
        flight_route_mnf = f"{origin}-{destination}"
    else:
        fl_simple = re.search(r"([A-Z0-9]{2}\s*\d{3,4})", full_text, re.IGNORECASE)
        if fl_simple:
            fl_prefix = re.search(r"([A-Z]+)", fl_simple.group(1), re.I).group(1).upper()
            fl_num = re.sub(r"[^0-9]", "", fl_simple.group(1))
            flight_no_mnf = f"{fl_prefix} {fl_num}"

        date_simple = re.search(r"(\d{1,2}\s+[A-Z]{3}\s+\d{4}|\d{1,2}[A-Za-z]{3}\d{2})", full_text, re.IGNORECASE)
        if date_simple:
            raw_d = date_simple.group(1).upper()
            d_sub = re.search(r"(\d{1,2})\s*([A-Z]{3})", raw_d)
            flight_date_mnf = f"{d_sub.group(1)}{d_sub.group(2)}" if d_sub else raw_d

        route_simple = re.search(r"([A-Z]{3})-([A-Z]{3})", full_text)
        flight_route_mnf = f"{route_simple.group(1)}-{route_simple.group(2)}" if route_simple else "-"

    last_parent_pnr = "NO_PNR_PELITA"
    last_parent_name = ""

    for line in full_text.split("\n"):
        line_str = line.strip()
        if not line_str or line_str.startswith("CONFIDENTIAL") or line_str.startswith("MANIFEST") or line_str.startswith("TOTAL") or line_str.startswith("BAGGAGE") or line_str.startswith("WEIGHT") or line_str.startswith("QTY") or line_str.startswith("SSR") or "SEATOPTION" in line_str:
            continue

        if line_str.startswith("~"):
            infant_raw = line_str.replace("~", "").strip()
            infant_clean_str = re.sub(r"\s+\d+.*$", "", infant_raw).strip()
            infant_clean_str = re.split(r"[\d,]", infant_clean_str)[0].strip()
            clean_name = clean_passenger_name(infant_clean_str)

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": infant_clean_str,
                    "clean_nama_manifest": clean_name if clean_name else f"INFANT OF {last_parent_name}",
                    "seat_manifest": "INF",
                    "pnr_manifest": last_parent_pnr,
                    "type_manifest": "Infant",
                    "section": "BOARDED",
                    "is_matched": False
                })
            continue

        match_pax = re.search(r"^\d+\)\s+([A-Za-z\s\.-]+?)\s+(Mr|Mrs|Ms|Miss|Mstr)\.?\s*([A-Z0-9]{6})\s+[A-Z]\s+(\d{1,3}[A-Z])", line_str, re.IGNORECASE)
        if match_pax:
            raw_name = match_pax.group(1).strip()
            title = match_pax.group(2) if match_pax.group(2) else ""
            pnr_val = match_pax.group(3).strip().upper()
            seat_val = clean_seat_number(match_pax.group(4).strip())

            last_parent_pnr = pnr_val
            clean_name = clean_passenger_name(f"{raw_name} {title}".strip())
            last_parent_name = clean_name
            pax_type = "Child" if (title and title.upper().replace(".", "") in ["MSTR", "MISS"]) else "Adult"

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": f"{raw_name} {title}".strip(),
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_val,
                    "type_manifest": pax_type,
                    "section": "BOARDED",
                    "is_matched": False
                })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_china_airlines_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"\b(CI\s*\d{3,4})\s+(\d{1,2}[A-Z]{3})\s+([A-Z]{3})\b", full_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", "", fl_match.group(1).upper())
        flight_date_mnf = fl_match.group(2).upper()
        origin = fl_match.group(3).upper()
    else:
        fl_simple = re.search(r"\b(CI\s*\d{3,4})\b", full_text, re.IGNORECASE)
        if fl_simple:
            flight_no_mnf = re.sub(r"\s+", "", fl_simple.group(1).upper())
        date_simple = re.search(r"\b(\d{1,2}[A-Z]{3})\b", full_text, re.IGNORECASE)
        if date_simple:
            flight_date_mnf = date_simple.group(1).upper()

    dest_match = re.search(r"-([A-Z]{3})\s+\d+/\d+", full_text)
    if dest_match:
        destination = dest_match.group(1).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    pax_pattern = re.compile(r"^\s*(\d{1,3}[A-Z])/(?:[A-Z]{3})\s+(.*?)$", re.MULTILINE | re.IGNORECASE)

    for seat_raw, raw_name in pax_pattern.findall(full_text):
        raw_name = raw_name.strip()
        seat_raw = seat_raw.strip()
        if "CABIN TOTAL" in raw_name.upper() or "TOTAL PAX" in raw_name.upper():
            continue

        raw_name_upper = raw_name.upper()
        if re.search(r"\bCHD\b", raw_name_upper):
            pax_type = "Child"
        elif re.search(r"\bINF(?:ANT)?\b", raw_name_upper):
            pax_type = "Infant"
        else:
            pax_type = "Adult"

        clean_name = clean_passenger_name(raw_name)
        seat_clean = clean_seat_number(seat_raw)

        if len(clean_name) >= 2:
            manifest_data.append({
                "raw_nama_manifest": raw_name,
                "clean_nama_manifest": clean_name,
                "seat_manifest": seat_clean,
                "pnr_manifest": "-",
                "type_manifest": pax_type,
                "section": "BOARDED",
                "is_matched": False
            })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_korean_air_from_text(full_text):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    passenger_section_match = re.search(r"(Selected\s*List:.*|No\s*Customer.*)", full_text, re.DOTALL | re.IGNORECASE)
    working_text = passenger_section_match.group(1) if passenger_section_match else full_text

    fl_match = re.search(r"\b(KE\s*\d{3,4})\s+(\d{1,2}[A-Z]{3})\b", working_text, re.IGNORECASE) or re.search(r"\b(KE\s*\d{3,4})\s+(\d{1,2}[A-Z]{3})\b", full_text, re.IGNORECASE)
    if fl_match:
        flight_no_mnf = re.sub(r"\s+", "", fl_match.group(1).upper())
        flight_date_mnf = fl_match.group(2).upper()
    else:
        fl_simple = re.search(r"\b(KE\s*\d{3,4})\b", full_text, re.IGNORECASE)
        if fl_simple:
            flight_no_mnf = re.sub(r"\s+", "", fl_simple.group(1).upper())
        date_simple = re.search(r"\b(\d{1,2}[A-Z]{3})\b", full_text, re.IGNORECASE)
        if date_simple:
            flight_date_mnf = date_simple.group(1).upper()

    route_match = re.search(r"\b([A-Z]{3})\s*(?:\([^)]*\))?\s*([A-Z]{3})\b", working_text)
    if route_match:
        origin = route_match.group(1).upper()
        destination = route_match.group(2).upper()
    else:
        route_simple = re.search(r"(DPS|ICN)(DPS|ICN)", working_text)
        if route_simple:
            origin = route_simple.group(1).upper()
            destination = route_simple.group(2).upper()

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    pax_pattern = re.compile(
        r"(\d{1,3})\s*([A-Za-z\s\.\'-]+?)\s*(?:DPSICN|ICNDPS|DPS\s+ICN|ICN\s+DPS)\s*([CYF])\s*([0-9]{1,3}[A-Z]|INF|-|\d+)\s*Boarded",
        re.IGNORECASE
    )

    for num, raw_name, cabin_class, seat_raw in pax_pattern.findall(working_text):
        raw_name = raw_name.strip()
        seat_raw = seat_raw.strip()
        raw_name_upper = raw_name.upper()
        if re.search(r"\bINFANT\b", raw_name_upper):
            pax_type = "Infant"
        elif re.search(r"\bCHILD\b", raw_name_upper):
            pax_type = "Child"
        else:
            pax_type = "Adult"

        clean_name = clean_passenger_name(raw_name)
        seat_clean = clean_seat_number(seat_raw)

        if len(clean_name) >= 2:
            manifest_data.append({
                "raw_nama_manifest": raw_name,
                "clean_nama_manifest": clean_name,
                "seat_manifest": seat_clean,
                "pnr_manifest": "-",
                "type_manifest": pax_type,
                "section": "BOARDED",
                "is_matched": False
            })

    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def parse_manifest_chinese_hk_from_text(full_text, default_code="HX"):
    manifest_data = []
    flight_no_mnf = "-"
    flight_date_mnf = "-"
    origin = "-"
    destination = "-"

    fl_match = re.search(r"\b([A-Z0-9]{2})\s*[\/]?\s*(\d{3,4})\s*[\/,-]?\s*(\d{1,2}[A-Za-z]{3}\d{2})\b", full_text, re.IGNORECASE)
    if fl_match:
        airline_code = fl_match.group(1).upper()
        flight_no_mnf = f"{airline_code} {fl_match.group(2)}"
        flight_date_mnf = fl_match.group(3).upper()

    route_match = re.search(r"\b([A-Z]{3})\s*[\/\.-]\s*([A-Z]{3})\b", full_text)
    if route_match:
        origin = route_match.group(1).upper()
        destination = route_match.group(2).upper()

    pax_unit_pattern_general = re.compile(
        r"(?:(\d{3,4})\s+)?([A-Za-z\/\+\s\.-]+?)\s+(?:(\d{3,4})\s+)?(?:\b([CI])\b\s+)?([0-9]{1,3}[A-Z]|\d{2,3})",
        re.IGNORECASE
    )

    for line in full_text.split("\n"):
        line_str = line.strip()
        line_upper = line_str.upper()

        if not line_str or "PASSENGER LIST" in line_upper or "PAGE" in line_upper or "CLASS " in line_upper or "TOTAL " in line_upper or "ACFT RECN" in line_upper or "HONG KONG" in line_upper:
            continue

        for match in pax_unit_pattern_general.finditer(line_str):
            seq_front = match.group(1)
            raw_name = match.group(2).strip()
            seq_back = match.group(3)
            pax_code = match.group(4).upper() if match.group(4) else ""
            seat_raw = match.group(5).strip()

            pnr_seq = seq_front if seq_front else (seq_back if seq_back else "-")
            if pax_code == "C":
                pax_type = "Child"
            elif pax_code == "I":
                pax_type = "Infant"
            else:
                pax_type = "Adult"

            raw_name_clean = re.sub(r"\+$", "", raw_name).strip()
            clean_name = clean_passenger_name(raw_name_clean)
            seat_val = clean_seat_number(seat_raw) if pax_type != "Infant" else "INF"

            if len(clean_name) > 2:
                manifest_data.append({
                    "raw_nama_manifest": raw_name,
                    "clean_nama_manifest": clean_name,
                    "seat_manifest": seat_val,
                    "pnr_manifest": pnr_seq,
                    "type_manifest": pax_type,
                    "section": "BOARDED",
                    "is_matched": False
                })

    flight_route_mnf = f"{origin}-{destination}" if origin != "-" and destination != "-" else "-"
    return pd.DataFrame(manifest_data), flight_no_mnf, flight_date_mnf, flight_route_mnf


def calculate_name_score(tap_nama_raw, mnf_nama, same_seat=False):
    clean_tap = clean_passenger_name(tap_nama_raw)
    clean_mnf = clean_passenger_name(mnf_nama)

    if not clean_tap or not clean_mnf:
        clean_tap = re.sub(r"[^A-Z]", "", str(tap_nama_raw).upper())
        clean_mnf = re.sub(r"[^A-Z]", "", str(mnf_nama).upper())

    words_tap = clean_tap.split()
    words_mnf = clean_mnf.split()

    if len(words_tap) >= 1 and len(words_mnf) >= 1:
        if words_tap[-1] == words_mnf[-1]:
            w1, w2 = words_tap[0], words_mnf[0]
            if (len(w1) >= 3 and len(w2) >= 3) and (w1.startswith(w2) or w2.startswith(w1)):
                return 95

    s_sort = fuzz.token_sort_ratio(clean_tap, clean_mnf)
    s_set = fuzz.token_set_ratio(clean_tap, clean_mnf)
    s_ratio = fuzz.ratio(clean_tap.replace(" ", ""), clean_mnf.replace(" ", ""))

    tap_no_space = clean_tap.replace(" ", "")
    mnf_no_space = clean_mnf.replace(" ", "")

    if same_seat:
        if tap_no_space == mnf_no_space or tap_no_space in mnf_no_space or mnf_no_space in tap_no_space:
            return 98

        raw_tap_ns = re.sub(r"[^A-Z]", "", str(tap_nama_raw).upper())
        raw_mnf_ns = re.sub(r"[^A-Z]", "", str(mnf_nama).upper())
        raw_no_space_ratio = fuzz.ratio(raw_tap_ns, raw_mnf_ns)

        if raw_no_space_ratio >= 70 or s_ratio >= 70 or s_set >= 70:
            return max(raw_no_space_ratio, s_ratio, s_set, s_sort)

        if len(words_tap) >= 1 and len(words_mnf) >= 1:
            if words_tap[0] == words_mnf[0] or words_tap[-1] == words_mnf[-1]:
                if s_sort >= 45 or s_set >= 45 or s_ratio >= 45:
                    return max(s_sort, s_set, s_ratio)

        if s_sort >= 60 or s_set >= 65:
            return max(s_sort, s_set)

        return 0

    if len(words_tap) >= 3 and len(words_mnf) >= 3:
        if words_tap[-1] != words_mnf[-1] and not (words_tap[-1].startswith(words_mnf[-1]) or words_mnf[-1].startswith(words_tap[-1])):
            return min(s_sort, s_ratio)

    if len(words_tap) >= 2 and len(words_mnf) >= 2:
        if words_tap[0] == words_mnf[0] and words_tap[-1] == words_mnf[-1]:
            return max(88, s_sort, s_set)

    if tap_no_space == mnf_no_space or tap_no_space in mnf_no_space or mnf_no_space in tap_no_space:
        return 90

    common_words = {"MUHAMMAD", "MOHAMMAD", "MUHAMAD", "ABDUL", "SITI", "NUR", "AHMAD", "INFANT", "OF", "WAYAN", "NI"}
    significant_tap = set(words_tap) - common_words
    significant_mnf = set(words_mnf) - common_words

    if not significant_tap.intersection(significant_mnf):
        has_prefix = False
        for wt in significant_tap:
            for wm in significant_mnf:
                if len(wt) >= 2 and len(wm) >= 2 and (wt.startswith(wm) or wm.startswith(wt)):
                    has_prefix = True
                    break
            if has_prefix:
                break
        if not has_prefix:
            return 0

    return max(s_sort, s_set, s_ratio)


def reconcile_engine(df_tapping, df_manifest, airline_name):
    if df_tapping.empty and df_manifest.empty:
        return pd.DataFrame()

    results = []
    df_manifest["is_matched"] = False
    processed_tap_indices = set()
    is_lion_group = "LION" in airline_name.upper() or any(code in airline_name.upper() for code in ["JT", "IW", "ID", "IU", "OD", "SL"])

    # TAHAP 1: EXACT SEAT MATCH
    for idx, tap in df_tapping.iterrows():
        tap_nama_raw = str(tap.get("NAME", tap.get("NAMA", tap.get("PASSENGER NAME", "")))).strip()
        tap_seat = clean_seat_number(str(tap.get("SEAT", tap.get("NO SEAT", ""))).strip().replace(".", ""))
        tap_pnr = str(tap.get("PNR", tap.get("NO PNR", ""))).strip()

        raw_type = str(tap.get("TYPE", tap.get("PAX TYPE", "Adult"))).strip()
        raw_cat = str(tap.get("CATEGORY", "")).strip()
        is_transit = "TRANSIT" in raw_cat.upper() or "TRANSIT" in raw_type.upper()
        tap_type_final = determine_pax_type(raw_type, is_transit)

        if tap_seat == "-" or tap_seat == "INF":
            continue

        available_manifest = df_manifest[~df_manifest["is_matched"]]
        if available_manifest.empty:
            break

        same_seat_rows = available_manifest[available_manifest["seat_manifest"] == tap_seat]
        if not same_seat_rows.empty:
            best_score = 0
            best_m_idx = None
            for m_idx, m_row in same_seat_rows.iterrows():
                score = calculate_name_score(tap_nama_raw, m_row["clean_nama_manifest"], same_seat=True)
                if score >= 45 and score > best_score:
                    best_score = score
                    best_m_idx = m_idx

            if best_m_idx is not None:
                df_manifest.at[best_m_idx, "is_matched"] = True
                processed_tap_indices.add(idx)
                m_row = df_manifest.loc[best_m_idx]

                m_section = str(m_row.get("section", "")).upper()
                if m_section in ["NO_SHOW", "THRU_NO_SHOW", "N"]:
                    status = "OFFLOAD"
                    catatan = f"Offload (Penumpang No Show / Kode N pada seat {tap_seat})"
                else:
                    status = "MATCH"
                    catatan = "Match Perfect (Seat & Name Match)"

                results.append({
                    "NAMA SCAN": tap_nama_raw,
                    "SEAT SCAN": tap_seat,
                    "PNR SCAN": tap_pnr,
                    "TYPE SCAN": tap_type_final,
                    "NAMA MANIFEST": m_row["clean_nama_manifest"],
                    "SEAT MANIFEST": m_row["seat_manifest"],
                    "PNR MANIFEST": m_row["pnr_manifest"],
                    "TYPE MANIFEST": m_row["type_manifest"],
                    "HASIL": status,
                    "CATATAN": catatan
                })

    # TAHAP 2: INFANT, CHANGE SEAT, OFFLOAD, CONFIRMATION
    for idx, tap in df_tapping.iterrows():
        if idx in processed_tap_indices:
            continue

        tap_nama_raw = str(tap.get("NAME", tap.get("NAMA", tap.get("PASSENGER NAME", "")))).strip()
        tap_seat = clean_seat_number(str(tap.get("SEAT", tap.get("NO SEAT", ""))).strip().replace(".", ""))
        tap_pnr = str(tap.get("PNR", tap.get("NO PNR", ""))).strip()

        raw_type = str(tap.get("TYPE", tap.get("PAX TYPE", "Adult"))).strip()
        raw_cat = str(tap.get("CATEGORY", "")).strip()
        is_transit = "TRANSIT" in raw_cat.upper() or "TRANSIT" in raw_type.upper()
        tap_type_final = determine_pax_type(raw_type, is_transit)

        matched_idx = None
        status = ""
        catatan = ""
        available_manifest = df_manifest[~df_manifest["is_matched"]]

        is_tap_infant = (tap_seat == "INF" or "INFANT" in tap_type_final.upper())
        infant_manifests = available_manifest[
            (available_manifest["seat_manifest"] == "INF") |
            (available_manifest["type_manifest"].str.contains("Infant", case=False))
        ]

        if is_tap_infant or not infant_manifests.empty:
            best_inf_score = 0
            best_inf_idx = None
            for m_idx, m_row in infant_manifests.iterrows():
                m_pnr = str(m_row.get("pnr_manifest", "")).strip()
                if tap_pnr != "-" and tap_pnr != "" and tap_pnr == m_pnr:
                    best_inf_idx = m_idx
                    break
                score = calculate_name_score(tap_nama_raw, m_row["clean_nama_manifest"])
                if score >= 50 and score > best_inf_score:
                    best_inf_score = score
                    best_inf_idx = m_idx

            if best_inf_idx is not None:
                matched_idx = best_inf_idx
                status = "INFANT"
                catatan = f"Match Infant Pax (Seat Scan {tap_seat})"

        if matched_idx is None and tap_seat != "INF" and not available_manifest.empty:
            best_name_score = 0
            best_name_idx = None
            for m_idx, m_row in available_manifest.iterrows():
                if m_row["seat_manifest"] == "INF":
                    continue
                score = calculate_name_score(tap_nama_raw, m_row["clean_nama_manifest"], same_seat=False)
                if score >= 85 and score > best_name_score:
                    best_name_score = score
                    best_name_idx = m_idx

            if best_name_idx is not None:
                matched_idx = best_name_idx
                mnf_seat = df_manifest.loc[matched_idx, "seat_manifest"]
                m_section = str(df_manifest.loc[matched_idx, "section"]).upper()

                if m_section in ["NO_SHOW", "THRU_NO_SHOW", "N"]:
                    status = "OFFLOAD"
                    catatan = f"Offload (Penumpang No Show di seat manifest {mnf_seat})"
                else:
                    status = "CHANGE SEAT"
                    catatan = f"Penumpang di scan seat {tap_seat} dan di manifest seat {mnf_seat}"

        if matched_idx is not None:
            df_manifest.at[matched_idx, "is_matched"] = True
            match_row = df_manifest.loc[matched_idx]
            results.append({
                "NAMA SCAN": tap_nama_raw,
                "SEAT SCAN": tap_seat,
                "PNR SCAN": tap_pnr,
                "TYPE SCAN": tap_type_final,
                "NAMA MANIFEST": match_row["clean_nama_manifest"],
                "SEAT MANIFEST": match_row["seat_manifest"],
                "PNR MANIFEST": match_row["pnr_manifest"],
                "TYPE MANIFEST": match_row["type_manifest"],
                "HASIL": status,
                "CATATAN": catatan
            })
        else:
            prev_matches = [
                r for r in results
                if r["NAMA SCAN"] != "-" and
                clean_passenger_name(r["NAMA SCAN"]) == clean_passenger_name(tap_nama_raw) and
                ("MATCH" in r["HASIL"] or "INFANT" in r["HASIL"])
            ]

            if prev_matches:
                prev_seat = prev_matches[0]["SEAT SCAN"]
                prev_mnf_seat = prev_matches[0]["SEAT MANIFEST"]
                seat_ref = prev_seat if prev_seat != "-" else prev_mnf_seat

                if is_lion_group or tap_seat != seat_ref:
                    status = "OFFLOAD"
                    catatan = f"Pax Tapping 2x. Seat Match {seat_ref}"
                else:
                    status = "CONFIRMATION"
                    catatan = f"Double Tapping / Scan 2x (Penumpang sudah Match di Seat {seat_ref})"
            elif tap_seat == "INF" or "INFANT" in tap_type_final.upper():
                status = "INFANT"
                catatan = "Infant Scan Tidak Ada di Manifest"
            else:
                if is_lion_group:
                    status = "OFFLOAD"
                    catatan = "Offload (Seat/Pax tidak ada di manifest Lion Group)"
                else:
                    status = "CONFIRMATION"
                    catatan = "Confirmation (Seat & Nama scan tidak ditemukan di manifest)"

            results.append({
                "NAMA SCAN": tap_nama_raw,
                "SEAT SCAN": tap_seat,
                "PNR SCAN": tap_pnr,
                "TYPE SCAN": tap_type_final,
                "NAMA MANIFEST": "-",
                "SEAT MANIFEST": "-",
                "PNR MANIFEST": "-",
                "TYPE MANIFEST": "-",
                "HASIL": status,
                "CATATAN": catatan
            })

    # TAHAP 3: MANIFEST YANG TIDAK DI-SCAN (NOT SCAN)
    unscanned = df_manifest[~df_manifest["is_matched"]]
    for _, mnf in unscanned.iterrows():
        mnf_type = mnf.get("type_manifest", "Adult")
        mnf_seat = mnf.get("seat_manifest", "-")
        mnf_section = str(mnf.get("section", "")).upper()

        if mnf_type == "Infant" or mnf_seat == "INF":
            results.append({
                "NAMA SCAN": "-", "SEAT SCAN": "-", "PNR SCAN": "-", "TYPE SCAN": "-",
                "NAMA MANIFEST": mnf["clean_nama_manifest"], "SEAT MANIFEST": mnf["seat_manifest"],
                "PNR MANIFEST": mnf["pnr_manifest"], "TYPE MANIFEST": mnf["type_manifest"],
                "HASIL": "INFANT", "CATATAN": "Pax Infant (Manifest Only)"
            })
        else:
            catatan_not_scan = "Passenger No Show Not Scan" if (mnf_section in ["NO_SHOW", "THRU_NO_SHOW"] or mnf_seat == "-") else "Passenger did not scan / Ghost Pax"
            results.append({
                "NAMA SCAN": "-", "SEAT SCAN": "-", "PNR SCAN": "-", "TYPE SCAN": "-",
                "NAMA MANIFEST": mnf["clean_nama_manifest"], "SEAT MANIFEST": mnf["seat_manifest"],
                "PNR MANIFEST": mnf["pnr_manifest"], "TYPE MANIFEST": mnf["type_manifest"],
                "HASIL": "NOT SCAN", "CATATAN": catatan_not_scan
            })

    df_res = pd.DataFrame(results)
    if not df_res.empty:
        df_res["effective_seat"] = df_res.apply(
            lambda r: r["SEAT SCAN"] if r["SEAT SCAN"] != "-" else r["SEAT MANIFEST"], axis=1
        )
        df_res["sort_key"] = df_res["effective_seat"].apply(seat_sort_key)
        df_res = df_res.sort_values(by="sort_key").reset_index(drop=True)
        df_res["NO"] = df_res.index + 1

        cols = [
            "NO", "NAMA SCAN", "SEAT SCAN", "PNR SCAN", "TYPE SCAN",
            "NAMA MANIFEST", "SEAT MANIFEST", "PNR MANIFEST", "TYPE MANIFEST",
            "HASIL", "CATATAN"
        ]
        df_res = df_res[cols]

    return df_res


def run_pax_reconciliation(tapping_items, manifest_filename, manifest_bytes):
    df_tapping, scan_summary_text = load_multiple_tapping_files(tapping_items)
    if df_tapping.empty:
        return {"error": "Data Gate Tapping tidak berhasil terbaca atau kosong."}

    (df_manifest, flight_no_mnf, flight_date_mnf, flight_route_mnf), detected_airline = detect_and_parse_manifest(
        manifest_filename, manifest_bytes
    )
    if df_manifest.empty:
        return {"error": "Data Manifest PDF/TXT tidak berhasil terbaca atau kosong."}

    df_result = reconcile_engine(df_tapping, df_manifest, detected_airline)

    clean_airline_display = detected_airline.split("(")[0].strip()
    manifest_card_val = f"{flight_no_mnf} ({flight_route_mnf})"

    mnf_adult = int(len(df_manifest[df_manifest["type_manifest"].str.contains("Adult")]))
    mnf_child = int(len(df_manifest[df_manifest["type_manifest"].str.contains("Child")]))
    mnf_infant = int(len(df_manifest[df_manifest["type_manifest"].str.contains("Infant")]))
    mnf_transit = int(len(df_manifest[df_manifest["type_manifest"].str.contains("Transit")]))

    is_lion = "LION" in detected_airline.upper()
    cnt_manifest_total = (mnf_adult + mnf_child + mnf_infant) if is_lion else int(len(df_manifest))

    cnt_scan = int(len(df_result[df_result["NAMA SCAN"] != "-"]))
    cnt_match = int(len(df_result[df_result["HASIL"] == "MATCH"]))
    cnt_offload = int(len(df_result[df_result["HASIL"] == "OFFLOAD"]))
    cnt_seat_conflict = int(len(df_result[df_result["HASIL"] == "CHANGE SEAT"]))
    cnt_not_scan = int(len(df_result[df_result["HASIL"] == "NOT SCAN"]))
    cnt_infant = int(len(df_result[df_result["HASIL"] == "INFANT"]))
    cnt_confirm = int(len(df_result[df_result["HASIL"] == "CONFIRMATION"]))

    df_scan_only = df_result[df_result["NAMA SCAN"] != "-"]
    scan_adult = int(len(df_scan_only[df_scan_only["TYPE SCAN"].str.contains("Adult")]))
    scan_child = int(len(df_scan_only[df_scan_only["TYPE SCAN"].str.contains("Child")]))
    scan_infant = int(len(df_scan_only[df_scan_only["TYPE SCAN"].str.contains("Infant")]))
    scan_transit = int(len(df_scan_only[df_scan_only["TYPE SCAN"].str.contains("Transit")]))

    records = df_result.fillna("-").to_dict(orient="records")

    return {
        "flight_detail": {
            "airline": clean_airline_display,
            "airline_full": detected_airline,
            "flight_no": flight_no_mnf,
            "route": flight_route_mnf,
            "date": flight_date_mnf,
            "scan_summary": scan_summary_text,
            "manifest_summary": manifest_card_val,
        },
        "summary_counts": {
            "scan": cnt_scan,
            "manifest": cnt_manifest_total,
            "match": cnt_match,
            "offload": cnt_offload,
            "change_seat": cnt_seat_conflict,
            "not_scan": cnt_not_scan,
            "infant": cnt_infant,
            "confirmation": cnt_confirm,
        },
        "pax_types": {
            "scan": {
                "adult": scan_adult,
                "child": scan_child,
                "infant": scan_infant,
                "transit": scan_transit,
            },
            "manifest": {
                "adult": mnf_adult,
                "child": mnf_child,
                "infant": mnf_infant,
                "transit": mnf_transit,
            },
        },
        "records": records,
    }


def generate_excel_bytes(records):
    df = pd.DataFrame(records)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Rekonsiliasi")
    output.seek(0)
    return output