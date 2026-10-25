import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.engine.ocr_extractor import OCRExtractor

DATE_PATTERN = r"(?:[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"

_DATE_FORMATS = [
    "%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y", "%b. %d, %Y",
    "%d %B %Y", "%d %b %Y", "%d %B, %Y", "%m/%d/%Y", "%m/%d/%y", "%d.%m.%Y", "%m-%d-%Y",
    "%d%b%y", "%d%b%Y", "%d-%b-%Y", "%d-%b-%y",  # hotel / airline style: 13Jul26, 13-Jul-2026
]


def normalize_ws(text: str) -> str:
    """Collapses all whitespace (including line breaks) to single spaces."""
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_date(value: Optional[str]) -> Optional[str]:
    """Returns an ISO date (YYYY-MM-DD) when the value parses, else None."""
    if not value:
        return None
    v = normalize_ws(str(value))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_amount(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(str(value).replace(",", "").replace("$", "").replace("€", "").replace("£", "").strip()), 2)
    except ValueError:
        return None


def make_field(name: str, label: str, value: Any, confidence: float, field_type: str = "text",
               words_with_boxes: Optional[List[Dict[str, Any]]] = None, box_phrase: Optional[str] = None,
               validation_error: Optional[str] = None, required: bool = False) -> Dict[str, Any]:
    """Builds an extracted field. A value that was not found is None with zero confidence, never a guess."""
    if value is None or value == "":
        value = None
        confidence = 0.0
        if required and not validation_error:
            validation_error = f"Required field '{label}' was not found in the document."
    box = None
    if value is not None and words_with_boxes:
        box = OCRExtractor.find_phrase_box(box_phrase or str(value), words_with_boxes)
    return {
        "field_name": name,
        "display_name": label,
        "value": value,
        "confidence": round(confidence, 2),
        "bounding_box": box,
        "field_type": field_type,
        "validation_error": validation_error,
    }
