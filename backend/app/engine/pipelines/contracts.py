import re
from typing import Dict, Any, List
from app.engine.pipelines.common import make_field, normalize_ws, normalize_date, DATE_PATTERN

_ENTITY_TAIL = r"(?:,?\s+an?\s+[^()]{0,120}?)?\s*\(\s*(?:the\s+)?[\"“]([^\"”]+)[\"”]\s*\)"


def _clean_party(name: str) -> str:
    name = normalize_ws(name).strip(" ,.;:")
    return re.sub(r"^(?:the\s+)", "", name, flags=re.IGNORECASE)


class ContractsPipeline:
    @staticmethod
    def process(text: str, words_with_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        fields = {}
        risk_flags = []
        body = re.sub(r"--- Page \d+ ---", " ", text)
        flat = normalize_ws(body)
        lower = flat.lower()

        # 1. Agreement title: the heading lines before the preamble, ending at the first line naming the instrument
        title_val = None
        heading = []
        for line in [l.strip() for l in body.splitlines() if l.strip()][:6]:
            if re.match(r"^(this|the)\s", line, re.IGNORECASE):
                break
            heading.append(line)
            if re.search(r"\b(agreement|contract|addendum|memorandum|deed|lease)\b", line, re.IGNORECASE):
                title_val = normalize_ws(" ".join(heading)).title()
                break
        if not title_val:
            m = re.search(r"\b((?:[A-Z][A-Za-z\-]+\s+){0,5}(?:AGREEMENT|CONTRACT))\b", flat)
            title_val = m.group(1).title() if m else None
        fields["agreement_title"] = make_field("agreement_title", "Agreement Title", title_val, 0.92, "text",
                                               words_with_boxes, box_phrase=(title_val or "").split(" ")[0], required=True)

        # 2. Parties: "between X, a ... ("Client"), and Y, a ... ("Vendor")"
        p_a = p_b = None
        conf_parties = 0.0
        m = re.search(r"between\s+(.+?)" + _ENTITY_TAIL + r",?\s+and\s+(.+?)" + _ENTITY_TAIL, flat, re.IGNORECASE)
        if m:
            p_a, p_b = _clean_party(m.group(1)), _clean_party(m.group(3))
            p_a = re.split(r",\s+an?\s+", p_a)[0]
            p_b = re.split(r",\s+an?\s+", p_b)[0]
            conf_parties = 0.93
        else:
            m = re.search(r"between\s+([A-Z][\w&.,\- ]{2,80}?)\s+and\s+([A-Z][\w&.,\- ]{2,80}?)(?:[,.(]|\s+\()", flat)
            if m:
                p_a, p_b = _clean_party(m.group(1)), _clean_party(m.group(2))
                p_a = re.split(r",\s+an?\s+", p_a)[0]
                p_b = re.split(r",\s+an?\s+", p_b)[0]
                conf_parties = 0.78
        fields["party_a"] = make_field("party_a", "First Party (Disclosing/Client)", p_a, conf_parties, "text",
                                       words_with_boxes, required=True)
        fields["party_b"] = make_field("party_b", "Second Party (Receiving/Vendor)", p_b, conf_parties, "text",
                                       words_with_boxes, required=True)

        # 3. Effective date
        m = re.search(r"(?:effective\s+as\s+of|effective\s+date\s*(?:is|:)|dated(?:\s+as\s+of)?|made\s+(?:and\s+entered\s+into\s+)?(?:as\s+of|on))\s*(" + DATE_PATTERN + ")", flat, re.IGNORECASE)
        raw = m.group(1) if m else None
        iso = normalize_date(raw)
        fields["effective_date"] = make_field("effective_date", "Effective Date", iso or raw, 0.93 if iso else 0.6, "date",
                                              words_with_boxes, box_phrase=raw, required=True,
                                              validation_error=None if (iso or not raw) else f"Could not parse date '{raw}'.")

        # 4. Expiration / term date
        m = re.search(r"(?:terminate\s+on|expire[sd]?\s+on|expiration\s+date\s*(?:is|:)?|until)\s*(" + DATE_PATTERN + ")", flat, re.IGNORECASE)
        raw = m.group(1) if m else None
        iso = normalize_date(raw)
        fields["expiration_date"] = make_field("expiration_date", "Expiration / Term Date", iso or raw, 0.88 if iso else 0.6, "date",
                                               words_with_boxes, box_phrase=raw)

        # 5. Governing law
        law = None
        m = re.search(r"governed\s+by\s+(?:and\s+construed\s+in\s+accordance\s+with\s+)?the\s+laws?\s+of\s+(?:the\s+)?(.+?)(?:,|\.|;|\s+without|\s+excluding)", flat, re.IGNORECASE)
        if m:
            law = normalize_ws(m.group(1))
            if len(law) > 60:
                law = None
        fields["governing_law"] = make_field("governing_law", "Governing Law / Jurisdiction", law, 0.92, "text",
                                             words_with_boxes, required=True)

        # 6. Liability cap
        cap = None
        m = re.search(r"liability\s+(?:shall\s+not\s+exceed|(?:is\s+|shall\s+be\s+)?(?:capped|limited)\s+(?:at|to))\s*((?:US)?[\$€£]\s?[\d,]+(?:\.\d{2})?(?:\s*(?:USD|EUR|GBP))?|the\s+(?:total\s+)?fees\s+paid[^.]{0,60})", flat, re.IGNORECASE)
        if m:
            cap = normalize_ws(m.group(1))
        if "unlimited liability" in lower:
            cap = cap or "Unlimited"
        fields["liability_cap"] = make_field("liability_cap", "Liability Cap / Limitation", cap, 0.91, "currency", words_with_boxes)

        # 7. Confidentiality duration (normalized to years)
        conf_years = None
        m = re.search(r"confidential\w*[^.]{0,120}?(?:survive|remain\s+in\s+effect|continue)[^.]{0,40}?(?:for\s+)?(?:a\s+period\s+of\s+)?(\d+)\s*\(?\w*\)?\s*(years?|months?)", flat, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            conf_years = n if m.group(2).lower().startswith("year") else round(n / 12, 2)
        fields["confidentiality_term_years"] = make_field("confidentiality_term_years", "Confidentiality Duration (Years)",
                                                          conf_years, 0.9, "number", words_with_boxes,
                                                          box_phrase=m.group(1) + " " + m.group(2) if m else None)

        # 8. Termination notice
        days = None
        m = re.search(r"(\d+)\s*\(?\w*\)?\s*(?:calendar\s+|business\s+)?days['’]?\s*(?:prior\s+|advance\s+)?(?:written\s+)?notice", flat, re.IGNORECASE)
        if m:
            days = int(m.group(1))
        fields["termination_notice_days"] = make_field("termination_notice_days", "Termination Notice (Days)", days, 0.92,
                                                       "number", words_with_boxes, box_phrase=f"{days} days" if days else None)

        # 9. Risk assessment from clause signals
        high_signals = [s for s in ["unlimited liability", "sole discretion", "uncapped", "without limitation of liability"] if s in lower]
        if high_signals:
            risk_rating = "HIGH"
            risk_flags.extend(f"High-risk language: '{s}'" for s in high_signals)
        elif "indemnif" in lower and "hold harmless" in lower:
            risk_rating = "MEDIUM"
            risk_flags.append("Broad indemnification and hold harmless clause present")
        elif cap is None:
            risk_rating = "MEDIUM"
            risk_flags.append("No limitation of liability clause found")
        else:
            risk_rating = "LOW"
            risk_flags.append("Standard bilateral commercial protections observed")
        fields["risk_rating"] = make_field("risk_rating", "Overall Contract Risk Rating", risk_rating, 0.85, "enum",
                                           validation_error="High contract risk: review flagged clauses" if risk_rating == "HIGH" else None)

        clauses = [c for c, k in [("Confidentiality", "confidential"), ("Term", "term"), ("Liability", "liabilit"),
                                  ("Termination", "terminat"), ("Governing Law", "governed by"),
                                  ("Indemnification", "indemnif")] if k in lower]
        return {
            "fields": fields,
            "metadata": {
                "risk_flags": risk_flags,
                "document_subclass": "Non-Disclosure Agreement" if "non-disclosure" in lower and "services" not in lower else "Commercial Agreement",
                "clauses_analyzed": clauses,
            }
        }
