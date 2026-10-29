from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from enum import Enum

class DocumentStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"

class BoundingBox(BaseModel):
    page: int = 1
    x0: float
    y0: float
    x1: float
    y1: float

class ExtractedField(BaseModel):
    field_name: str
    display_name: Optional[str] = None
    value: Any = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    bounding_box: Optional[BoundingBox] = None
    validation_error: Optional[str] = None
    is_manually_edited: bool = False
    is_manually_added: bool = False
    original_value: Optional[Any] = None
    field_type: str = "text"
    extraction_method: Optional[str] = None

class AuditLogEntry(BaseModel):
    timestamp: str
    user: str
    action: str
    details: Dict[str, Any]

class DocumentBase(BaseModel):
    title: str
    doc_type: str
    schema_id: Optional[str] = None
    file_name: str
    file_size_bytes: int
    page_count: int = 1
    folder_id: Optional[str] = None

class DocumentResponse(DocumentBase):
    id: str
    status: DocumentStatus
    overall_confidence: float
    needs_review: bool
    created_at: str
    processed_at: Optional[str] = None
    fields: Dict[str, ExtractedField]
    raw_text: Optional[str] = None
    audit_trail: List[AuditLogEntry] = []
    file_url: Optional[str] = None
    page_urls: List[str] = []
    metadata: Dict[str, Any] = {}

class FieldUpdateItem(BaseModel):
    field_name: str
    value: Any

class FieldUpdateBatchRequest(BaseModel):
    fields: List[FieldUpdateItem]
    reason: Optional[str] = None

class CustomSchemaFieldDefinition(BaseModel):
    name: str
    label: str
    data_type: str  # text, number, date, currency, regex, enum
    required: bool = False
    regex_pattern: Optional[str] = None
    confidence_threshold: float = 0.70
    enum_values: Optional[List[str]] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None  # other labels the value may appear under
    region: Optional[BoundingBox] = None  # fixed page area, for templates saved from a sample
    locate: Optional[str] = None  # "region": read the region first (fields drawn on the page in Review)
    api_search: bool = False  # a search key of the template's lookup endpoint (?lastName=…)
    sensitive: bool = False  # personal data such as an SSN: masked in lookup results unless the key has pii:read

class CustomSchemaCreate(BaseModel):
    name: str
    document_type_code: str
    description: str = ""
    fields: List[CustomSchemaFieldDefinition]
    base_pipeline: Optional[str] = None  # contracts / identity / invoices: run those rules first
    fingerprint: Optional[str] = None  # header text of the sample document, to recognise similar ones
    api_enabled: bool = False  # publish GET /api/v1/lookup/<api_endpoint>
    api_endpoint: Optional[str] = Field(None, max_length=64)  # e.g. getPassportDetails, unique among templates

class CustomSchemaResponse(CustomSchemaCreate):
    id: str
    created_at: str
    updated_at: str
    is_active: bool = True
    documents_count: int = 0

class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = ["doc:read", "doc:write"]
    quota_limit: int = 10000

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    full_key: Optional[str] = None  # Only returned on creation
    created_at: str
    last_used: Optional[str] = None
    scopes: List[str]
    quota_limit: int
    quota_used: int
    is_active: bool = True

def _http_url(v: str) -> str:
    from urllib.parse import urlsplit
    p = urlsplit((v or "").strip())
    if p.scheme not in ("http", "https") or not p.netloc or p.username or p.password:
        raise ValueError("Use an http:// or https:// address without a username or password in it.")
    return v.strip()


class WebhookSubscriptionCreate(BaseModel):
    url: str = Field(..., max_length=2000)
    events: List[str] = ["document.completed", "document.needs_review"]
    secret: Optional[str] = Field(None, max_length=200)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _http_url(v)

class WebhookSubscriptionResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    secret: str
    is_active: bool
    created_at: str
    successful_deliveries: int = 0
    failed_deliveries: int = 0

class WebhookDeliveryLog(BaseModel):
    id: str
    webhook_id: str
    event: str
    status_code: int
    success: bool
    payload: Dict[str, Any]
    response_body: Optional[str] = None
    timestamp: str
    duration_ms: int

class AnalyticsSummary(BaseModel):
    total_documents: int
    straight_through_rate: float
    avg_confidence: float
    needs_review_count: int
    approved_count: int
    rejected_count: int
    queued_count: int
    processing_count: int
    failed_count: int = 0
    docs_by_type: Dict[str, int]
    credits_used: int
    credits_total: int
    volume_by_day: List[Dict[str, Any]]
