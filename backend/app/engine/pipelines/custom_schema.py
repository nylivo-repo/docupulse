import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from app.engine.ocr_extractor import OCRExtractor
from app.engine.pipelines.common import normalize_ws, normalize_date, parse_amount, DATE_PATTERN
from app.engine.pipelines.generic import extract_key_values, slugify


def _words_in_region(region: Dict[str, Any], words_with_boxes: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Returns the text of words whose centre falls inside a template region (percent coordinates)."""
    page = region.get("page", 1)
    inside = [w for w in words_with_boxes
              if w["page"] == page
              and region["x0"] <= (w["x0"] + w["x1"]) / 2 <= region["x1"]
              and region["y0"] <= (w["y0"] + w["y1"]) / 2 <= region["y1"]]
    if not inside:
        return None, None
    inside.sort(key=lambda w: (round(w["y0"]), w["x0"]))
    box = {"page": page, "x0": min(w["x0"] for w in inside), "y0": min(w["y0"] for w in inside),
           "x1": max(w["x1"] for w in inside), "y1": max(w["y1"] for w in inside)}
    return " ".join(w["text"] for w in inside), box


def coerce_value(value: Any, d_type: str, enum_vals: List[str]) -> Tuple[Any, Optional[str]]:
    """Converts a raw string to the field's type. Returns (value, validation_error)."""
    if value is None:
        return None, None
    raw = str(value).strip()
    if d_type == "date":
        iso = normalize_date(raw)
        if iso:
            return iso, None
        m = re.search(DATE_PATTERN, raw)
        if m and normalize_date(m.group(0)):
            return normalize_date(m.group(0)), None
        return raw, f"'{raw}' is not a recognizable date."
    if d_type in ("number", "currency"):
        m = re.search(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", raw)
        if not m:
            return raw, f"'{raw}' is not a number."
        num = parse_amount(m.group(0))
        if d_type == "number" and num is not None and float(num).is_integer():
            num = int(num)
        return num, None
    if d_type == "enum" and enum_vals:
        for ev in enum_vals:
            if raw.lower() == ev.lower():
                return ev, None
        for ev in enum_vals:
            if re.search(rf"\b{re.escape(ev)}\b", raw, re.IGNORECASE):
                return ev, None
        return raw, f"'{raw}' is not one of: {', '.join(enum_vals)}"
    return raw, None


class CustomSchemaPipeline:
    """
    Template-driven extraction. Each template field is located, in order, by its regex pattern,
    its page region (templates saved from a sample document), or its label and aliases.
    """

    @staticmethod
    def process(text: str, words_with_boxes: List[Dict[str, Any]], schema_fields: List[Dict[str, Any]]) -> Dict[str, Any]:
        fields = {}
        missing_required = []
        kv_pairs = extract_key_values(text)
        kv_by_key = {}
        for kv in kv_pairs:
            kv_by_key.setdefault(kv["key"], kv)  # the first occurrence of a repeated label wins

        for f_def in schema_fields:
            name = f_def.get("name")
            label = f_def.get("label") or name
            d_type = f_def.get("data_type", "text")
            required = f_def.get("required", False)
            regex_pat = f_def.get("regex_pattern")
            threshold = f_def.get("confidence_threshold", 0.75)
            enum_vals = f_def.get("enum_values") or []
            aliases = [a for a in (f_def.get("aliases") or []) if a]
            region = f_def.get("region")

            val, conf, box, method = None, 0.0, None, None

            # 0. Fields drawn on the page in Review: their position is the most reliable cue
            if region and f_def.get("locate") == "region":
                val, box = _words_in_region(region, words_with_boxes)
                if val:
                    conf, method = 0.88, "region"

            # 1. Explicit regex pattern
            if val is None and regex_pat:
                try:
                    m = re.search(regex_pat, text, re.IGNORECASE | re.MULTILINE)
                    if m:
                        val = (m.group(1) if m.groups() else m.group(0)).strip()
                        conf, method = 0.95, "regex"
                except re.error as e:
                    logging.getLogger("idp.extract").warning("Template regex error for field %s: %s", name, e)

            # 2. Labelled value, "Label: value", matched on label, aliases or field name
            if val is None:
                for cand in [label, *aliases, name.replace("_", " ")]:
                    kv = kv_by_key.get(slugify(cand))
                    if kv:
                        val, conf, method = kv["value"], 0.9, "label"
                        break

            # 3. Label followed by its value on the same line, without a colon
            if val is None:
                for cand in [label, *aliases]:
                    m = re.search(rf"^\s*{re.escape(cand)}\s*(?:#|No\.?|-)?\s+(\S.{{0,80}}?)\s*$", text, re.IGNORECASE | re.MULTILINE)
                    if m:
                        val, conf, method = m.group(1), 0.8, "label_line"
                        break

            # 4. Fixed page region from a template saved off a sample document
            if val is None and region and f_def.get("locate") != "region":
                val, box = _words_in_region(region, words_with_boxes)
                if val:
                    conf, method = 0.85, "region"

            # 5. An enum value mentioned anywhere
            if val is None and d_type == "enum" and enum_vals:
                for ev in enum_vals:
                    if re.search(rf"\b{re.escape(ev)}\b", text, re.IGNORECASE):
                        val, conf, method = ev, 0.7, "enum_scan"
                        break

            val_err = None
            if val is None:
                if required:
                    val_err = f"Required field '{label}' was not found in the document."
                    missing_required.append(name)
            else:
                if box is None:  # locate the text as written, before it is normalized
                    box = OCRExtractor.find_phrase_box(str(val), words_with_boxes) or \
                          OCRExtractor.find_phrase_box(" ".join(normalize_ws(str(val)).split()[:4]), words_with_boxes)
                val, val_err = coerce_value(val, d_type, enum_vals)
                if val_err:
                    conf = min(conf, 0.5)
                if conf < threshold and not val_err:
                    val_err = f"Extraction confidence ({int(conf * 100)}%) is below the required threshold ({int(threshold * 100)}%)."

            fields[name] = {
                "field_name": name,
                "display_name": label,
                "value": val,
                "confidence": round(conf, 2),
                "bounding_box": box,
                "field_type": d_type,
                "validation_error": val_err,
                "extraction_method": method,
            }

        # Labelled values in the document that the template does not cover, for building templates further
        covered = {slugify(f.get("label") or "") for f in schema_fields} | {f.get("name") for f in schema_fields}
        for f in schema_fields:
            covered |= {slugify(a) for a in (f.get("aliases") or [])}
        extra = [{"label": kv["label"], "value": kv["value"]} for kv in kv_pairs if kv["key"] not in covered]

        return {
            "fields": fields,
            "metadata": {
                "custom_schema_evaluation": True,
                "missing_required_fields": missing_required,
                "unmapped_key_values": extra[:50],
            }
        }
