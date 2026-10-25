import re
from typing import Dict, Any, List, Optional
from app.engine.pipelines.common import make_field, normalize_ws, normalize_date, parse_amount, DATE_PATTERN

_MONEY = r"(?:[\$€£]|USD|EUR|GBP|CAD|AUD)?\s*(-?\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|-?\d+(?:\.\d{1,2})?)"


def _line_amount(lines: List[str], label_regex: str, exclude_regex: Optional[str] = None, last: bool = False):
    """Finds an amount on a line whose start matches label_regex. Returns (amount, raw_text)."""
    hits = []
    for line in lines:
        s = line.strip()
        if not re.match(label_regex, s, re.IGNORECASE):
            continue
        if exclude_regex and re.match(exclude_regex, s, re.IGNORECASE):
            continue
        amounts = re.findall(_MONEY, s)
        # Use the right-most amount on the line (labels like "Tax (VAT 9%)" carry a rate first)
        money = re.findall(r"[\$€£]\s*(-?[\d,]+(?:\.\d{1,2})?)", s) or [a for a in amounts if "." in a] or amounts
        if money:
            hits.append((parse_amount(money[-1]), money[-1]))
    if not hits:
        return None, None
    return hits[-1] if last else hits[0]


class InvoicesPipeline:
    @staticmethod
    def process(text: str, words_with_boxes: List[Dict[str, Any]]) -> Dict[str, Any]:
        fields = {}
        body = re.sub(r"--- Page \d+ ---", "", text)
        lines = [l for l in body.splitlines() if l.strip()]
        flat = normalize_ws(body)

        # 1. Invoice number (must contain a digit, so "Invoice Date" is not mistaken for it)
        inv_num = None
        m = re.search(r"\bINVOICE\s*(?:NO\.?|NUMBER|NUM|#|ID)?\s*[:#]?\s*#?\s*([A-Z0-9][A-Z0-9\-/]*\d[A-Z0-9\-/]*)", flat, re.IGNORECASE)
        if m:
            inv_num = m.group(1)
        fields["invoice_number"] = make_field("invoice_number", "Invoice Number", inv_num, 0.96, "text", words_with_boxes, required=True)

        # 2. Vendor
        vendor = None
        m = re.search(r"^(?:FROM|VENDOR|SUPPLIER|BILLER|SELLER|REMIT\s+TO)\s*[:\-]\s*(.+)$", body, re.IGNORECASE | re.MULTILINE)
        if m:
            vendor = m.group(1).strip()
        elif lines:
            # Many invoices put the vendor name on the first line above the word INVOICE
            first = lines[0].strip()
            if not re.search(r"invoice", first, re.IGNORECASE) and len(first) < 60:
                vendor = first
        fields["vendor_name"] = make_field("vendor_name", "Vendor / Supplier Name", vendor, 0.92 if m else 0.6, "text",
                                           words_with_boxes, required=True)

        # 3. Invoice date / 4. Due date
        m = re.search(r"(?:INVOICE\s+DATE|DATE\s+OF\s+ISSUE|ISSUE\s+DATE|(?<!DUE\s)\bDATE)\s*[:\-]?\s*(" + DATE_PATTERN + ")", flat, re.IGNORECASE)
        raw = m.group(1) if m else None
        iso = normalize_date(raw)
        fields["invoice_date"] = make_field("invoice_date", "Invoice Date", iso or raw, 0.94 if iso else 0.6, "date",
                                            words_with_boxes, box_phrase=raw, required=True)

        m = re.search(r"(?:DUE\s+DATE|PAYMENT\s+DUE|DUE\s+ON|PAY\s+BY)\s*[:\-]?\s*(" + DATE_PATTERN + ")", flat, re.IGNORECASE)
        raw = m.group(1) if m else None
        iso = normalize_date(raw)
        fields["due_date"] = make_field("due_date", "Payment Due Date", iso or raw, 0.91 if iso else 0.6, "date",
                                        words_with_boxes, box_phrase=raw)

        # 5. Currency: explicit label first, then the symbols used
        currency = None
        m = re.search(r"CURRENCY\s*[:\-]?\s*([A-Z]{3})\b", flat, re.IGNORECASE)
        if m:
            currency = m.group(1).upper()
        else:
            for sym, code in [("€", "EUR"), ("£", "GBP"), ("EUR", "EUR"), ("GBP", "GBP"), ("CAD", "CAD"), ("AUD", "AUD"), ("USD", "USD"), ("$", "USD")]:
                if sym in flat:
                    currency = code
                    break
        fields["currency"] = make_field("currency", "Currency", currency, 0.97 if m else 0.85, "enum", words_with_boxes,
                                        box_phrase=m.group(0) if m else None, required=True)

        # 6. Amounts, each read from its own labelled line
        subtotal, sub_raw = _line_amount(lines, r"^(?:SUB\s*-?\s*TOTAL|NET\s+(?:AMOUNT|TOTAL))\b")
        tax, tax_raw = _line_amount(lines, r"^(?:TAX|VAT|GST|HST|SALES\s+TAX)\b", exclude_regex=r"^(?:TAX|VAT|GST)\s*(?:ID|NO\.?|NUMBER|REG)")
        total, tot_raw = _line_amount(lines, r"^(?:(?:GRAND\s+|INVOICE\s+)?TOTAL(?:\s+AMOUNT)?(?:\s+DUE)?|AMOUNT\s+DUE|BALANCE\s+DUE)\b", last=True)

        # Line items: rows ending in an amount, between the table header and the subtotal
        line_items = []
        in_table = False
        for line in lines:
            s = line.strip()
            if re.match(r"^(?:SUB\s*-?\s*TOTAL|TOTAL|TAX|VAT)\b", s, re.IGNORECASE):
                if in_table:
                    break
                continue
            if re.search(r"\b(description|item)\b", s, re.IGNORECASE) and re.search(r"\b(amount|total|price)\b", s, re.IGNORECASE):
                in_table = True
                continue
            if in_table:
                im = re.match(r"^(.*?)\s+[\$€£]?\s*([\d,]+\.\d{2})$", s)
                if im:
                    line_items.append({"description": im.group(1), "amount": parse_amount(im.group(2))})

        fields["subtotal"] = make_field("subtotal", "Subtotal Amount", subtotal, 0.95, "currency", words_with_boxes,
                                        box_phrase=sub_raw, required=True)
        fields["tax_amount"] = make_field("tax_amount", "Tax / VAT Amount", tax, 0.93, "currency", words_with_boxes, box_phrase=tax_raw)
        fields["total_amount"] = make_field("total_amount", "Total Amount", total, 0.97, "currency", words_with_boxes,
                                            box_phrase=tot_raw, required=True)

        # 7. Reconciliation: subtotal + tax == total, and line items == subtotal
        diff = None
        problems = []
        if subtotal is not None and total is not None:
            diff = round(subtotal + (tax or 0.0) - total, 2)
            if abs(diff) >= 0.05:
                problems.append(f"Subtotal + Tax ({subtotal + (tax or 0):,.2f}) does not equal Total ({total:,.2f}).")
        else:
            problems.append("Cannot verify totals: subtotal or total was not found.")
        items_sum = round(sum(i["amount"] or 0 for i in line_items), 2) if line_items else None
        if items_sum is not None and subtotal is not None and abs(items_sum - subtotal) >= 0.05:
            problems.append(f"Line items sum ({items_sum:,.2f}) does not equal Subtotal ({subtotal:,.2f}).")

        if not problems:
            check_val = "VALID"
        elif subtotal is None or total is None:
            check_val = "UNVERIFIED"
        else:
            check_val = "DISCREPANCY"
        fields["math_check_valid"] = make_field("math_check_valid", "Math Integrity (Subtotal + Tax == Total)", check_val, 1.0,
                                                "enum", validation_error=" ".join(problems) or None)

        return {
            "fields": fields,
            "metadata": {
                "line_items": line_items,
                "line_items_sum": items_sum,
                "computed_math_difference": diff,
                "is_math_reconciled": check_val == "VALID",
            }
        }
