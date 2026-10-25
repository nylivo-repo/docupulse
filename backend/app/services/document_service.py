import os
import re
import json
import uuid
import asyncio
import traceback
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.database import get_connection
from app.engine.ocr_extractor import OCRExtractor
from app.engine.pipelines.contracts import ContractsPipeline
from app.engine.pipelines.identity import IdentityPipeline
from app.engine.pipelines.invoices import InvoicesPipeline
from app.engine.pipelines.custom_schema import CustomSchemaPipeline, coerce_value
from app.engine.pipelines.generic import GenericPipeline, classify_document, fingerprint_score, extract_layout_tables
from app.engine.local_llm import LocalLLM
from app.services.webhook_service import WebhookService

BUILTIN_PIPELINES = {
    "contracts": ContractsPipeline,
    "identity": IdentityPipeline,
    "invoices": InvoicesPipeline,
}

# Keeps fire-and-forget webhook tasks referenced until they finish
_background_tasks: set = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dispatch_webhook(event: str, payload: Dict[str, Any]):
    """Sends webhooks in the background so a slow or unreachable receiver never delays processing."""
    try:
        task = asyncio.get_running_loop().create_task(WebhookService.dispatch_event(event, payload))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
    except RuntimeError:
        pass


def _audit(cursor, doc_id: str, user: str, action: str, details: Dict[str, Any]):
    cursor.execute("""
        INSERT INTO audit_logs (id, document_id, "timestamp", "user", action, details_json)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(uuid.uuid4()), doc_id, _now(), user, action, json.dumps(details)))


def load_schemas() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, document_type_code, fields_json, base_pipeline, fingerprint FROM custom_schemas WHERE is_active = 1").fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "document_type_code": r["document_type_code"],
             "fields": json.loads(r["fields_json"]), "base_pipeline": r["base_pipeline"],
             "fingerprint": r["fingerprint"]} for r in rows]


def _template_match_score(schema: Dict[str, Any], text: str, words: List[Dict[str, Any]], builtin_fields: Dict[str, Any]) -> float:
    """
    How well a template built on a built-in pipeline fits a document: half from its sample's header
    (letterhead/title) appearing in the text, half from its added fields being findable, by label or
    by text inside their page region.
    """
    from app.engine.pipelines.custom_schema import _words_in_region
    lower = text.lower()
    extra = [f for f in schema["fields"] if f["name"] not in builtin_fields]
    field_score = 1.0
    if extra:
        hits = 0
        for f in extra:
            labels = [f.get("label", "")] + (f.get("aliases") or [])
            if any(l and len(l) > 2 and l.lower() in lower for l in labels):
                hits += 1
            elif f.get("region") and _words_in_region(f["region"], words)[0]:
                hits += 1
        field_score = hits / len(extra)
    if not schema.get("fingerprint"):
        return round(field_score, 3)
    fp = fingerprint_score(schema["fingerprint"], text)
    if fp < 0.75:
        return 0.0  # a different letterhead/title: another issuer's document, even if the layout looks alike
    return round((field_score + fp) / 2, 3)


def save_words(doc_id: str, words: List[Dict[str, Any]]):
    with open(os.path.join(settings.STORAGE_DIR, doc_id, "words.json"), "w") as f:
        json.dump(words, f)


def load_words(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Word boxes of a processed document; re-extracted (and cached) for documents processed before they were stored."""
    path = os.path.join(settings.STORAGE_DIR, doc["id"], "words.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    _, words, _, _ = OCRExtractor.extract_text_and_boxes(doc["file_path"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    save_words(doc["id"], words)
    return words


def _apply_schema_rules(fields: Dict[str, Dict[str, Any]], schema_fields: List[Dict[str, Any]]):
    """Applies a template's required flags and confidence thresholds to fields from a built-in pipeline."""
    for f_def in schema_fields:
        fld = fields.get(f_def.get("name"))
        if not fld:
            continue
        if fld.get("value") is None and f_def.get("required") and not fld.get("validation_error"):
            fld["validation_error"] = f"Required field '{f_def.get('label', f_def['name'])}' was not found in the document."
        threshold = f_def.get("confidence_threshold")
        if fld.get("value") is not None and threshold and fld.get("confidence", 0) < threshold and not fld.get("validation_error"):
            fld["validation_error"] = (f"Extraction confidence ({int(fld['confidence'] * 100)}%) is below the "
                                       f"required threshold ({int(threshold * 100)}%).")


class DocumentService:
    @staticmethod
    async def process_document_pipeline(doc_id: str, file_path: str, doc_type: str, schema_id: Optional[str] = None):
        """Runs OCR/text extraction, picks the pipeline (or detects it when doc_type is 'auto') and stores the result."""
        conn = get_connection()
        conn.execute("UPDATE documents SET status = 'processing' WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()

        try:
            doc_dir = os.path.join(settings.STORAGE_DIR, doc_id)
            os.makedirs(doc_dir, exist_ok=True)
            # OCR and rendering are CPU-bound; keep them off the event loop so the API stays responsive
            await asyncio.to_thread(OCRExtractor.render_pdf_to_images, file_path, doc_dir)
            raw_text, words_with_boxes, page_count, extraction_info = await asyncio.to_thread(
                OCRExtractor.extract_text_and_boxes, file_path)
            save_words(doc_id, words_with_boxes)

            schemas = load_schemas()
            schemas_by_id = {s["id"]: s for s in schemas}
            schemas_by_code = {s["document_type_code"]: s for s in schemas}
            classification = classify_document(raw_text, schemas)

            requested_type = doc_type
            schema = schemas_by_id.get(schema_id) if schema_id else None
            if doc_type == "auto" and not schema:
                best = classification["best"]
                if best.startswith("schema:"):
                    schema = schemas_by_id.get(best.split(":", 1)[1])
                    doc_type = "custom"
                else:
                    doc_type = best
            elif doc_type not in BUILTIN_PIPELINES and doc_type not in ("custom", "generic") and doc_type in schemas_by_code:
                schema = schemas_by_code[doc_type]
                doc_type = "custom"

            metadata: Dict[str, Any] = {}

            # A detected contract/passport/invoice may have a template that extends it with more fields
            if doc_type in BUILTIN_PIPELINES and not schema and requested_type == "auto":
                base_result = BUILTIN_PIPELINES[doc_type].process(raw_text, words_with_boxes)
                candidates = [(s, _template_match_score(s, raw_text, words_with_boxes, base_result.get("fields", {})))
                              for s in schemas if s.get("base_pipeline") == doc_type]
                candidates = [c for c in candidates if c[1] >= 0.75]
                if candidates:
                    schema = max(candidates, key=lambda c: c[1])[0]
                    classification["template_match"] = {"schema_id": schema["id"], "score": max(c[1] for c in candidates)}

            if doc_type in BUILTIN_PIPELINES and not schema:
                result = BUILTIN_PIPELINES[doc_type].process(raw_text, words_with_boxes)
                fields = result.get("fields", {})
                builtin_schema = schemas_by_code.get(doc_type)
                if builtin_schema:
                    _apply_schema_rules(fields, builtin_schema["fields"])
            elif schema and schema.get("base_pipeline") in BUILTIN_PIPELINES:
                # Built-in rules first (MRZ checks, invoice math...), then the template's own added fields
                base = schema["base_pipeline"]
                result = BUILTIN_PIPELINES[base].process(raw_text, words_with_boxes)
                fields = result.get("fields", {})
                extra_defs = [f for f in schema["fields"] if f["name"] not in fields]
                extra = CustomSchemaPipeline.process(raw_text, words_with_boxes, extra_defs)
                fields.update(extra["fields"])
                _apply_schema_rules(fields, [f for f in schema["fields"] if f["name"] not in extra["fields"]])
                result["metadata"] = {**result.get("metadata", {}), **extra["metadata"], "base_pipeline": base}
                doc_type = "custom"
                schema_id = schema["id"]
            elif schema:
                doc_type = "custom"
                result = CustomSchemaPipeline.process(raw_text, words_with_boxes, schema["fields"])
                fields = result.get("fields", {})
                filled = await LocalLLM.fill_missing(raw_text, fields, schema["fields"])
                for name in filled:
                    f_def = next(f for f in schema["fields"] if f["name"] == name)
                    value, err = coerce_value(fields[name]["value"], f_def.get("data_type", "text"), f_def.get("enum_values") or [])
                    fields[name]["value"] = value
                    fields[name]["validation_error"] = err or fields[name]["validation_error"]
                metadata["local_llm_filled_fields"] = filled
                schema_id = schema["id"]
            else:
                doc_type = "generic"
                result = GenericPipeline.process(raw_text, words_with_boxes)
                fields = result.get("fields", {})

            metadata.update(result.get("metadata", {}))
            if "tables" not in metadata and words_with_boxes:
                # Line-item tables for every kind of document, not only general ones (shown in Review, in the CSV)
                metadata["tables"] = extract_layout_tables(words_with_boxes)
            metadata["classification"] = {**classification, "requested_type": requested_type, "resolved_type": doc_type}
            metadata["extraction"] = extraction_info

            confidences = [f.get("confidence", 0.0) for f in fields.values()]
            overall_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
            review_reasons = []
            if any(f.get("validation_error") for f in fields.values()):
                review_reasons.append("One or more fields failed validation")
            if overall_conf < settings.REVIEW_CONFIDENCE_THRESHOLD:
                review_reasons.append(f"Overall confidence below {int(settings.REVIEW_CONFIDENCE_THRESHOLD * 100)}%")
            if not raw_text.strip():
                review_reasons.append("No readable text was found")
            if not fields:
                review_reasons.append("No fields were extracted")
            if doc_type == "generic":
                review_reasons.append("No template matched; check the extracted fields")
            needs_review = bool(review_reasons)
            metadata["review_reasons"] = review_reasons
            final_status = "needs_review" if needs_review else "approved"

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE documents
                SET status = ?, doc_type = ?, schema_id = ?, page_count = ?, overall_confidence = ?, needs_review = ?,
                    processed_at = ?, fields_json = ?, raw_text = ?, metadata_json = ?
                WHERE id = ?
            """, (final_status, doc_type, schema_id, page_count, overall_conf, 1 if needs_review else 0, _now(),
                  json.dumps(fields), raw_text, json.dumps(metadata), doc_id))
            _audit(cursor, doc_id, "pipeline_extractor",
                   f"Extraction completed ({'Straight-Through Approved' if not needs_review else 'Review Required'})",
                   {"confidence": overall_conf, "fields_count": len(fields), "needs_review": needs_review,
                    "pipeline": doc_type, "reasons": review_reasons})
            conn.commit()
            conn.close()

            _dispatch_webhook("document.needs_review" if needs_review else "document.completed", {
                "document_id": doc_id,
                "doc_type": doc_type,
                "status": final_status,
                "overall_confidence": overall_conf,
                "needs_review": needs_review,
                "extracted_fields_summary": {k: v.get("value") for k, v in fields.items()},
            })
        except Exception as e:
            traceback.print_exc()
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE documents SET status = 'failed', needs_review = 1, processed_at = ?, metadata_json = ? WHERE id = ?",
                           (_now(), json.dumps({"error": str(e)}), doc_id))
            _audit(cursor, doc_id, "pipeline_extractor", "Extraction failed", {"error": str(e)})
            conn.commit()
            conn.close()
            _dispatch_webhook("document.failed", {"document_id": doc_id, "error": str(e)})

    @staticmethod
    def _row_to_doc(row) -> Dict[str, Any]:
        d = dict(row)
        d["fields"] = json.loads(d["fields_json"]) if d["fields_json"] else {}
        d["metadata"] = json.loads(d["metadata_json"]) if d["metadata_json"] else {}
        d["needs_review"] = bool(d["needs_review"])
        d["file_url"] = f"{settings.API_V1_STR}/documents/{d['id']}/preview/page_1.png"
        d["page_urls"] = [f"{settings.API_V1_STR}/documents/{d['id']}/preview/page_{i}.png" for i in range(1, (d.get("page_count") or 1) + 1)]
        return d

    @staticmethod
    def get_document(doc_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE id = ?", (doc_id,))
        doc_row = cursor.fetchone()
        if not doc_row:
            conn.close()
            return None
        cursor.execute("""SELECT * FROM audit_logs WHERE document_id = ? ORDER BY "timestamp" ASC""", (doc_id,))
        audit_rows = cursor.fetchall()
        conn.close()

        doc = DocumentService._row_to_doc(doc_row)
        doc["audit_trail"] = [{"timestamp": r["timestamp"], "user": r["user"], "action": r["action"],
                               "details": json.loads(r["details_json"])} for r in audit_rows]
        return doc

    @staticmethod
    def list_documents(doc_type: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None,
                       owner_id: Optional[str] = None, folder: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = get_connection()
        cursor = conn.cursor()
        query = "SELECT * FROM documents WHERE 1=1"
        params = []
        if owner_id is not None:
            query += " AND owner_id = ?"
            params.append(owner_id)
        if folder == "root":
            query += " AND folder_id IS NULL"
        elif folder:
            query += " AND folder_id = ?"
            params.append(folder)
        if doc_type and doc_type != "all":
            query += " AND doc_type = ?"
            params.append(doc_type)
        if status and status != "all":
            query += " AND status = ?"
            params.append(status)
        if search:
            query += " AND (title LIKE ? OR file_name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY created_at DESC"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        docs = []
        for r in rows:
            d = DocumentService._row_to_doc(r)
            d["raw_text"] = None  # keep list responses small
            docs.append(d)
        return docs

    @staticmethod
    async def update_fields_and_review(doc_id: str, field_updates: List[Dict[str, Any]], actor: str = "human_reviewer",
                                       action: str = "update", reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        doc = DocumentService.get_document(doc_id)
        if not doc:
            return None

        fields = doc["fields"]
        changes = {}
        for update in field_updates:
            f_name = update["field_name"]
            new_val = update["value"]
            if f_name not in fields:
                continue
            fld = fields[f_name]
            old_val = fld.get("value")
            if old_val is not None and new_val is not None and str(old_val) == str(new_val).strip():
                continue  # unchanged, e.g. "$2,500,000" sent back as typed
            if new_val == "" or new_val is None:
                new_val = None
            else:
                new_val, err = coerce_value(new_val, fld.get("field_type", "text"), [])
                if err and fld.get("field_type") in ("number", "currency", "date"):
                    fld["validation_error"] = err
            # Compare as text so an untouched 30 and "30" are not treated as an edit
            if (str(old_val) if old_val is not None else "") == (str(new_val) if new_val is not None else ""):
                continue
            changes[f_name] = {"old": old_val, "new": new_val}
            if not fld.get("is_manually_edited"):
                fld["original_value"] = old_val
            fld["value"] = new_val
            fld["is_manually_edited"] = True
            fld["confidence"] = 1.0 if new_val is not None else 0.0
            if new_val is not None and not (fld.get("validation_error") or "").startswith(f"'{new_val}'"):
                fld["validation_error"] = None  # cleared by the reviewer's correction

        remaining_errors = [k for k, f in fields.items() if f.get("validation_error")]
        if action == "approve":
            new_status, needs_review = "approved", False
        elif action == "reject":
            new_status, needs_review = "rejected", False
        elif doc["status"] in ("approved", "rejected"):
            new_status, needs_review = doc["status"], doc["needs_review"]
        else:
            needs_review = bool(remaining_errors)
            new_status = "needs_review" if needs_review else "approved"

        confidences = [f.get("confidence", 0.0) for f in fields.values()]
        new_overall_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.0
        metadata = doc["metadata"]
        if action == "reject":
            metadata["rejection_reason"] = reason

        if not changes and action == "update":
            return doc

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE documents SET fields_json = ?, status = ?, needs_review = ?, overall_confidence = ?, metadata_json = ?
            WHERE id = ?
        """, (json.dumps(fields), new_status, 1 if needs_review else 0, new_overall_conf, json.dumps(metadata), doc_id))
        details = {"modified_fields": changes, "new_status": new_status}
        if reason:
            details["reason"] = reason
        _audit(cursor, doc_id, actor, f"Human-in-the-Loop ({action.capitalize()})", details)
        conn.commit()
        conn.close()

        if action in ["approve", "reject"]:
            _dispatch_webhook(f"document.{action}d", {
                "document_id": doc_id,
                "status": new_status,
                "reviewer": actor,
                "reason": reason,
                "verified_fields": {k: v.get("value") for k, v in fields.items()},
            })

        return DocumentService.get_document(doc_id)

    @staticmethod
    def delete_document(doc_id: str) -> bool:
        conn = get_connection()
        row = conn.execute("SELECT file_path FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if not row:
            conn.close()
            return False
        conn.execute("DELETE FROM audit_logs WHERE document_id = ?", (doc_id,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()
        conn.close()
        for path in [row["file_path"], os.path.join(settings.STORAGE_DIR, doc_id)]:
            if path and os.path.isfile(path):
                os.remove(path)
            elif path and os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
        return True

    @staticmethod
    def region_text(doc: Dict[str, Any], region: Dict[str, Any]) -> Dict[str, Any]:
        """Text of the words inside a box drawn on the page (percent coordinates)."""
        from app.engine.pipelines.custom_schema import _words_in_region
        text, box = _words_in_region(region, load_words(doc))
        return {"text": text or "", "bounding_box": box}

    @staticmethod
    def add_field(doc_id: str, label: Optional[str], data_type: Optional[str] = None, value: Any = None,
                  region: Optional[Dict[str, Any]] = None, actor: str = "human_reviewer") -> Optional[Dict[str, Any]]:
        """
        Adds a field the extractor did not produce: read from a region drawn on the page, or typed in.
        Without a label, the label next to or above the drawn box is used; without a type, it is inferred.
        """
        from app.engine.pipelines.generic import slugify, guess_type
        doc = DocumentService.get_document(doc_id)
        if not doc:
            return None
        fields = doc["fields"]
        if not label:
            label = (DocumentService.suggest_label(doc, region) if region else None) or f"Field {len(fields) + 1}"
        if not data_type:
            text = value or (DocumentService.region_text(doc, region)["text"] if region else "")
            data_type = guess_type(text)[0] if text else "text"
            if data_type not in ("text", "number", "date", "currency", "email"):
                data_type = "text"
        name = base = slugify(label)
        i = 2
        while name in fields:
            name = f"{base}_{i}"
            i += 1

        box = None
        if region:
            found = DocumentService.region_text(doc, region)
            box = found["bounding_box"] or region
            if value in (None, ""):
                value = found["text"] or None
        err = None
        if value not in (None, ""):
            value, err = coerce_value(value, data_type, [])
        else:
            value = None

        fields[name] = {
            "field_name": name,
            "display_name": label,
            "value": value,
            "confidence": 1.0 if value is not None else 0.0,
            "bounding_box": box,
            "field_type": data_type,
            "validation_error": err,
            "is_manually_edited": True,
            "is_manually_added": True,
            "extraction_method": "reviewer",
            # remembered so "Save as Template" can find the value in the same place on similar documents
            "template_region": region,
        }
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET fields_json = ? WHERE id = ?", (json.dumps(fields), doc_id))
        _audit(cursor, doc_id, actor, "Human-in-the-Loop (Field Added)", {"modified_fields": {name: {"old": None, "new": value}}})
        conn.commit()
        conn.close()
        return DocumentService.get_document(doc_id)

    @staticmethod
    def rename_field(doc_id: str, field_name: str, display_name: str, actor: str = "human_reviewer") -> Optional[Dict[str, Any]]:
        """Changes a field's label. The label printed on the document is kept so templates still find it."""
        doc = DocumentService.get_document(doc_id)
        if not doc or field_name not in doc["fields"]:
            return None
        fld = doc["fields"][field_name]
        old = fld.get("display_name") or field_name
        if old == display_name:
            return doc
        fld.setdefault("source_label", old)
        fld["display_name"] = display_name
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET fields_json = ? WHERE id = ?", (json.dumps(doc["fields"]), doc_id))
        _audit(cursor, doc_id, actor, "Human-in-the-Loop (Field Renamed)", {"renamed": {field_name: {"old": old, "new": display_name}}})
        conn.commit()
        conn.close()
        return DocumentService.get_document(doc_id)

    @staticmethod
    def suggest_label(doc: Dict[str, Any], region: Dict[str, Any]) -> Optional[str]:
        """
        A name for a value drawn on the page: the label just left of it on the same line
        ("Room:  206"), or else the line directly above it ("Date of Birth" over the date).
        """
        from app.engine.pipelines.generic import layout_lines, _segment_text, _box
        words = [w for w in load_words(doc) if w["page"] == region.get("page", 1)]
        first_line_mid = None
        inside = [w for w in words if region["x0"] <= (w["x0"] + w["x1"]) / 2 <= region["x1"]
                  and region["y0"] <= (w["y0"] + w["y1"]) / 2 <= region["y1"]]
        if inside:
            top = min(inside, key=lambda w: (w["y0"], w["x0"]))
            first_line_mid = (top["y0"] + top["y1"]) / 2
        mid_y = first_line_mid if first_line_mid is not None else (region["y0"] + region["y1"]) / 2

        # Words just left of the box on its first line, read right-to-left until a wide gap (the label beside it)
        left = sorted([w for w in words if w not in inside and w["x1"] <= region["x0"] + 0.5
                       and w["y0"] - 0.3 <= mid_y <= w["y1"] + 0.3], key=lambda w: -w["x1"])
        run = []
        for w in left:
            edge = run[-1]["x0"] if run else region["x0"]
            if edge - w["x1"] > (6.0 if not run else 1.5):
                break
            run.append(w)
        candidate = " ".join(w["text"] for w in reversed(run)) if run else None

        # Otherwise the text directly above the box ("Date of Birth" printed over its value)
        if not candidate:
            best_above = None
            for line in layout_lines(words):
                for seg in line:
                    b = _box(seg)
                    if any(w in inside for w in seg):
                        continue
                    if b["y1"] <= region["y0"] + 0.3 and region["y0"] - b["y1"] < 3 and b["x0"] < region["x1"] and b["x1"] > region["x0"]:
                        if best_above is None or b["y1"] > best_above[0]:
                            best_above = (b["y1"], _segment_text(seg)[0].strip())
            candidate = best_above[1] if best_above else None
        if not candidate:
            return None
        # "Room Type: STKT  Clerk:" → the last "Label:" before the value; otherwise the whole short text
        labels = re.findall(r"([A-Za-z][\w /#&().'\-]{0,40}?)\s*:\s*$", candidate)
        label = labels[-1] if labels else candidate.rstrip(":").strip()
        return label if 0 < len(label) <= 40 else None

    @staticmethod
    def remove_field(doc_id: str, field_name: str, actor: str = "human_reviewer") -> Optional[Dict[str, Any]]:
        doc = DocumentService.get_document(doc_id)
        if not doc or field_name not in doc["fields"]:
            return None
        removed = doc["fields"].pop(field_name)
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE documents SET fields_json = ? WHERE id = ?", (json.dumps(doc["fields"]), doc_id))
        _audit(cursor, doc_id, actor, "Human-in-the-Loop (Field Removed)",
               {"modified_fields": {field_name: {"old": removed.get("value"), "new": None}}})
        conn.commit()
        conn.close()
        return DocumentService.get_document(doc_id)
