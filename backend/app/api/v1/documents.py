import os
import io
import re
import csv
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel
from app.core.config import settings
from app.core.security import check_scope
from app.core.database import get_connection
from app.api.v1.folders import owned_folder
from app.models.schemas import DocumentResponse, FieldUpdateBatchRequest
from app.services.document_service import DocumentService, BUILTIN_PIPELINES
from app.engine.sample_generator import create_all_samples
from app.engine.ocr_extractor import IMAGE_EXTS, TEXT_EXTS

router = APIRouter(prefix="/documents", tags=["Documents"])

ALLOWED_EXTS = [".pdf"] + IMAGE_EXTS + TEXT_EXTS
DOC_TYPES = ["auto", "generic", "custom"] + list(BUILTIN_PIPELINES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_document(doc_id: str, title: str, doc_type: str, schema_id: Optional[str], file_name: str, file_size: int,
                     path: str, owner_id: str, folder_id: Optional[str] = None):
    conn = get_connection()
    conn.execute("""
        INSERT INTO documents (id, title, doc_type, schema_id, status, file_name, file_size_bytes, file_path, page_count, overall_confidence, needs_review, created_at, fields_json, raw_text, metadata_json, owner_id, folder_id)
        VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, 1, 0.0, 0, ?, '{}', '', '{}', ?, ?)
    """, (doc_id, title, doc_type, schema_id, file_name, file_size, path, _now(), owner_id, folder_id))
    conn.commit()
    conn.close()


_NUMBER = re.compile(r"^[-+]?[\d,]*\.?\d+(?:[eE][-+]?\d+)?%?$")
_MAGIC = {
    ".pdf": [b"%PDF-"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
    ".tif": [b"II*\x00", b"MM\x00*"], ".tiff": [b"II*\x00", b"MM\x00*"],
    ".bmp": [b"BM"],
    ".webp": [b"RIFF"],
}


def _content_matches(ext: str, content: bytes) -> bool:
    """The file really is what its extension says (a renamed executable or HTML page is refused)."""
    if ext in _MAGIC:
        return any(content.startswith(m) for m in _MAGIC[ext]) and (ext != ".webp" or content[8:12] == b"WEBP")
    if ext in TEXT_EXTS:
        if b"\x00" in content[:4096]:
            return False
        try:
            content[:65536].decode("utf-8")
        except UnicodeDecodeError as e:
            if e.start < 65530:  # not just a multi-byte character cut at the boundary
                try:
                    content[:65536].decode("latin-1")
                except UnicodeDecodeError:
                    return False
        return True
    return False


def _csv_safe(value):
    """Stops spreadsheet formula injection: text starting with = + - @ is prefixed with ' (numbers are left alone)."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r") and not _NUMBER.match(value.strip()):
        return "'" + value
    return value


def _owned(doc_id: str, auth: dict) -> dict:
    """
    The document, if it belongs to the caller. Someone else's document answers exactly like a
    missing one, so its existence is not revealed.
    """
    doc = DocumentService.get_document(doc_id)
    if not doc or doc.get("owner_id") != auth["user_id"]:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


def _validate_type(doc_type: str, schema_id: Optional[str]):
    conn = get_connection()
    if schema_id:
        if not conn.execute("SELECT 1 FROM custom_schemas WHERE id = ? AND is_active = 1", (schema_id,)).fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail=f"Template '{schema_id}' does not exist.")
    elif doc_type == "custom":
        conn.close()
        raise HTTPException(status_code=400, detail="Choose a template (schema_id) for doc_type 'custom', or use doc_type 'auto'.")
    elif doc_type not in DOC_TYPES and not conn.execute(
            "SELECT 1 FROM custom_schemas WHERE document_type_code = ? AND is_active = 1", (doc_type,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Unknown doc_type '{doc_type}'. Use one of {DOC_TYPES} or a template code.")
    conn.close()


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = Form("auto"),
    schema_id: Optional[str] = Form(None),
    sync: bool = Form(True),  # False: returns at once with status 'queued'; listen on webhooks or poll
    folder_id: Optional[str] = Form(None),  # one of the caller's folders (GET /folders); empty = top level
    auth: dict = Depends(check_scope("doc:write"))
):
    """
    Ingests a PDF, image (scans and photos are OCR'd locally) or text file and extracts structured data.
    doc_type 'auto' detects the document type and matching template; 'generic' extracts any labelled values.
    """
    original_name = os.path.basename(file.filename or "document")
    file_ext = os.path.splitext(original_name)[1].lower()
    if file_ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{file_ext or 'none'}'. Allowed: {', '.join(ALLOWED_EXTS)}")
    schema_id = schema_id or None
    _validate_type(doc_type, schema_id)
    folder_id = folder_id or None
    conn = get_connection()
    try:
        owned_folder(conn, folder_id, auth["user_id"])
    finally:
        conn.close()

    # Read in chunks and stop at the limit, so an oversized upload never fills memory
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    chunks, size = [], 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"File is larger than {settings.MAX_UPLOAD_MB} MB.")
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if not _content_matches(file_ext, content):
        raise HTTPException(status_code=400, detail=f"The file's contents do not match its '{file_ext}' extension.")

    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    safe_name = re.sub(r"[^\w.\- ]", "_", original_name)
    saved_path = os.path.join(settings.STORAGE_DIR, "uploads", f"{doc_id}_{safe_name}")
    with open(saved_path, "wb") as buffer:
        buffer.write(content)

    title = os.path.splitext(original_name)[0].replace("_", " ").strip().title() or "Untitled Document"
    _insert_document(doc_id, title, doc_type, schema_id, original_name, len(content), saved_path, auth["user_id"], folder_id)

    if auth.get("key_id"):
        conn = get_connection()
        conn.execute("UPDATE api_keys SET quota_used = quota_used + 1, last_used = ? WHERE id = ?", (_now(), auth["key_id"]))
        conn.commit()
        conn.close()

    if sync:
        await DocumentService.process_document_pipeline(doc_id, saved_path, doc_type, schema_id)
    else:
        background_tasks.add_task(DocumentService.process_document_pipeline, doc_id, saved_path, doc_type, schema_id)
    return DocumentService.get_document(doc_id)


@router.get("", response_model=List[DocumentResponse])
def list_documents(
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    folder: Optional[str] = None,
    auth: dict = Depends(check_scope("doc:read"))
):
    """
    Lists the caller's own documents, with optional filters by document type and status.
    folder: a folder id for the documents directly in it, "root" for those in no folder; omitted lists all.
    """
    return DocumentService.list_documents(doc_type=doc_type, status=status, search=search, owner_id=auth["user_id"],
                                          folder=folder)


class MoveDocumentsRequest(BaseModel):
    ids: List[str]
    folder_id: Optional[str] = None  # null / empty = top level


@router.post("/move")
def move_documents(payload: MoveDocumentsRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Moves the caller's documents into one of their folders, or to the top level (folder_id null)."""
    folder_id = payload.folder_id or None
    conn = get_connection()
    try:
        owned_folder(conn, folder_id, auth["user_id"])
        own = {d["id"] for d in DocumentService.list_documents(owner_id=auth["user_id"])}
        moved = [i for i in payload.ids if i in own]
        for doc_id in moved:
            conn.execute("UPDATE documents SET folder_id = ? WHERE id = ? AND owner_id = ?", (folder_id, doc_id, auth["user_id"]))
        conn.commit()
    finally:
        conn.close()
    return {"moved": moved, "folder_id": folder_id}


@router.get("/{doc_id}", response_model=DocumentResponse)
def get_document(doc_id: str, auth: dict = Depends(check_scope("doc:read"))):
    """Retrieves a document with extracted fields, bounding boxes and audit trail."""
    return _owned(doc_id, auth)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(doc_id: str, auth: dict = Depends(check_scope("doc:write"))):
    """Deletes a document, its stored file, page images and audit trail."""
    _owned(doc_id, auth)
    DocumentService.delete_document(doc_id)
    return None


class BulkDeleteRequest(BaseModel):
    ids: List[str]


@router.post("/bulk-delete")
def bulk_delete_documents(payload: BulkDeleteRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Deletes several documents at once, with their stored files, page images and audit trails."""
    own = {d["id"] for d in DocumentService.list_documents(owner_id=auth["user_id"])}
    deleted = [d for d in dict.fromkeys(payload.ids) if d in own and DocumentService.delete_document(d)]
    return {"deleted": deleted, "not_found": [d for d in payload.ids if d not in deleted]}


class ReprocessRequest(BaseModel):
    doc_type: str = "auto"
    schema_id: Optional[str] = None


@router.post("/{doc_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(doc_id: str, payload: ReprocessRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Runs extraction again, e.g. with a different pipeline or a template created after upload."""
    doc = _owned(doc_id, auth)
    _validate_type(payload.doc_type, payload.schema_id)
    await DocumentService.process_document_pipeline(doc_id, doc["file_path"], payload.doc_type, payload.schema_id)
    return DocumentService.get_document(doc_id)


@router.patch("/{doc_id}/fields", response_model=DocumentResponse)
async def update_document_fields(doc_id: str, payload: FieldUpdateBatchRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Human-in-the-Loop review: updates changed fields, marks them verified and appends to the audit trail."""
    _owned(doc_id, auth)
    updates = [{"field_name": f.field_name, "value": f.value} for f in payload.fields]
    # The audit trail records who signed in, not a name the client sends
    return await DocumentService.update_fields_and_review(doc_id, updates, actor=auth["username"], action="update")


class RegionBox(BaseModel):
    page: int = 1
    x0: float
    y0: float
    x1: float
    y1: float


class AddFieldRequest(BaseModel):
    label: Optional[str] = None  # empty: named after the label beside or above the drawn box
    data_type: Optional[str] = None  # empty: inferred from the value
    value: Optional[str] = None  # typed value; when empty, the text inside `region` is used
    region: Optional[RegionBox] = None


class RenameFieldRequest(BaseModel):
    display_name: str


@router.post("/{doc_id}/region-text")
def read_region_text(doc_id: str, region: RegionBox, auth: dict = Depends(check_scope("doc:read"))):
    """Returns the text inside a box drawn on a page (coordinates in percent of the page)."""
    return DocumentService.region_text(_owned(doc_id, auth), region.model_dump())


@router.post("/{doc_id}/fields", response_model=DocumentResponse)
def add_document_field(doc_id: str, payload: AddFieldRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Adds a field the extractor missed, from a region drawn on the page or a typed value."""
    if not payload.region and not (payload.label or "").strip():
        raise HTTPException(status_code=400, detail="A typed field needs a label.")
    if payload.data_type and payload.data_type not in ("text", "number", "date", "currency", "email"):
        raise HTTPException(status_code=400, detail="data_type must be text, number, date, currency or email.")
    _owned(doc_id, auth)
    return DocumentService.add_field(doc_id, (payload.label or "").strip() or None, payload.data_type, payload.value,
                                     payload.region.model_dump() if payload.region else None, auth["username"])


@router.patch("/{doc_id}/fields/{field_name}/label", response_model=DocumentResponse)
def rename_document_field(doc_id: str, field_name: str, payload: RenameFieldRequest, auth: dict = Depends(check_scope("doc:write"))):
    """Renames a field's label (kept in templates and exports)."""
    if not payload.display_name.strip():
        raise HTTPException(status_code=400, detail="The label cannot be empty.")
    _owned(doc_id, auth)
    doc = DocumentService.rename_field(doc_id, field_name, payload.display_name.strip(), auth["username"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document or field not found")
    return doc


@router.delete("/{doc_id}/fields/{field_name}", response_model=DocumentResponse)
def remove_document_field(doc_id: str, field_name: str, auth: dict = Depends(check_scope("doc:write"))):
    """Removes a field from a document (for example one added by mistake)."""
    _owned(doc_id, auth)
    doc = DocumentService.remove_field(doc_id, field_name, auth["username"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document or field not found")
    return doc


@router.post("/{doc_id}/approve", response_model=DocumentResponse)
async def approve_document(doc_id: str, auth: dict = Depends(check_scope("doc:write"))):
    """Approves a document after review and notifies webhook subscribers."""
    _owned(doc_id, auth)
    return await DocumentService.update_fields_and_review(doc_id, [], actor=auth["username"], action="approve")


@router.post("/{doc_id}/reject", response_model=DocumentResponse)
async def reject_document(doc_id: str, reason: str = "Unreadable or invalid document",
                          auth: dict = Depends(check_scope("doc:write"))):
    """Rejects a document; the reason is stored on the document and in its audit trail."""
    _owned(doc_id, auth)
    return await DocumentService.update_fields_and_review(doc_id, [], actor=auth["username"], action="reject", reason=reason)


@router.get("/{doc_id}/preview/{image_name}")
def get_document_page_preview(doc_id: str, image_name: str, auth: dict = Depends(check_scope("doc:read"))):
    """Serves rendered page images for the review canvas."""
    if not re.fullmatch(r"page_\d{1,4}\.png", image_name) or not re.fullmatch(r"[\w\-]+", doc_id):
        raise HTTPException(status_code=400, detail="Invalid preview path")
    _owned(doc_id, auth)
    img_path = os.path.join(settings.STORAGE_DIR, doc_id, image_name)
    if os.path.exists(img_path):
        return FileResponse(img_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Page preview image not found")


@router.get("/{doc_id}/export/json")
def export_document_json(doc_id: str, auth: dict = Depends(check_scope("doc:read"))):
    """Exports extracted data as JSON."""
    doc = _owned(doc_id, auth)
    data = {
        "document_id": doc["id"],
        "title": doc["title"],
        "doc_type": doc["doc_type"],
        "status": doc["status"],
        "confidence": doc["overall_confidence"],
        "fields": {k: v.get("value") for k, v in doc["fields"].items()},
        "metadata": doc["metadata"],
        "exported_at": _now(),
    }
    return JSONResponse(content=data, headers={"Content-Disposition": f"attachment; filename={doc['id']}_extracted.json"})


@router.get("/{doc_id}/export/csv")
def export_document_csv(doc_id: str, auth: dict = Depends(check_scope("doc:read"))):
    """Exports extracted fields as a flat CSV."""
    doc = _owned(doc_id, auth)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Field Name", "Display Name", "Extracted Value", "Confidence", "Validation Error", "Manually Edited"])
    for f in doc["fields"].values():
        writer.writerow([_csv_safe(v) for v in (
            f.get("field_name"),
            f.get("display_name") or f.get("field_name"),
            "" if f.get("value") is None else f.get("value"),
            f.get("confidence"),
            f.get("validation_error") or "",
            "Yes" if f.get("is_manually_edited") else "No",
        )])
    # Tables (line items) follow the fields, each with its own header row
    for n, table in enumerate(doc["metadata"].get("tables") or [], start=1):
        writer.writerow([])
        writer.writerow([f"Table {n}"])
        writer.writerow([_csv_safe(c) for c in table.get("columns", [])])
        for row in table.get("rows", []):
            writer.writerow([_csv_safe(c) for c in row])
    return Response(content=output.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={doc['id']}_fields.csv"})


@router.get("/{doc_id}/export/xlsx")
def export_document_xlsx(doc_id: str, auth: dict = Depends(check_scope("doc:read"))):
    """Exports an Excel workbook: a Fields sheet, then one sheet per extracted table."""
    from app.services.xlsx_writer import build_xlsx
    doc = _owned(doc_id, auth)
    field_rows = [["Field", "Value", "Confidence", "Validation Error", "Manually Edited"]]
    for f in doc["fields"].values():
        field_rows.append([
            f.get("display_name") or f.get("field_name"),
            f.get("value"),
            f.get("confidence"),
            f.get("validation_error") or "",
            "Yes" if f.get("is_manually_edited") else "No",
        ])
    sheets = [("Fields", field_rows)]
    for n, table in enumerate(doc["metadata"].get("tables") or [], start=1):
        sheets.append((f"Table {n}", [table.get("columns", [])] + table.get("rows", [])))
    safe = re.sub(r"[^\w\-]+", "_", doc["title"]).strip("_") or doc["id"]
    return Response(
        content=build_xlsx(sheets),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={safe}.xlsx"},
    )


@router.post("/sample/{sample_type}", response_model=DocumentResponse)
async def process_sample_preset(sample_type: str, auth: dict = Depends(check_scope("doc:write"))):
    """
    1-click demo: ingests one of the bundled sample documents ('contract', 'passport' (US), 'invoice').
    Available only when the demo feature flag is on ([features] demo_presets in server.ini).
    """
    if not settings.DEMO_PRESETS:
        raise HTTPException(status_code=404, detail="Demo samples are turned off on this server.")
    samples = create_all_samples()
    if sample_type not in samples:
        raise HTTPException(status_code=400, detail=f"Invalid sample type. Must be one of: {list(samples.keys())}")

    src_path = samples[sample_type]
    file_name = os.path.basename(src_path)
    doc_id = f"doc_sample_{sample_type}_{uuid.uuid4().hex[:6]}"
    dest_path = os.path.join(settings.STORAGE_DIR, "uploads", f"{doc_id}_{file_name}")
    shutil.copyfile(src_path, dest_path)
    actual_type = {"contract": "contracts", "passport": "identity", "invoice": "invoices"}[sample_type]

    _insert_document(doc_id, file_name.replace(".pdf", "").replace("_", " "), actual_type, None,
                     file_name, os.path.getsize(dest_path), dest_path, auth["user_id"])
    await DocumentService.process_document_pipeline(doc_id, dest_path, actual_type)
    return DocumentService.get_document(doc_id)
