import hashlib
import json
from fastapi import Cookie, Header, HTTPException, Security, status
from typing import Optional
from app.core.auth import ROLE_SCOPES, SESSION_COOKIE, get_user, user_for_session
from app.core.database import get_connection
from app.core.logging_config import set_request_user


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    session: Optional[str] = Cookie(None, alias=SESSION_COOKIE),
):
    """
    Identifies the caller: a signed-in browser session, or an API key (X-API-Key or Bearer).
    Every request is tied to a user; their role decides what they may do, and an API key can
    only narrow that further. Anonymous requests are refused.
    """
    key = None
    if x_api_key:
        key = x_api_key.strip()
    elif authorization and authorization.startswith("Bearer "):
        key = authorization.replace("Bearer ", "").strip()

    if not key:
        user = user_for_session(session)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Please sign in.")
        set_request_user(user["username"])
        if user.get("must_change_password"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Change your temporary password first (user menu → Change password).")
        return {"user_id": user["id"], "username": user["username"], "role": user["role"],
                "scopes": ROLE_SCOPES.get(user["role"], []), "key_id": None}

    conn = get_connection()
    # Keys are stored as SHA-256 hashes only
    row = conn.execute("""
        SELECT id, name, scopes_json, quota_limit, quota_used, owner_id
        FROM api_keys WHERE key_hash = ? AND is_active = 1
    """, (hash_api_key(key),)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or deactivated API Key provided.")
    if row["quota_used"] >= row["quota_limit"]:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Monthly processing quota exceeded for this API Key.")
    owner = get_user(row["owner_id"]) if row["owner_id"] else None
    if not owner or not owner["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="This API Key's owner is no longer active.")
    set_request_user(f'{owner["username"]} (API key {row["name"]})')
    role_scopes = ROLE_SCOPES.get(owner["role"], [])
    return {"user_id": owner["id"], "username": owner["username"], "role": owner["role"],
            "scopes": [s for s in json.loads(row["scopes_json"]) if s in role_scopes], "key_id": row["id"]}


def check_scope(required_scope: str):
    def dependency(auth: dict = Security(verify_api_key)):
        if required_scope in auth.get("scopes", []):
            return auth
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrators only." if required_scope == "admin" else f"Missing permission: '{required_scope}'",
        )
    return dependency
