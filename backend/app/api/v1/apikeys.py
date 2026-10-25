import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, status
from app.core.database import get_connection
from app.core.security import check_scope, hash_api_key
from app.models.schemas import ApiKeyCreate, ApiKeyResponse

router = APIRouter(prefix="/keys", tags=["API Keys & SaaS Metering"])

@router.get("", response_model=List[ApiKeyResponse])
def list_api_keys(auth: dict = Depends(check_scope("admin"))):
    """Lists all active API keys for the current tenant with usage meters."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM api_keys WHERE is_active = 1 ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()

    result = []
    for r in rows:
        result.append(ApiKeyResponse(
            id=r["id"],
            name=r["name"],
            key_prefix=r["key_prefix"],
            created_at=r["created_at"],
            last_used=r["last_used"],
            scopes=json.loads(r["scopes_json"]),
            quota_limit=r["quota_limit"],
            quota_used=r["quota_used"],
            is_active=bool(r["is_active"])
        ))
    return result

@router.post("", response_model=ApiKeyResponse, status_code=status.HTTP_201_CREATED)
def create_api_key(payload: ApiKeyCreate, auth: dict = Depends(check_scope("admin"))):
    """
    Generates a new secure SaaS API key with specified scopes and quota.
    The full key is only displayed once upon generation.
    """
    raw_token = f"dp_live_{secrets.token_hex(16)}"
    key_prefix = f"{raw_token[:10]}..."
    key_id = str(uuid.uuid4())
    now_str = datetime.now(timezone.utc).isoformat()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO api_keys (id, name, key_hash, key_prefix, created_at, last_used, scopes_json, quota_limit, quota_used, is_active, owner_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?)
    """, (key_id, payload.name, hash_api_key(raw_token), key_prefix, now_str, now_str, json.dumps(payload.scopes),
          payload.quota_limit, auth["user_id"]))  # only the hash is kept; the key acts as its creator
    conn.commit()
    conn.close()

    return ApiKeyResponse(
        id=key_id,
        name=payload.name,
        key_prefix=key_prefix,
        full_key=raw_token,
        created_at=now_str,
        last_used=now_str,
        scopes=payload.scopes,
        quota_limit=payload.quota_limit,
        quota_used=0,
        is_active=True
    )

@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(key_id: str, auth: dict = Depends(check_scope("admin"))):
    """Immediately revokes and deactivates an API key."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE api_keys SET is_active = 0 WHERE id = ?", (key_id,))
    conn.commit()
    conn.close()
    return None
