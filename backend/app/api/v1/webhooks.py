import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, field_validator
from app.core.database import get_connection
from app.core.security import check_scope
from app.models.schemas import _http_url, WebhookSubscriptionCreate, WebhookSubscriptionResponse, WebhookDeliveryLog
from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhooks", tags=["Webhooks & Event Streaming"])

class WebhookTestRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _http_url(v)
    event: str = "document.completed"
    secret: str = "whsec_test"
    sample_data: Dict[str, Any] = {
        "document_id": "doc_test_12345",
        "doc_type": "contracts",
        "status": "approved",
        "overall_confidence": 0.96
    }

@router.get("", response_model=List[WebhookSubscriptionResponse])
def list_webhooks(auth: dict = Depends(check_scope("admin"))):
    """Lists all configured webhook subscriptions."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM webhooks WHERE is_active = 1 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append(WebhookSubscriptionResponse(
            id=r["id"],
            url=r["url"],
            events=json.loads(r["events_json"]),
            secret=r["secret"],
            is_active=bool(r["is_active"]),
            created_at=r["created_at"],
            successful_deliveries=r["successful_deliveries"],
            failed_deliveries=r["failed_deliveries"]
        ))
    return result

@router.post("", response_model=WebhookSubscriptionResponse, status_code=status.HTTP_201_CREATED)
def create_webhook(payload: WebhookSubscriptionCreate, auth: dict = Depends(check_scope("admin"))):
    """Registers a new webhook destination URL for real-time IDP pipeline events."""
    wh_id = f"wh_{uuid.uuid4().hex[:10]}"
    secret = payload.secret or f"whsec_{secrets.token_hex(12)}"
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO webhooks (id, url, events_json, secret, is_active, created_at, successful_deliveries, failed_deliveries)
        VALUES (?, ?, ?, ?, 1, ?, 0, 0)
    """, (wh_id, payload.url, json.dumps(payload.events), secret, now_str))
    conn.commit()
    conn.close()

    return WebhookSubscriptionResponse(
        id=wh_id,
        url=payload.url,
        events=payload.events,
        secret=secret,
        is_active=True,
        created_at=now_str,
        successful_deliveries=0,
        failed_deliveries=0
    )

@router.delete("/{wh_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(wh_id: str, auth: dict = Depends(check_scope("admin"))):
    """Removes a webhook subscription."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE webhooks SET is_active = 0 WHERE id = ?", (wh_id,))
    conn.commit()
    conn.close()
    return None

@router.post("/test")
async def test_webhook_delivery(payload: WebhookTestRequest, auth: dict = Depends(check_scope("admin"))):
    """Simulates an immediate webhook test dispatch to test client connectivity and payload ingestion."""
    res = await WebhookService.send_to_webhook(
        webhook_id="wh-test-simulator",
        url=payload.url,
        secret=payload.secret,
        event=payload.event,
        payload=payload.sample_data
    )
    return res

@router.post("/echo", include_in_schema=True)
async def webhook_echo_receiver(request: Request):
    """Built-in receiver for testing webhooks without any outside service: echoes what it received."""
    body = await request.body()
    h = request.headers
    return {"received": True, "event": h.get("X-IDP-Event") or h.get("X-DocuPulse-Event"),
            "signature": h.get("X-IDP-Signature") or h.get("X-DocuPulse-Signature"), "bytes": len(body)}


@router.get("/logs", response_model=List[WebhookDeliveryLog])
def list_delivery_logs(limit: int = 20, auth: dict = Depends(check_scope("admin"))):
    """Fetches recent webhook dispatch logs."""
    conn = get_connection()
    cursor = conn.cursor()
    # fetchmany instead of LIMIT/TOP, which differ between SQLite, PostgreSQL and SQL Server
    cursor.execute("""SELECT * FROM webhook_logs ORDER BY "timestamp" DESC""")
    rows = cursor.fetchmany(max(1, min(limit, 500)))
    conn.close()

    result = []
    for r in rows:
        result.append(WebhookDeliveryLog(
            id=r["id"],
            webhook_id=r["webhook_id"],
            event=r["event"],
            status_code=r["status_code"],
            success=bool(r["success"]),
            payload=json.loads(r["payload_json"]),
            response_body=r["response_body"],
            timestamp=r["timestamp"],
            duration_ms=r["duration_ms"]
        ))
    return result
