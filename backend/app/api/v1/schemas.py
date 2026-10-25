import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from app.core.database import get_connection
from app.core.security import check_scope
from app.models.schemas import CustomSchemaCreate, CustomSchemaResponse, CustomSchemaFieldDefinition
from app.services.document_service import DocumentService, BUILTIN_PIPELINES
from app.engine.pipelines.generic import make_fingerprint

router = APIRouter(prefix="/schemas", tags=["Templates (Custom Schemas)"])

RESERVED_CODES = {"auto", "generic", "custom", "all"}

_LIST_SQL = """
    SELECT s.*, (SELECT COUNT(*) FROM documents d WHERE d.schema_id = s.id OR d.doc_type = s.document_type_code) as doc_count
    FROM custom_schemas s
"""


def _row_to_schema(r) -> CustomSchemaResponse:
    return CustomSchemaResponse(
        id=r["id"],
        name=r["name"],
        document_type_code=r["document_type_code"],
        description=r["description"] or "",
        fields=json.loads(r["fields_json"]),
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        is_active=bool(r["is_active"]),
        documents_count=r["doc_count"] or 0,
        base_pipeline=r["base_pipeline"],
        fingerprint=r["fingerprint"],
    )


def _validate(payload: CustomSchemaCreate):
    if not payload.fields:
        raise HTTPException(status_code=400, detail="A template needs at least one field.")
    names = [f.name for f in payload.fields]
    if len(set(names)) != len(names):
        raise HTTPException(status_code=400, detail="Field names must be unique within a template.")
    for f in payload.fields:
        if f.regex_pattern:
            try:
                re.compile(f.regex_pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Field '{f.name}': invalid regex ({e}).")
        if f.data_type == "enum" and not f.enum_values:
            raise HTTPException(status_code=400, detail=f"Field '{f.name}': enum fields need allowed values.")


def _fields_json(payload: CustomSchemaCreate) -> str:
    return json.dumps([f.model_dump(exclude_none=True) for f in payload.fields])


@router.get("", response_model=List[CustomSchemaResponse])
def list_schemas(auth: dict = Depends(check_scope("doc:read"))):
    """
    Lists all active templates. Everyone can pick a template when uploading or re-running; only
    admins manage them. The sample header text (fingerprint) is shown to admins only, since it
    comes from someone's document.
    """
    conn = get_connection()
    rows = conn.execute(_LIST_SQL + " WHERE is_active = 1 ORDER BY created_at DESC").fetchall()
    conn.close()
    out = [_row_to_schema(r) for r in rows]
    if "admin" not in auth["scopes"]:
        for s in out:
            s.fingerprint = None
    return out


@router.post("", response_model=CustomSchemaResponse, status_code=status.HTTP_201_CREATED)
def create_schema(payload: CustomSchemaCreate, auth: dict = Depends(check_scope("schema:manage"))):
    """Creates a template: the fields to extract, with labels, aliases, types, regex rules and thresholds."""
    code = re.sub(r"[^a-z0-9_]+", "_", payload.document_type_code.strip().lower()).strip("_")
    if not code or code in RESERVED_CODES:
        raise HTTPException(status_code=400, detail=f"'{payload.document_type_code}' cannot be used as a document type code.")
    _validate(payload)

    conn = get_connection()
    if conn.execute("SELECT id FROM custom_schemas WHERE document_type_code = ? AND is_active = 1", (code,)).fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail=f"Document type code '{code}' already exists.")
    schema_id = f"schema-{uuid.uuid4().hex[:8]}"
    now_str = datetime.now(timezone.utc).isoformat()
    base = payload.base_pipeline if payload.base_pipeline in BUILTIN_PIPELINES else None
    conn.execute("""
        INSERT INTO custom_schemas (id, name, document_type_code, description, fields_json, created_at, updated_at, is_active, base_pipeline, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    """, (schema_id, payload.name, code, payload.description, _fields_json(payload), now_str, now_str, base, payload.fingerprint))
    conn.commit()
    row = conn.execute(_LIST_SQL + " WHERE s.id = ?", (schema_id,)).fetchone()
    conn.close()
    return _row_to_schema(row)


@router.put("/{schema_id}", response_model=CustomSchemaResponse)
def update_schema(schema_id: str, payload: CustomSchemaCreate, auth: dict = Depends(check_scope("schema:manage"))):
    """Replaces a template's name, description and fields. The document type code stays the same."""
    _validate(payload)
    conn = get_connection()
    if not conn.execute("SELECT 1 FROM custom_schemas WHERE id = ? AND is_active = 1", (schema_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Template not found")
    conn.execute("UPDATE custom_schemas SET name = ?, description = ?, fields_json = ?, updated_at = ? WHERE id = ?",
                 (payload.name, payload.description, _fields_json(payload), datetime.now(timezone.utc).isoformat(), schema_id))
    conn.commit()
    row = conn.execute(_LIST_SQL + " WHERE s.id = ?", (schema_id,)).fetchone()
    conn.close()
    return _row_to_schema(row)


class TemplateFromDocumentRequest(BaseModel):
    name: str
    document_type_code: str
    description: str = ""
    field_names: Optional[List[str]] = None  # defaults to every field that has a value
    use_regions: bool = True  # remember where each value sits on the page, for fixed-layout forms


@router.post("/from-document/{doc_id}", response_model=CustomSchemaResponse, status_code=status.HTTP_201_CREATED)
def create_schema_from_document(doc_id: str, payload: TemplateFromDocumentRequest, auth: dict = Depends(check_scope("doc:write"))):
    """
    Builds a template from one of the caller's reviewed documents: each chosen field keeps its label,
    type and, optionally, its page position, so similar documents are extracted the same way.
    Any user may do this from Review; managing templates otherwise is for admins.
    """
    doc = DocumentService.get_document(doc_id)
    if not doc or doc.get("owner_id") != auth["user_id"]:
        raise HTTPException(status_code=404, detail="Document not found")
    chosen = payload.field_names or [k for k, f in doc["fields"].items() if f.get("value") not in (None, "")]
    fields = []
    for name in chosen:
        f = doc["fields"].get(name)
        if not f:
            continue
        label = f.get("display_name") or name
        d_type = f.get("field_type") if f.get("field_type") in ("text", "number", "date", "currency") else "text"
        # A value the reviewer typed (not read off the page) may not exist on other documents, so it is optional
        typed_only = f.get("is_manually_added") and not f.get("template_region")
        # A renamed field keeps the label printed on the document as an alias, so it is still found
        aliases = list(dict.fromkeys(a for a in [label, f.get("source_label")] if a))
        definition = {"name": name, "label": label, "data_type": d_type, "required": not typed_only,
                      "confidence_threshold": 0.75, "aliases": aliases}
        box = f.get("bounding_box")
        raw_text = (doc.get("raw_text") or "").lower()
        label_in_text = any(a.lower() in raw_text for a in aliases)
        repeated = sum(1 for g in doc["fields"].values() if (g.get("source_label") or g.get("display_name")) ==
                       (f.get("source_label") or f.get("display_name"))) > 1
        if f.get("template_region"):
            # Drawn by the reviewer: read that area first on similar documents
            definition["region"] = f["template_region"]
            definition["locate"] = "region"
        elif box and (not label_in_text or repeated):
            # No printed label to find it by ("Person 1"), or a label used twice ("Time"): its position decides
            definition["region"] = {"page": box.get("page", 1),
                                    "x0": max(0.0, box["x0"] - 1.0), "y0": max(0.0, box["y0"] - 0.5),
                                    "x1": min(100.0, box["x1"] + 4.0), "y1": min(100.0, box["y1"] + 0.5)}
            definition["locate"] = "region"
        elif payload.use_regions and box:
            definition["region"] = {"page": box.get("page", 1),
                                    "x0": max(0.0, box["x0"] - 2.0), "y0": max(0.0, box["y0"] - 1.0),
                                    "x1": min(100.0, box["x1"] + 8.0), "y1": min(100.0, box["y1"] + 1.0)}
        if not box and not label_in_text:
            definition["required"] = False  # nothing to locate it by on other documents
        fields.append(CustomSchemaFieldDefinition(**definition))
    if not fields:
        raise HTTPException(status_code=400, detail="The document has no extracted fields to build a template from.")
    # A contract, passport or invoice keeps its built-in rules (MRZ checks, invoice math) under the template
    base = doc["doc_type"] if doc["doc_type"] in BUILTIN_PIPELINES else doc["metadata"].get("base_pipeline")
    return create_schema(CustomSchemaCreate(name=payload.name, document_type_code=payload.document_type_code,
                                            description=payload.description or f"Created from {doc['title']}",
                                            fields=fields, base_pipeline=base,
                                            fingerprint=make_fingerprint(doc.get("raw_text") or "")), auth)


@router.delete("/{schema_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schema(schema_id: str, auth: dict = Depends(check_scope("schema:manage"))):
    """Deactivates a template and frees its document type code for reuse."""
    conn = get_connection()
    row = conn.execute("SELECT document_type_code FROM custom_schemas WHERE id = ?", (schema_id,)).fetchone()
    if row and row["document_type_code"] in BUILTIN_PIPELINES:
        conn.close()
        raise HTTPException(status_code=400, detail="Built-in templates can be edited but not deleted.")
    if row:
        conn.execute("UPDATE custom_schemas SET is_active = 0, document_type_code = ? WHERE id = ?",
                     (f"{row['document_type_code']}__deleted_{schema_id}", schema_id))
    conn.commit()
    conn.close()
    return None
