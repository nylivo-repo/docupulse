from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends
from app.core.database import get_connection
from app.core.security import check_scope
from app.models.schemas import AnalyticsSummary

router = APIRouter(prefix="/analytics", tags=["SaaS Analytics"])

@router.get("", response_model=AnalyticsSummary)
def get_analytics(auth: dict = Depends(check_scope("doc:read"))):
    """Retrieves operational metrics, straight-through processing rates, and quota statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    me = auth["user_id"]  # every figure covers only the caller's own documents
    cursor.execute("SELECT COUNT(*) as total, AVG(overall_confidence) as avg_conf FROM documents WHERE owner_id = ?", (me,))
    row_tot = cursor.fetchone()
    total_docs = row_tot["total"] or 0
    avg_conf = round(float(row_tot["avg_conf"] or 0.0), 3)

    cursor.execute("SELECT status, COUNT(*) as cnt FROM documents WHERE owner_id = ? GROUP BY status", (me,))
    status_counts = {r["status"]: r["cnt"] for r in cursor.fetchall()}

    cursor.execute("SELECT doc_type, COUNT(*) as cnt FROM documents WHERE owner_id = ? GROUP BY doc_type", (me,))
    type_counts = {r["doc_type"]: r["cnt"] for r in cursor.fetchall()}

    approved_count = status_counts.get("approved", 0)
    needs_review_count = status_counts.get("needs_review", 0)
    rejected_count = status_counts.get("rejected", 0)
    queued_count = status_counts.get("queued", 0)
    processing_count = status_counts.get("processing", 0)
    failed_count = status_counts.get("failed", 0)

    stp_rate = round((approved_count / total_docs * 100), 1) if total_docs > 0 else 0.0

    # Quota from api keys
    cursor.execute("SELECT SUM(quota_limit) as q_tot, SUM(quota_used) as q_usd FROM api_keys WHERE is_active = 1 AND owner_id = ?", (me,))
    quota_row = cursor.fetchone()
    q_tot = quota_row["q_tot"] or 0
    q_usd = quota_row["q_usd"] or 0

    # Volume over the last 7 days, from document ingestion dates
    today = datetime.now(timezone.utc).date()
    # Grouped by day here rather than in SQL, where date functions differ between databases
    cursor.execute("SELECT created_at, status FROM documents WHERE created_at >= ? AND owner_id = ?",
                   ((today - timedelta(days=6)).isoformat(), me))
    by_day: dict = {}
    for r in cursor.fetchall():
        day = by_day.setdefault(r["created_at"][:10], {"cnt": 0, "stp": 0})
        day["cnt"] += 1
        day["stp"] += 1 if r["status"] == "approved" else 0
    volume_by_day = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        r = by_day.get(d.isoformat(), {"cnt": 0, "stp": 0})
        volume_by_day.append({"day": d.strftime("%a"), "date": d.isoformat(), "count": r["cnt"], "stp": r["stp"]})

    conn.close()

    return AnalyticsSummary(
        total_documents=total_docs,
        straight_through_rate=stp_rate,
        avg_confidence=avg_conf,
        needs_review_count=needs_review_count,
        approved_count=approved_count,
        rejected_count=rejected_count,
        queued_count=queued_count,
        processing_count=processing_count,
        failed_count=failed_count,
        docs_by_type=type_counts,
        credits_used=q_usd,
        credits_total=q_tot,
        volume_by_day=volume_by_day
    )
