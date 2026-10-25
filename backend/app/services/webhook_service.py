import hmac
import hashlib
import json
import time
import uuid
import httpx
from datetime import datetime, timezone
from typing import Dict, Any
from app.core.database import get_connection

class WebhookService:
    @staticmethod
    async def dispatch_event(event: str, payload: Dict[str, Any]):
        """Dispatches event to active webhook subscribers."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, url, events_json, secret FROM webhooks WHERE is_active = 1")
        webhooks = cursor.fetchall()
        conn.close()

        for wh in webhooks:
            subscribed_events = json.loads(wh["events_json"])
            if event in subscribed_events or "*" in subscribed_events:
                await WebhookService.send_to_webhook(
                    webhook_id=wh["id"],
                    url=wh["url"],
                    secret=wh["secret"],
                    event=event,
                    payload=payload
                )

    @staticmethod
    async def send_to_webhook(webhook_id: str, url: str, secret: str, event: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Sends payload to a specific webhook endpoint and records delivery log."""
        start_time = time.time()
        body = json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": payload})
        # Receivers verify HMAC-SHA256(secret, body); the secret itself is never sent
        signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers = {
            "Content-Type": "application/json",
            "X-DocuPulse-Event": event,
            "X-DocuPulse-Signature": f"sha256={signature}",
            "User-Agent": "DocuPulse-IDP-Webhook-Dispatcher/1.0"
        }
        
        status_code = 0
        success = False
        resp_text = ""

        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                res = await client.post(url, content=body, headers=headers)
                status_code = res.status_code
                resp_text = res.text[:500]
                success = (200 <= status_code < 300)
        except Exception as e:
            status_code = 0
            resp_text = f"Connection error: {type(e).__name__}: {e}"
            success = False

        duration_ms = int((time.time() - start_time) * 1000)
        now_str = datetime.now(timezone.utc).isoformat()
        log_id = str(uuid.uuid4())

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO webhook_logs (id, webhook_id, event, status_code, success, payload_json, response_body, "timestamp", duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (log_id, webhook_id, event, status_code, 1 if success else 0, json.dumps(payload), resp_text, now_str, duration_ms))

        if success:
            cursor.execute("UPDATE webhooks SET successful_deliveries = successful_deliveries + 1 WHERE id = ?", (webhook_id,))
        else:
            cursor.execute("UPDATE webhooks SET failed_deliveries = failed_deliveries + 1 WHERE id = ?", (webhook_id,))

        conn.commit()
        conn.close()

        return {
            "log_id": log_id,
            "status_code": status_code,
            "success": success,
            "duration_ms": duration_ms,
            "response": resp_text
        }
