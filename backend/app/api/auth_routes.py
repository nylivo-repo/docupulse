"""
Sign-in endpoints: local username/password, Okta (OpenID Connect, authorization code + PKCE),
sign-out and "who am I". The local admin login always works, as a backup to Okta.
"""
import base64
import logging
import hashlib
import json
import secrets
import time
from typing import Optional
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core import auth as A
from app.core.config import settings
from app.core.logging_config import audit, set_request_user

router = APIRouter(prefix="/api/auth", tags=["Sign-in"])

# An Okta sign-in in progress (state + PKCE verifier) travels in a short-lived encrypted cookie, not in
# server memory, so the callback works on any API instance behind a load balancer (no sticky sessions).
_OKTA_COOKIE = "idp_okta"
_OKTA_MAX_AGE = 600

# Failed sign-ins per username and per client address (in memory), to stop password guessing
_failures: dict = {}
_ip_failures: dict = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "-"


def _recent(store: dict, key: str) -> list:
    window = time.time() - settings.LOGIN_LOCKOUT_MINUTES * 60
    hits = [t for t in store.get(key, []) if t > window]
    if hits:
        store[key] = hits
    else:
        store.pop(key, None)
    return hits


def _prune():
    """Keeps the failure tables small (many random usernames cannot exhaust memory)."""
    if len(_failures) + len(_ip_failures) > 10000:
        for store in (_failures, _ip_failures):
            for k in list(store):
                _recent(store, k)


# Where people land after Okta sign-in: the separately deployed UI, or this server in single-server mode
_UI = settings.FRONTEND_URL


def _cookie_options(request: Request) -> dict:
    """Cookie flags from config/server.ini, so the UI can be served from another host of the same site."""
    secure = request.url.scheme == "https" if settings.COOKIE_SECURE == "auto" else settings.COOKIE_SECURE == "true"
    samesite = settings.COOKIE_SAMESITE if settings.COOKIE_SAMESITE in ("lax", "strict", "none") else "lax"
    if samesite == "none":
        secure = True  # browsers reject SameSite=None without Secure
    return {"httponly": True, "samesite": samesite, "secure": secure, "path": "/"}


def _set_session_cookie(response: Response, request: Request, user_id: str):
    response.set_cookie(A.SESSION_COOKIE, A.create_session(user_id), max_age=A.SESSION_HOURS * 3600,
                        **_cookie_options(request))


def _public_user(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"], "display_name": u["display_name"], "email": u["email"],
            "role": u["role"], "auth_source": u["auth_source"], "groups": u["groups"],
            "must_change_password": bool(u.get("must_change_password"))}


@router.get("/config")
def sign_in_options():
    """What the login page should offer. Needs no sign-in."""
    s = A.get_auth_settings()
    okta = s["okta"]
    configured = bool(okta.get("issuer") and okta.get("client_id") and okta.get("client_secret") and okta.get("redirect_uri"))
    return {"mode": s["mode"], "okta_available": s["mode"] == "okta" and configured,
            "ldap_available": s["mode"] == "ldap" and bool(s["ldap"].get("server_url") and s["ldap"].get("user_base_dn")),
            "features": {"demo_presets": settings.DEMO_PRESETS}}


class LoginRequest(BaseModel):
    username: str
    password: str


def _sign_in_directory_user(person: dict, settings: dict) -> dict:
    """Creates or updates the app user for someone the directory (AD/LDAP) just authenticated."""
    role = A.role_for_groups(person["groups"], settings)
    user = A.find_user(person["username"], "ldap")
    if user and user["role_locked"]:
        role = user["role"]
    if not role:
        raise HTTPException(status_code=403, detail="Your account is not in any group allowed to use this app. Ask an admin for access.")
    if user:
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="Your account has been disabled. Ask an admin for access.")
        return A.update_user(user["id"], role=role, groups_json=json.dumps(person["groups"]),
                             display_name=person["display_name"], email=person["email"])
    return A.create_user(person["username"], role, "ldap", display_name=person["display_name"],
                         email=person["email"], groups=person["groups"])


@router.post("/login")
async def local_login(payload: LoginRequest, request: Request, response: Response):
    """
    Username/password sign-in. In AD/LDAP mode the directory checks the password; in Local mode
    the app does. Local admins can always sign in (the break-glass account), so a broken Okta or
    directory setup can never lock administrators out.
    """
    key = payload.username.strip().lower()[:200]
    ip = _client_ip(request)
    _prune()
    fails = _recent(_failures, key)
    if len(fails) >= settings.LOGIN_MAX_FAILURES or len(_recent(_ip_failures, ip)) >= settings.LOGIN_MAX_FAILURES_PER_IP:
        audit("login", "blocked", username=key, reason="too many failed attempts")
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {settings.LOGIN_LOCKOUT_MINUTES} minutes.")

    def failed(reason: str):
        _failures[key] = fails + [time.time()]
        _ip_failures[ip] = _recent(_ip_failures, ip) + [time.time()]
        audit("login", "failure", username=key, reason=reason, method=settings_["mode"])

    settings_ = A.get_auth_settings()
    reason = None
    if settings_["mode"] == "ldap":
        import asyncio
        from app.core.ldap_auth import authenticate
        person, reason = await asyncio.to_thread(authenticate, settings_["ldap"], payload.username.strip(), payload.password)
        if person:
            _failures.pop(key, None)
            try:
                user = _sign_in_directory_user(person, settings_)
            except HTTPException as e:
                audit("login", "denied", username=key, method="ldap", reason=e.detail)
                raise
            _set_session_cookie(response, request, user["id"])
            set_request_user(user["username"])
            audit("login", "success", user=user["username"], method="ldap", role=user["role"])
            return _public_user(user)
        # Not a directory login: fall through to the local admin backup below

    user = A.find_user(payload.username.strip(), "local")
    conn_ok = user and user["is_active"]
    stored = None
    if conn_ok:
        from app.core.database import get_connection
        c = get_connection()
        stored = c.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()["password_hash"]
        c.close()
    if not A.verify_password(payload.password, stored) or not conn_ok:
        failed("unknown user, disabled account or wrong password" if settings_["mode"] == "local" else (reason or "wrong password"))
        if settings_["mode"] == "ldap" and reason and reason != "Wrong username or password.":
            raise HTTPException(status_code=503, detail=reason)  # e.g. the directory server is unreachable
        raise HTTPException(status_code=401, detail="Wrong username or password.")
    if settings_["mode"] != "local" and user["role"] != "admin":
        audit("login", "denied", username=key, method="local", reason="local sign-in is for administrators in this mode")
        raise HTTPException(status_code=403, detail="Local sign-in is for administrators only. Use your company sign-in.")
    _failures.pop(key, None)
    _set_session_cookie(response, request, user["id"])
    set_request_user(user["username"])
    audit("login", "success", user=user["username"], method="local", role=user["role"])
    return _public_user(user)


@router.post("/logout")
def logout(request: Request, response: Response, session: Optional[str] = Cookie(None, alias=A.SESSION_COOKIE)):
    user = A.user_for_session(session)
    A.delete_session(session)
    if user:
        audit("logout", user=user["username"])
    opts = _cookie_options(request)
    response.delete_cookie(A.SESSION_COOKIE, path="/", secure=opts["secure"], httponly=True, samesite=opts["samesite"])
    return {"signed_out": True}


@router.get("/me")
def me(session: Optional[str] = Cookie(None, alias=A.SESSION_COOKIE)):
    user = A.user_for_session(session)
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in.")
    return _public_user(user)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
def change_password(payload: PasswordChange, session: Optional[str] = Cookie(None, alias=A.SESSION_COOKIE)):
    user = A.user_for_session(session)
    if not user or user["auth_source"] != "local":
        raise HTTPException(status_code=400, detail="Only local accounts have a password here.")
    from app.core.database import get_connection
    c = get_connection()
    stored = c.execute("SELECT password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()["password_hash"]
    c.close()
    if not A.verify_password(payload.current_password, stored):
        audit("password_change", "failure", user=user["username"], reason="wrong current password")
        raise HTTPException(status_code=401, detail="The current password is wrong.")
    problem = A.password_problem(payload.new_password, user["username"])
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if A.verify_password(payload.new_password, stored):
        raise HTTPException(status_code=400, detail="Choose a password different from the current one.")
    A.update_user(user["id"], password_hash=A.hash_password(payload.new_password), must_change_password=0)
    # Other sessions of this person end; this one continues
    A.end_other_sessions(user["id"], session)
    # The first-run password file is no longer needed once the admin has their own password
    import os
    if user["username"] == "admin" and os.path.exists(A.initial_password_file()):
        os.remove(A.initial_password_file())
    audit("password_change", user=user["username"], was_temporary=bool(user.get("must_change_password")) or None)
    return {"changed": True}


# ---------- Okta (OpenID Connect) ----------

async def _discover(issuer: str) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(issuer.rstrip("/") + "/.well-known/openid-configuration")
        res.raise_for_status()
        return res.json()


@router.get("/okta/login")
async def okta_login(request: Request):
    s = A.get_auth_settings()
    okta = s["okta"]
    if s["mode"] != "okta" or not okta.get("issuer"):
        raise HTTPException(status_code=400, detail="Okta sign-in is not enabled.")
    try:
        meta = await _discover(okta["issuer"])
    except Exception:
        raise HTTPException(status_code=502, detail="Okta could not be reached from this server.")
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    params = {"client_id": okta["client_id"], "response_type": "code", "scope": okta.get("scopes") or "openid profile email",
              "redirect_uri": okta["redirect_uri"], "state": state, "code_challenge": challenge,
              "code_challenge_method": "S256"}
    response = RedirectResponse(meta["authorization_endpoint"] + "?" + urlencode(params))
    from app.core.secret_box import encrypt
    opts = {**_cookie_options(request), "samesite": "lax", "path": "/api/auth/okta"}  # lax: sent on Okta's redirect back
    response.set_cookie(_OKTA_COOKIE, encrypt(json.dumps({"state": state, "verifier": verifier, "t": time.time()})),
                        max_age=_OKTA_MAX_AGE, **opts)
    return response


@router.get("/okta/callback")
async def okta_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    from app.core.secret_box import PREFIX, decrypt
    raw = request.cookies.get(_OKTA_COOKIE, "")
    try:
        pending = json.loads(decrypt(raw) or "{}") if raw.startswith(PREFIX) else {}
    except ValueError:
        pending = {}
    valid = (pending.get("state") and secrets.compare_digest(pending["state"], state or "")
             and pending.get("t", 0) > time.time() - _OKTA_MAX_AGE)
    if error or not code or not valid:
        return RedirectResponse(_UI + "/?login_error=" + ("okta_" + error if error else "okta_failed"))
    verifier = pending["verifier"]
    s = A.get_auth_settings()
    okta = s["okta"]
    try:
        meta = await _discover(okta["issuer"])
        async with httpx.AsyncClient(timeout=15) as client:
            tok = await client.post(meta["token_endpoint"], data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": okta["redirect_uri"],
                "code_verifier": verifier}, auth=(okta["client_id"], okta["client_secret"]))
            tok.raise_for_status()
            access = tok.json()["access_token"]
            # Claims come straight from Okta's userinfo endpoint over TLS, using the token just issued to us
            info = await client.get(meta["userinfo_endpoint"], headers={"Authorization": f"Bearer {access}"})
            info.raise_for_status()
            claims = info.json()
    except Exception as e:
        logging.getLogger("idp.auth").warning("Okta token or userinfo request failed: %s", type(e).__name__)
        audit("login", "failure", method="okta", reason="token or userinfo request failed")
        return RedirectResponse(_UI + "/?login_error=okta_token")

    username = claims.get("preferred_username") or claims.get("email") or claims.get("sub")
    groups = claims.get(okta.get("groups_claim") or "groups") or []
    if isinstance(groups, str):
        groups = [groups]
    role = A.role_for_groups(groups, s)
    user = A.find_user(username, "okta")
    if user and user["role_locked"]:
        role = user["role"]  # an admin fixed this person's role by hand
    if not role:
        audit("login", "denied", username=username, method="okta", reason="no mapped group")
        return RedirectResponse(_UI + "/?login_error=no_role")
    if user:
        if not user["is_active"]:
            audit("login", "denied", username=username, method="okta", reason="account disabled")
            return RedirectResponse(_UI + "/?login_error=disabled")
        A.update_user(user["id"], role=role, groups_json=json.dumps(groups),
                      display_name=claims.get("name") or user["display_name"], email=claims.get("email") or user["email"])
    else:
        user = A.create_user(username, role, "okta", display_name=claims.get("name") or username,
                             email=claims.get("email") or "", groups=groups)
    response = RedirectResponse(_UI + "/")
    response.delete_cookie(_OKTA_COOKIE, path="/api/auth/okta")
    _set_session_cookie(response, request, user["id"])
    audit("login", "success", user=user["username"], method="okta", role=user["role"])
    return response
