import re
from datetime import date
from typing import Dict, Any, List, Optional
from app.engine.pipelines.common import make_field, normalize_date, DATE_PATTERN


def compute_mrz_check_digit(chars: str) -> int:
    """ICAO 9303 check digit calculation with weights [7, 3, 1]."""
    weights = [7, 3, 1]
    total = 0
    for idx, c in enumerate(chars):
        if c.isdigit():
            val = int(c)
        elif c.isalpha():
            val = ord(c.upper()) - 55  # 'A' -> 10
        else:
            val = 0  # '<' filler
        total += val * weights[idx % 3]
    return total % 10


def build_td3_mrz(surname: str, given_names: str, country: str, doc_number: str, nationality: str,
                  dob_yymmdd: str, sex: str, expiry_yymmdd: str, personal_number: str = "") -> List[str]:
    """Builds a valid ICAO 9303 TD3 (passport) MRZ, check digits included."""
    name = surname.upper().replace(" ", "<") + "<<" + given_names.upper().replace(" ", "<")
    line1 = ("P<" + country.upper() + name).ljust(44, "<")[:44]
    num = doc_number.upper().ljust(9, "<")[:9]
    pers = personal_number.upper().ljust(14, "<")[:14]
    pers_check = "<" if not personal_number else str(compute_mrz_check_digit(pers))
    line2 = (num + str(compute_mrz_check_digit(num)) + nationality.upper() +
             dob_yymmdd + str(compute_mrz_check_digit(dob_yymmdd)) + sex.upper() +
             expiry_yymmdd + str(compute_mrz_check_digit(expiry_yymmdd)) + pers + pers_check)
    composite = line2[0:10] + line2[13:20] + line2[21:43]
    return [line1, line2 + str(compute_mrz_check_digit(composite))]


def _yymmdd_to_iso(s: str, future: bool) -> Optional[str]:
    """Converts YYMMDD to ISO. Birth dates resolve to the past, expiry dates to this century."""
    if not re.fullmatch(r"\d{6}", s):
        return None
    yy = int(s[0:2])
    century = 2000 if future or yy <= date.today().year % 100 else 1900
    try:
        return date(century + yy, int(s[2:4]), int(s[4:6])).isoformat()
    except ValueError:
        return None


def _check(field: str, check_char: str) -> bool:
    return check_char.isdigit() and compute_mrz_check_digit(field) == int(check_char)


class IdentityPipeline:
    @staticmethod
    def process(text: str, words_with_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        fields = {}
        metadata: Dict[str, Any] = {}

        # ICAO TD3 MRZ: two 44-character lines, e.g.
        #   P<USASMITH<<JOHN<MICHAEL<<<<<<<<<<<<<<<<<<<<
        #   5639274181USA8501019M3001019<<<<<<<<<<<<<<<0
        candidates = [re.sub(r"\s+", "", l).replace("«", "<").upper() for l in text.splitlines()]
        l1 = next((c for c in candidates if len(c) >= 40 and re.fullmatch(r"P[A-Z<][A-Z<]{3}[A-Z<]+", c[:44])), None)
        l2 = next((c for c in candidates if re.fullmatch(r"[A-Z0-9<]{9}\d[A-Z<]{3}\d{6}\d[MFX<]\d{6}\d[A-Z0-9<]{14}[\d<]\d", c[:44])), None)

        if l1 and l2:
            l1, l2 = l1[:44].ljust(44, "<"), l2[:44]
            issuing_country = l1[2:5].replace("<", "")
            name_split = l1[5:].split("<<", 1)
            surname = name_split[0].replace("<", " ").strip()
            given_names = name_split[1].replace("<", " ").strip() if len(name_split) > 1 else ""
            full_name = f"{given_names} {surname}".strip()

            doc_number = l2[0:9].replace("<", "")
            nationality = l2[10:13].replace("<", "")
            dob = _yymmdd_to_iso(l2[13:19], future=False)
            sex = l2[20] if l2[20] in ["M", "F"] else "X"
            exp_date = _yymmdd_to_iso(l2[21:27], future=True)

            checks = {
                "document_number": _check(l2[0:9], l2[9]),
                "date_of_birth": _check(l2[13:19], l2[19]),
                "date_of_expiry": _check(l2[21:27], l2[27]),
                "personal_number": l2[42] == "<" or _check(l2[28:42], l2[42]),
                "composite": _check(l2[0:10] + l2[13:20] + l2[21:43], l2[43]),
            }
            failed = [k for k, ok in checks.items() if not ok]
            checksum_valid = not failed
            is_expired = bool(exp_date) and date.fromisoformat(exp_date) < date.today()

            # Cross-check the MRZ against the printed (visual) zone
            visual = "\n".join(l for l in text.splitlines() if "<<" not in l)
            visual_mismatch = []
            if doc_number and doc_number not in visual.replace(" ", ""):
                visual_mismatch.append("document number")
            if surname and surname.split()[0] not in visual.upper():
                visual_mismatch.append("surname")

            conf = 0.98 if checksum_valid else 0.7
            fields["document_type"] = make_field("document_type", "Document Type", "PASSPORT", 0.99, "enum")
            fields["full_name"] = make_field("full_name", "Full Legal Name", full_name, conf, "text", words_with_boxes,
                                             box_phrase=surname, required=True,
                                             validation_error=f"MRZ does not match printed {', '.join(visual_mismatch)}." if visual_mismatch else None)
            fields["document_number"] = make_field("document_number", "Document / Passport Number", doc_number,
                                                   0.99 if checks["document_number"] else 0.6, "text", words_with_boxes, required=True,
                                                   validation_error=None if checks["document_number"] else "Document number check digit does not match.")
            fields["issuing_country"] = make_field("issuing_country", "Issuing Country (ISO Code)", issuing_country, conf, "text", required=True)
            fields["nationality"] = make_field("nationality", "Nationality", nationality, conf, "text", required=True)
            fields["date_of_birth"] = make_field("date_of_birth", "Date of Birth", dob, 0.97 if checks["date_of_birth"] else 0.6, "date",
                                                 words_with_boxes, required=True,
                                                 validation_error=None if checks["date_of_birth"] else "Date of birth check digit does not match.")
            exp_err = "Document has expired." if is_expired else (None if checks["date_of_expiry"] else "Expiry date check digit does not match.")
            fields["date_of_expiry"] = make_field("date_of_expiry", "Expiration Date", exp_date, 0.97 if checks["date_of_expiry"] else 0.6,
                                                  "date", words_with_boxes, required=True, validation_error=exp_err)
            fields["sex"] = make_field("sex", "Sex / Gender", sex, conf, "enum")
            fields["mrz_checksum_valid"] = make_field("mrz_checksum_valid", "MRZ Checksum Verified", "PASS" if checksum_valid else "FAIL",
                                                      1.0, "enum", words_with_boxes, box_phrase=l2,
                                                      validation_error=None if checksum_valid else f"MRZ check digit mismatch: {', '.join(failed)}.")
            metadata.update({"mrz_lines": [l1, l2], "mrz_checks": checks, "is_expired": is_expired,
                             "visual_zone_mismatch": visual_mismatch})
        else:
            # No MRZ: read labelled fields from ID cards / driving licences. Nothing is guessed.
            def find(pattern: str) -> Optional[str]:
                m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
                return m.group(1).strip() if m else None

            full_name = find(r"^\s*(?:FULL\s+)?NAME\s*[:\-]\s*([A-Za-z][A-Za-z ,.'\-]+)$")
            if not full_name:
                ln = find(r"^\s*(?:LN|SURNAME|LAST\s+NAME)\s*[:\-]?\s*([A-Za-z'\-]+)")
                fn = find(r"^\s*(?:FN|GIVEN\s+NAMES?|FIRST\s+NAME)\s*[:\-]?\s*([A-Za-z' \-]+)")
                full_name = " ".join(x for x in [fn, ln] if x) or None
            doc_num = find(r"(?:LIC(?:ENSE|ENCE)?|DL|ID|DOCUMENT|PASSPORT)\s*(?:NO\.?|NUMBER|#)\s*[:\-]?\s*([A-Z0-9\-]{4,})")
            dob_raw = find(r"(?:DOB|DATE\s+OF\s+BIRTH|BIRTH\s+DATE)\s*[:\-]?\s*(" + DATE_PATTERN + ")")
            exp_raw = find(r"(?:EXP(?:IRY|IRATION)?(?:\s+DATE)?|EXPIRES|VALID\s+UNTIL)\s*[:\-]?\s*(" + DATE_PATTERN + ")")
            sex = find(r"\bSEX\s*[:\-]?\s*([MFX])\b")
            country = find(r"(?:ISSUING\s+COUNTRY|COUNTRY)\s*[:\-]\s*([A-Z]{2,3})\b")
            nationality = find(r"NATIONALITY\s*[:\-]\s*([A-Za-z ]+)$")
            exp_iso = normalize_date(exp_raw)
            lower = text.lower()
            doc_type = "DRIVERS_LICENSE" if ("licen" in lower or "driver" in lower) else ("NATIONAL_ID" if "identity" in lower else None)
            is_expired = bool(exp_iso) and date.fromisoformat(exp_iso) < date.today()

            fields["document_type"] = make_field("document_type", "Document Type", doc_type, 0.8, "enum", required=True)
            fields["full_name"] = make_field("full_name", "Full Legal Name", full_name, 0.85, "text", words_with_boxes, required=True)
            fields["document_number"] = make_field("document_number", "Document / Passport Number", doc_num, 0.85, "text", words_with_boxes, required=True)
            fields["issuing_country"] = make_field("issuing_country", "Issuing Country (ISO Code)", country, 0.8, "text", words_with_boxes)
            fields["nationality"] = make_field("nationality", "Nationality", nationality, 0.8, "text", words_with_boxes)
            fields["date_of_birth"] = make_field("date_of_birth", "Date of Birth", normalize_date(dob_raw) or dob_raw, 0.85, "date",
                                                 words_with_boxes, box_phrase=dob_raw, required=True)
            fields["date_of_expiry"] = make_field("date_of_expiry", "Expiration Date", exp_iso or exp_raw, 0.85, "date", words_with_boxes,
                                                  box_phrase=exp_raw, required=True,
                                                  validation_error="Document has expired." if is_expired else None)
            fields["sex"] = make_field("sex", "Sex / Gender", sex, 0.85, "enum", words_with_boxes)
            fields["mrz_checksum_valid"] = make_field("mrz_checksum_valid", "MRZ Checksum Verified", "N/A", 1.0, "enum",
                                                      validation_error="No machine-readable zone found; verify identity fields manually.")
            metadata["is_expired"] = is_expired

        return {"fields": fields, "metadata": metadata}
