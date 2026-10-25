import re
from typing import Dict, Any, List, Optional, Tuple
from app.engine.pipelines.common import make_field, normalize_ws, normalize_date, parse_amount, DATE_PATTERN

_LABEL = re.compile(r"(?:(?<=^)|(?<=\s))([A-Za-z][\w/&().#'\-]*(?:\s[A-Za-z][\w/&().#'\-]*){0,3}?)\s?[:：](?=\s|$)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<![\w-])\+?\(?\d[\d\s().-]{6,}\d(?![\w-])")
_URL = re.compile(r"\bhttps?://[^\s)]+|\bwww\.[^\s)]+")
_AMOUNT = re.compile(r"(?:[\$€£]|USD|EUR|GBP|INR|Rs\.?|₹)\s?\d{1,3}(?:,\d{2,3})*(?:\.\d{1,2})?")
_REFERENCE = re.compile(r"\b(?=[A-Z0-9\-/]*\d)(?=[A-Z0-9\-/]*[A-Z])[A-Z0-9]{2,}(?:[\-/][A-Z0-9]+)+\b")

# Words that tell the built-in pipelines apart. Each hit adds to that type's score.
TYPE_KEYWORDS = {
    "invoices": ["invoice", "bill to", "subtotal", "amount due", "tax", "vat", "due date", "remit", "qty", "unit price"],
    "contracts": ["agreement", "party", "parties", "hereinafter", "governing law", "terminate", "indemnif", "whereas", "confidential", "liability"],
    "identity": ["passport", "date of birth", "nationality", "driver", "licence", "license", "identity card", "sex", "p<", "expiry"],
}


_LABEL_PREFIXES = {"due", "invoice", "issue", "order", "ship", "bill", "start", "end", "expiry", "expiration",
                   "payment", "delivery", "effective", "total", "net", "grand", "first", "last", "full", "middle",
                   "birth", "joining", "contact", "account", "reference", "po", "tax", "vat"}


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    return s[:48] or "field"


def guess_type(value: str) -> Tuple[str, Any]:
    """Infers a field type from its text and returns (type, normalized value)."""
    v = value.strip()
    iso = normalize_date(v)
    if iso:
        return "date", iso
    if re.fullmatch(r"(?:[\$€£₹]|USD|EUR|GBP|INR|Rs\.?)\s?-?[\d,]+(?:\.\d{1,2})?", v):
        return "currency", parse_amount(re.sub(r"[^\d.,-]", "", v))
    if re.fullmatch(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?|-?\d+(?:\.\d+)?", v):
        num = parse_amount(v)
        return "number", int(num) if num is not None and float(num).is_integer() and "." not in v else num
    if _EMAIL.fullmatch(v):
        return "email", v
    return "text", v


def _usable(label: str, value: str) -> bool:
    return bool(value) and len(value) <= 160 and not re.fullmatch(r"https?|www", label, re.IGNORECASE) \
        and not re.fullmatch(r"[_.\-\s]+", value)  # an empty signature line "By: ______"


def extract_key_values(text: str) -> List[Dict[str, Any]]:
    """
    Finds "Label: value" pairs anywhere in the text, including several pairs on one line
    ("Date: March 20, 2026 Due Date: April 19, 2026").
    """
    pairs = []
    seen = set()
    for line in text.splitlines():
        if line.startswith("--- Page"):
            continue
        for label, value, _, _ in line_label_spans(line):
            if not _usable(label, value):
                continue
            key = slugify(label)
            if (key, value) in seen:
                continue
            seen.add((key, value))
            pairs.append({"label": label, "key": key, "value": value})
    return pairs


def line_label_spans(line: str) -> List[Tuple[str, str, int, int]]:
    """Splits one line into (label, value, value_start, value_end) for each "Label:" on it."""
    # Each label is up to four words, starting with a letter and ending in a colon; its value runs to the next label
    spans = [[m.start(1), m.end(1), m.end()] for m in _LABEL.finditer(line)]
    # "Name: Priya Sharma Employee ID: E-1" reads as one long second label; give its leading
    # words back to the previous value, keeping the last two as the label
    for i in range(1, len(spans)):
        if not line[spans[i - 1][2]:spans[i][0]].strip():
            words = list(re.finditer(r"\S+", line[spans[i][0]:spans[i][1]]))
            if len(words) > 1:
                spans[i][0] += words[max(1, len(words) - 2)].start()
    # Side-by-side columns repeat their labels ("Name: Sarah Jenkins   Name: David Miller"), and an
    # abbreviation can run into the next label ("Apex Inc. Vendor:"): trim those label starts
    for i in range(1, len(spans)):
        words = list(re.finditer(r"\S+", line[spans[i][0]:spans[i][1]]))
        earlier = [line[s[0]:s[1]].lower() for s in spans[:i]]
        for j in range(1, len(words)):
            tail = line[spans[i][0] + words[j].start():spans[i][1]].lower()
            prefix = words[j - 1].group(0).lower()
            if prefix in _LABEL_PREFIXES:
                break  # "Due Date", "Invoice Date": a compound label, not a repeat
            if tail in earlier or prefix.endswith((".", ",")):
                spans[i][0] += words[j].start()
                break
    # "App Label: AMERICAN EXPRESS AID: A0000": an all-caps value runs into an all-caps label; keep its last word
    for i in range(1, len(spans)):
        label_words = list(re.finditer(r"\S+", line[spans[i][0]:spans[i][1]]))
        before = line[spans[i - 1][2]:spans[i][0]].split()
        if len(label_words) > 1 and line[spans[i][0]:spans[i][1]].isupper() and before and before[-1].isupper():
            spans[i][0] += label_words[-1].start()
    out = []
    for i, (l_start, l_end, v_start) in enumerate(spans):
        end = spans[i + 1][0] if i + 1 < len(spans) else len(line)
        raw = line[v_start:end]
        value = raw.strip(" \t;,")
        lead = len(raw) - len(raw.lstrip(" \t;,"))
        out.append((normalize_ws(line[l_start:l_end]), value, v_start + lead, v_start + lead + len(value)))
    return out


def extract_entities(text: str) -> Dict[str, List[str]]:
    def uniq(items):
        out = []
        for i in items:
            i = i.strip(" .,;")
            if i and i not in out:
                out.append(i)
        return out[:25]

    return {
        "dates": uniq(re.findall(DATE_PATTERN, text)),
        "amounts": uniq(_AMOUNT.findall(text)),
        "emails": uniq(_EMAIL.findall(text)),
        "phones": uniq(p for p in _PHONE.findall(text)
                       if len(re.sub(r"\D", "", p)) >= 7 and not normalize_date(p.strip()) and not re.fullmatch(r"[\d,.\s]+", p.strip())),
        "urls": uniq(_URL.findall(text)),
        "references": uniq(_REFERENCE.findall(text)),
    }


def extract_tables(text: str) -> List[Dict[str, Any]]:
    """Detects simple tables: a header row followed by rows with the same number of columns (split on 2+ spaces or tabs)."""
    tables = []
    rows: List[List[str]] = []
    for line in text.splitlines() + [""]:
        cells = [c.strip() for c in re.split(r"\t|\s{2,}", line.strip()) if c.strip()]
        if len(cells) >= 2 and (not rows or len(cells) == len(rows[0])):
            rows.append(cells)
            continue
        if len(rows) >= 3:
            tables.append({"columns": rows[0], "rows": rows[1:]})
        rows = [cells] if len(cells) >= 2 else []
    return tables[:10]


def make_fingerprint(text: str, lines: int = 3) -> str:
    """The first few lines of a document (letterhead, title), which similar documents tend to share."""
    body = [l.strip() for l in re.sub(r"--- Page \d+ ---", "", text or "").splitlines() if l.strip()]
    return normalize_ws(" ".join(body[:lines]))[:300]


def fingerprint_score(fingerprint: Optional[str], text: str) -> float:
    """Share of the fingerprint's words (3+ letters) found in the text."""
    words = {w for w in re.findall(r"[a-z]{3,}", (fingerprint or "").lower())}
    if not words:
        return 0.0
    present = set(re.findall(r"[a-z]{3,}", text.lower()))
    return round(len(words & present) / len(words), 3)


def classify_document(text: str, schemas: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Scores the built-in document types and every template by how much of their vocabulary
    appears in the text. Returns the best match with its score (0-1) and all scores.
    """
    lower = text.lower()
    scores: Dict[str, float] = {}
    for doc_type, words in TYPE_KEYWORDS.items():
        hits = sum(1 for w in words if w in lower)
        scores[doc_type] = round(hits / len(words), 3)
    if "p<" in lower and re.search(r"\n[A-Z0-9<]{44}\s*$", text.upper(), re.MULTILINE):
        scores["identity"] = 1.0

    for s in schemas or []:
        if s.get("document_type_code") in TYPE_KEYWORDS:
            continue
        labels = []
        for f in s.get("fields", []):
            labels.append(f.get("label", ""))
            labels.extend(f.get("aliases") or [])
        labels = [l.lower() for l in labels if l and len(l) > 2]
        label_score = sum(1 for l in set(labels) if l in lower) / len(set(labels)) if labels else 0.0
        if s.get("fingerprint"):
            label_score = (label_score + fingerprint_score(s["fingerprint"], text)) / 2
        if labels or s.get("fingerprint"):
            scores[f"schema:{s['id']}"] = round(label_score, 3)

    best = max(scores.items(), key=lambda kv: kv[1]) if scores else ("generic", 0.0)
    if best[1] < 0.3:
        best = ("generic", best[1])
    return {"best": best[0], "score": best[1], "scores": scores}


_HONORIFIC = re.compile(r"^(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Shri|Smt|Sri|Kumari)\.?$", re.IGNORECASE)
_PERSON = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Dr|Prof|Shri|Smt|Sri)\.?[ \t]+[A-Z][A-Za-z'\-]+(?:[ \t]+[A-Z][A-Za-z'\-]+){0,3}")
_SENTENCE_WORDS = {"the", "and", "or", "of", "to", "for", "with", "should", "must", "shall", "is", "are", "be", "a", "an", "in", "by", "this"}


def _looks_like_label(segment: str) -> bool:
    """Short title-like text such as 'Date of Birth' or 'Place': a label, not a sentence or a value."""
    words = segment.split()
    if not 1 <= len(words) <= 4 or len(segment) > 32 or re.search(r"\d", segment):
        return False
    if not words[0][0].isupper() or segment.endswith((".", ",")) or _HONORIFIC.match(words[0]):
        return False
    if segment.isupper():
        return False  # "USA", "JOHN SMITH": all-caps text on a form is usually a filled-in value
    lowered = [w.lower() for w in words]
    return sum(1 for w in lowered if w in _SENTENCE_WORDS) <= 1 and lowered[-1] not in _SENTENCE_WORDS


def _box(words: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not words:
        return None
    return {"page": words[0]["page"], "x0": min(w["x0"] for w in words), "y0": min(w["y0"] for w in words),
            "x1": max(w["x1"] for w in words), "y1": max(w["y1"] for w in words)}


def layout_lines(words_with_boxes: List[Dict[str, Any]]) -> List[List[List[Dict[str, Any]]]]:
    """
    Groups words into visual lines, and each line into segments separated by a clearly wider gap than
    the usual space between words. Segments keep side-by-side columns apart, so an address on the left
    never runs into a "Room:" label on the right.
    """
    lines: List[List[Dict[str, Any]]] = []
    for w in sorted(words_with_boxes, key=lambda w: (w["page"], round((w["y0"] + w["y1"]) / 2, 1), w["x0"])):
        mid = (w["y0"] + w["y1"]) / 2
        if lines and lines[-1][0]["page"] == w["page"] and \
                abs((lines[-1][0]["y0"] + lines[-1][0]["y1"]) / 2 - mid) < max(0.6, (w["y1"] - w["y0"]) * 0.5):
            lines[-1].append(w)
        else:
            lines.append([w])
    for line in lines:
        line.sort(key=lambda w: w["x0"])

    # The usual space between words across the whole document; a column or label/value gap is clearly wider
    # (only small gaps count as word spaces: in a sparse table most gaps on a line are column gaps)
    all_gaps = sorted(g for line in lines for g in (line[i + 1]["x0"] - line[i]["x1"] for i in range(len(line) - 1)) if 0 < g < 2.5)
    typical = all_gaps[len(all_gaps) // 2] if all_gaps else 0.5
    threshold = max(1.0, typical * 2.2)

    def height(w):
        return max(0.01, w["y1"] - w["y0"])

    result = []
    for line in lines:
        segments, current = [], [line[0]]
        for prev, w in zip(line, line[1:]):
            gap = w["x0"] - prev["x1"]
            # A wide gap, or a change of font size after a visible space (a filled-in value next to its label)
            size_change = abs(height(w) - height(prev)) / max(height(w), height(prev)) > 0.15 and gap > typical * 1.3
            if gap >= threshold or size_change:
                segments.append(current)
                current = [w]
            else:
                current.append(w)
        segments.append(current)
        result.append(segments)
    return result


def _segment_text(segment: List[Dict[str, Any]]) -> Tuple[str, List[Tuple[int, int]]]:
    """Joins a segment's words and records each word's character span in the joined text."""
    parts, spans, pos = [], [], 0
    for w in segment:
        parts.append(w["text"])
        spans.append((pos, pos + len(w["text"])))
        pos += len(w["text"]) + 1
    return " ".join(parts), spans


def extract_layout_key_values(words_with_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    "Label: value" pairs read segment by segment from the page layout, with the exact box of each value.
    A label whose value sits in the next segment ("Folio Number:      65124") takes that segment.
    """
    pairs, seen = [], set()
    for segments in layout_lines(words_with_boxes):
        consumed = set()
        for si, seg in enumerate(segments):
            if si in consumed:
                continue
            text, spans = _segment_text(seg)
            found = line_label_spans(text)
            for li, (label, value, vs, ve) in enumerate(found):
                value_words = [w for w, (a, b) in zip(seg, spans) if a < ve and b > vs]
                is_last = li == len(found) - 1
                if not value and is_last and si + 1 < len(segments):
                    nxt_text, _ = _segment_text(segments[si + 1])
                    if not line_label_spans(nxt_text):
                        value, value_words = nxt_text, segments[si + 1]
                        consumed.add(si + 1)
                if not _usable(label, value):
                    continue
                key = slugify(label)
                if (key, value) in seen:
                    continue
                seen.add((key, value))
                pairs.append({"label": label, "key": key, "value": value, "box": _box(value_words)})
    return pairs


def extract_layout_tables(words_with_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Finds tables from the layout: a header row of 3+ short column titles, then rows whose cells line up
    under those columns (each cell goes to the column whose span it overlaps most).
    """
    lines = layout_lines(words_with_boxes)

    def is_header(segs) -> bool:
        titles = [_segment_text(s)[0] for s in segs]
        return len(segs) >= 3 and all(len(t) <= 25 and not re.search(r"\d", t) and ":" not in t for t in titles)

    def top(segs) -> float:
        return min(w["y0"] for s in segs for w in s)

    tables = []
    i = 0
    while i < len(lines):
        header = lines[i]
        if not is_header(header):
            i += 1
            continue
        titles = [_segment_text(s)[0] for s in header]
        heads = [_box(s) for s in header]
        # Each column owns the strip from just left of its title to the next title, so wide or
        # right-aligned values ("732.72" under "Credits") still land in the right column
        spans = [(heads[c]["x0"] - 1.5, heads[c + 1]["x0"] - 0.5 if c + 1 < len(heads) else 100.0) for c in range(len(heads))]

        def assign(segs):
            cells = [""] * len(spans)
            for s in segs:
                b = _box(s)
                best = max(range(len(spans)), key=lambda c: (min(b["x1"], spans[c][1]) - max(b["x0"], spans[c][0]),
                                                             -abs(b["x0"] - spans[c][0])))
                cells[best] = (cells[best] + " " + _segment_text(s)[0]).strip()
            return cells

        rows: List[List[str]] = []
        row_gaps: List[float] = []
        last_top = top(header)
        page = header[0][0]["page"]
        j = i + 1
        while j < len(lines):
            segs = lines[j]
            seg_page = segs[0][0]["page"]
            if seg_page != page:
                # The table may continue on the next page, usually under a repeated header
                if is_header(segs) and [_segment_text(s)[0] for s in segs] == titles:
                    page, last_top = seg_page, top(segs)
                    j += 1
                    continue
                if not any(re.search(r"\d", c) for c in assign(segs)):
                    break
                page, last_top = seg_page, top(segs) - (row_gaps[-1] if row_gaps else 2.0)
            gap = top(segs) - last_top
            typical = sorted(row_gaps)[len(row_gaps) // 2] if row_gaps else None
            if typical is not None and gap > typical * 3 + 1:
                break  # a clear vertical break: the table has ended
            cells = assign(segs)
            text = " ".join(_segment_text(s)[0] for s in segs)
            filled = sum(1 for c in cells if c)
            labelled = re.search(r"[A-Za-z#]\s*:(\s|$)", text)  # "Card Type: AMEX" is a field line, not a row; "11:18AM" is fine
            if any(re.search(r"\d", c) for c in cells) and filled >= 2 and not labelled:
                rows.append(cells)
                row_gaps.append(gap)
            elif rows and filled <= max(1, len(cells) // 2) and not re.search(r"\d", text) and (typical is None or gap <= typical * 1.2):
                # A wrapped cell ("STATE SALES" / "TAX"): add the text to the row above
                for c, extra in enumerate(cells):
                    if extra:
                        rows[-1][c] = (rows[-1][c] + " " + extra).strip()
            else:
                break
            last_top = top(segs)
            j += 1
        if len(rows) >= 2:
            tables.append({"columns": titles, "rows": rows, "page": header[0][0]["page"]})
            i = j
            continue
        i += 1
    return tables[:10]


def extract_layout_pairs(words_with_boxes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Finds label/value pairs that have no colon, as on filled-in forms ("Date of Birth   Dec 07, 2015"),
    using the page layout: a value sits on the label's line after a clearly wider gap than between words.
    """
    pairs = []
    for segments in layout_lines(words_with_boxes):
        if len(segments) < 2:
            continue
        texts = [_segment_text(s)[0] for s in segments]
        if any(":" in t for t in texts):
            continue  # colon-labelled lines are handled by extract_key_values
        if sum(1 for t in texts if " / " in t) >= 2:
            continue  # a header row of bilingual column labels ("Code / Code   Passport No. / No de passeport")
        if len(texts) >= 3 and sum(1 for t in texts if re.search(r"\d", t)) >= 2:
            continue  # a table row ("Advisory  20 hrs  $150.00  $3,000.00"), not a label and value

        # Alternate label / value across the line: "Name  X", "Date  Y   Place  Z"
        i = 0
        while i < len(segments) - 1:
            if _looks_like_label(texts[i]) and not _looks_like_label(texts[i + 1]) or \
                    (_looks_like_label(texts[i]) and len(segments) == 2):
                value_words = segments[i + 1]
                pairs.append({
                    "label": texts[i], "key": slugify(texts[i]), "value": texts[i + 1],
                    "box": {"page": value_words[0]["page"],
                            "x0": min(w["x0"] for w in value_words), "y0": min(w["y0"] for w in value_words),
                            "x1": max(w["x1"] for w in value_words), "y1": max(w["y1"] for w in value_words)},
                })
                i += 2
            else:
                i += 1
    return pairs


class GenericPipeline:
    """Extraction for any unstructured document: labelled values become fields; entities and tables go in metadata."""

    @staticmethod
    def process(text: str, words_with_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        fields = {}

        def add(key: str, label: str, raw: str, conf: float, box: Optional[Dict[str, Any]] = None):
            f_type, value = guess_type(raw)
            name = key
            i = 2
            while name in fields:
                name = f"{key}_{i}"
                i += 1
            fields[name] = make_field(name, label, value, conf, f_type, words_with_boxes, box_phrase=raw)
            if box:  # the exact position from the layout beats searching the page for the same text
                fields[name]["bounding_box"] = box

        # 1. "Label: value", read from the page layout when there is one (keeps columns apart, exact boxes)
        for kv in (extract_layout_key_values(words_with_boxes) if words_with_boxes else extract_key_values(text)):
            add(kv["key"], kv["label"], kv["value"], 0.8, kv.get("box"))
        seen_labels = {f["display_name"].lower() for f in fields.values()}

        # 2. Form layout without colons: label, a wide gap, then the value
        for kv in extract_layout_pairs(words_with_boxes):
            if kv["label"].lower() not in seen_labels:
                seen_labels.add(kv["label"].lower())
                add(kv["key"], kv["label"], kv["value"], 0.75, kv["box"])

        # 3. Named people ("Mr. John Smith") that are not already a field value
        # Read per layout segment so a name never runs into the next column ("Smith   Room: 206")
        values = " ".join(str(f["value"]) for f in fields.values())
        if words_with_boxes:
            # a lone honorific segment ("Mr.") belongs with the name segment after it
            chunks = [" ".join(_segment_text(s)[0] for s in line) if _HONORIFIC.match(_segment_text(line[0])[0]) else None
                      for line in layout_lines(words_with_boxes)]
            chunks = [c for c in chunks if c] + [_segment_text(s)[0] for line in layout_lines(words_with_boxes) for s in line]
        else:
            chunks = text.splitlines()
        people = []
        for chunk in chunks:
            for m in _PERSON.finditer(chunk):
                name = re.split(r"\s+\S+:", m.group(0))[0]  # stop before a following "Label:"
                if name not in people and name.split(None, 1)[-1] not in values:
                    people.append(name)
        for n, person in enumerate(people, start=1):
            add(f"person_{n}", f"Person {n}", person, 0.7)

        body = re.sub(r"--- Page \d+ ---", "", text)
        first_line = next((l.strip() for l in body.splitlines() if l.strip()), "")
        return {
            "fields": fields,
            "metadata": {
                "document_title": first_line[:120] or None,
                "entities": extract_entities(body),
                "tables": extract_layout_tables(words_with_boxes) if words_with_boxes else extract_tables(body),
                "word_count": len(body.split()),
            }
        }
