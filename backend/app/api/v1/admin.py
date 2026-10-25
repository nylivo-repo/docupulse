"""Admin settings: sign-in method, Okta configuration, AD group → role mapping and user accounts."""
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import auth as A
from app.core.auth_config import PATH as AUTH_INI, managed_sections
from app.core.logging_config import audit
from app.core.security import check_scope

router = APIRouter(prefix="/admin", tags=["Admin Settings"])
SECRET_MASK = "••••••••"


class OktaSettings(BaseModel):
    issuer: str = ""
    client_id: str = ""
    client_secret: str = ""  # sent back masked; leave masked or empty to keep the stored one
    redirect_uri: str = ""
    scopes: str = "openid profile email groups"
    groups_claim: str = "groups"


class LdapSettings(BaseModel):
    server_url: str = ""
    use_starttls: bool = False
    verify_tls: bool = True
    ca_cert_path: str = ""
    bind_dn: str = ""
    bind_password: str = ""  # sent back masked; leave masked or empty to keep the stored one
    user_base_dn: str = ""
    user_filter: str = "(&(objectClass=user)(sAMAccountName={username}))"
    group_attribute: str = "memberOf"
    nested_groups: bool = True
    timeout: int = 8


class GroupRole(BaseModel):
    group: str
    role: str


class AuthSettings(BaseModel):
    mode: str = "local"
    okta: OktaSettings = OktaSettings()
    ldap: LdapSettings = LdapSettings()
    group_roles: List[GroupRole] = []
    default_role: str = "user"


def _masked(s: dict) -> dict:
    out = {**s, "okta": {**s["okta"]}, "ldap": {**s["ldap"]}}
    out["okta"]["client_secret"] = SECRET_MASK if s["okta"].get("client_secret") else ""
    out["ldap"]["bind_password"] = SECRET_MASK if s["ldap"].get("bind_password") else ""
    return out


def _keep_secrets(new: dict, current: dict) -> dict:
    """A masked or empty secret in the form means 'keep the stored one'."""
    if new["okta"]["client_secret"] in ("", SECRET_MASK):
        new["okta"]["client_secret"] = current["okta"].get("client_secret", "")
    if new["ldap"]["bind_password"] in ("", SECRET_MASK):
        new["ldap"]["bind_password"] = current["ldap"].get("bind_password", "")
    return new


@router.get("/settings/auth")
def get_auth_settings(auth: dict = Depends(check_scope("admin"))):
    """
    Current sign-in settings (secrets masked). `managed` says which parts are set by
    config/auth.ini on the server and therefore read-only here.
    """
    return {**_masked(A.get_auth_settings()), "managed": managed_sections(), "managed_file": AUTH_INI}


@router.put("/settings/auth")
def save_auth_settings(payload: AuthSettings, auth: dict = Depends(check_scope("admin"))):
    if payload.mode not in ("local", "okta", "ldap"):
        raise HTTPException(status_code=400, detail="mode must be 'local', 'okta' or 'ldap'.")
    if payload.default_role not in A.ROLES + ["none"]:
        raise HTTPException(status_code=400, detail="default_role must be admin, user or none.")
    for g in payload.group_roles:
        if g.role not in A.ROLES or not g.group.strip():
            raise HTTPException(status_code=400, detail="Each group needs a name and a role of admin or user.")
    current = A.get_auth_settings()
    new = _keep_secrets(payload.model_dump(), current)
    # Parts set by config/auth.ini cannot be changed here (the file is applied again at every start)
    managed = managed_sections()
    if managed["method"]:
        changed_keys = [f"{sec}.{k}" for sec in ("okta", "ldap") for k, v in new[sec].items() if current[sec].get(k) != v]
        if new["mode"] != current["mode"] or changed_keys:
            raise HTTPException(status_code=409, detail="The sign-in method is set in config/auth.ini on the server. "
                                "Change it there and restart the service.")
    for key in ("group_roles", "default_role"):
        if managed[key]:
            new[key] = current[key]
    if new["mode"] == "ldap":
        missing = [k for k in ("server_url", "user_base_dn", "user_filter") if not new["ldap"].get(k)]
        if missing:
            raise HTTPException(status_code=400, detail=f"To switch to AD/LDAP, fill in: {', '.join(missing)}.")
        if "{username}" not in new["ldap"]["user_filter"]:
            raise HTTPException(status_code=400, detail="The user search filter must contain {username}.")
    new["group_roles"] = [{"group": g["group"].strip(), "role": g["role"]} for g in new["group_roles"]]
    if new["mode"] == "okta":
        o = new["okta"]
        missing = [k for k in ("issuer", "client_id", "client_secret", "redirect_uri") if not o.get(k)]
        if missing:
            raise HTTPException(status_code=400, detail=f"To switch to Okta, fill in: {', '.join(missing)}.")
    A.save_auth_settings(new)
    changed = sorted(k for k in ("mode", "okta", "ldap", "group_roles", "default_role") if new.get(k) != current.get(k))
    secrets_changed = [n for n, a, b in (("okta client secret", new["okta"]["client_secret"], current["okta"].get("client_secret")),
                                         ("directory bind password", new["ldap"]["bind_password"], current["ldap"].get("bind_password")))
                       if a != b]
    audit("admin.auth_settings_changed", user=auth["username"], mode=new["mode"], sections=changed,
          secrets_changed=secrets_changed or None)
    return {**_masked(A.get_auth_settings()), "managed": managed, "managed_file": AUTH_INI}


@router.post("/settings/auth/test-okta")
async def test_okta(payload: OktaSettings, auth: dict = Depends(check_scope("admin"))):
    """Checks this server can reach the Okta issuer and read its OpenID configuration."""
    if not payload.issuer:
        raise HTTPException(status_code=400, detail="Enter the issuer URL first.")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            res = await client.get(payload.issuer.rstrip("/") + "/.well-known/openid-configuration")
            res.raise_for_status()
            meta = res.json()
        return {"ok": True, "authorization_endpoint": meta.get("authorization_endpoint"),
                "scopes_supported": meta.get("scopes_supported", [])}
    except Exception as e:
        return {"ok": False, "error": f"Could not reach Okta from this server ({type(e).__name__})."}


class LdapTest(BaseModel):
    ldap: LdapSettings
    username: str = ""  # optional: also try signing this person in and show their groups and role
    password: str = ""


@router.post("/settings/auth/test-ldap")
async def test_ldap(payload: LdapTest, auth: dict = Depends(check_scope("admin"))):
    """Checks the directory connection and service account, and optionally a real user's sign-in."""
    import asyncio
    from app.core.ldap_auth import authenticate, test_connection
    current = A.get_auth_settings()
    cfg = _keep_secrets({"okta": {"client_secret": ""}, "ldap": payload.ldap.model_dump()}, current)["ldap"]
    if not cfg["server_url"]:
        raise HTTPException(status_code=400, detail="Enter the server address first.")
    result = await asyncio.to_thread(test_connection, cfg)
    if result["ok"] and payload.username:
        person, reason = await asyncio.to_thread(authenticate, cfg, payload.username, payload.password)
        if person:
            result["user"] = {"username": person["username"], "display_name": person["display_name"],
                              "groups": person["groups"], "role": A.role_for_groups(person["groups"], current) or "refused"}
        else:
            result.update({"ok": False, "error": reason})
    return result


class NewUser(BaseModel):
    username: str
    password: str
    role: str = "user"
    display_name: str = ""
    email: str = ""


class UserChange(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None
    role_locked: Optional[bool] = None
    password: Optional[str] = None


@router.get("/users")
def list_users(auth: dict = Depends(check_scope("admin"))):
    return A.list_users()


@router.post("/users", status_code=201)
def create_local_user(payload: NewUser, auth: dict = Depends(check_scope("admin"))):
    if payload.role not in A.ROLES:
        raise HTTPException(status_code=400, detail="role must be admin or user.")
    problem = A.password_problem(payload.password, payload.username.strip())
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if A.find_user(payload.username.strip(), "local"):
        raise HTTPException(status_code=400, detail="A local user with that name already exists.")
    user = A.create_user(payload.username.strip(), payload.role, "local", payload.password,
                         payload.display_name, payload.email, role_locked=True)
    # The admin chose this password, so the person sets their own at the first sign-in
    user = A.update_user(user["id"], must_change_password=1)
    audit("admin.user_created", user=auth["username"], target=user["username"], role=user["role"])
    return user


@router.patch("/users/{user_id}")
def change_user(user_id: str, payload: UserChange, auth: dict = Depends(check_scope("admin"))):
    user = A.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    changes = {}
    if payload.role is not None:
        if payload.role not in A.ROLES:
            raise HTTPException(status_code=400, detail="role must be admin or user.")
        changes["role"] = payload.role
        changes["role_locked"] = 1  # set by hand: group mapping no longer overrides it
    if payload.role_locked is not None:
        changes["role_locked"] = 1 if payload.role_locked else 0
    if payload.is_active is not None:
        changes["is_active"] = 1 if payload.is_active else 0
    if payload.password:
        if user["auth_source"] != "local":
            raise HTTPException(status_code=400, detail="Okta users sign in with Okta and have no password here.")
        problem = A.password_problem(payload.password, user["username"])
        if problem:
            raise HTTPException(status_code=400, detail=problem)
        changes["password_hash"] = A.hash_password(payload.password)
        changes["must_change_password"] = 1  # a reset password is temporary
    # Never leave the app without an active local admin (the break-glass login)
    if user["auth_source"] == "local" and user["role"] == "admin" and \
            (changes.get("role") == "user" or changes.get("is_active") == 0):
        others = [u for u in A.list_users() if u["auth_source"] == "local" and u["role"] == "admin"
                  and u["is_active"] and u["id"] != user_id]
        if not others:
            raise HTTPException(status_code=400, detail="This is the last local admin; it is the backup login and must stay.")
    updated = A.update_user(user_id, **changes)
    if "password_hash" in changes:
        A.end_other_sessions(user_id)  # a reset password signs the person out everywhere
    audit("admin.user_changed", user=auth["username"], target=user["username"],
          changes=sorted("password reset" if k == "password_hash" else f"{k}={v}" for k, v in changes.items()))
    return updated
