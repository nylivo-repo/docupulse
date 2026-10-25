"""
Users, sign-in sessions, local passwords and the authentication settings (local or Okta,
AD group → role mapping). Everything is stored in the app's own SQLite database.
"""
import logging
import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_connection

ROLES = ["admin", "user"]
ROLE_SCOPES = {
    "admin": ["doc:read", "doc:write", "schema:manage", "admin"],
    "user": ["doc:read", "doc:write"],
}
SESSION_COOKIE = "idp_session"
SESSION_HOURS = settings.SESSION_HOURS
_PBKDF2_ROUNDS = 600_000  # OWASP 2023 for PBKDF2-HMAC-SHA256; older hashes keep their own count

DEFAULT_AUTH_SETTINGS: Dict[str, Any] = {
    "mode": "local",  # "local", "okta" or "ldap"; the local admin login always stays available as a backup
    "okta": {
        "issuer": "",  # e.g. https://yourcompany.okta.com/oauth2/default
        "client_id": "",
        "client_secret": "",
        "redirect_uri": "",  # e.g. http://idp-server:8000/api/auth/okta/callback
        "scopes": "openid profile email groups",
        "groups_claim": "groups",
    },
    "ldap": {},  # Active Directory / LDAP settings, see app.core.ldap_auth.DEFAULT_LDAP_SETTINGS
    "group_roles": [],  # [{"group": "IDP-Admins", "role": "admin"}, ...]
    "default_role": "user",  # role for people in no mapped group; "none" refuses them
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- passwords ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${digest.hex()}"


def password_problem(password: str, username: str = "") -> Optional[str]:
    """Why a new local password is not acceptable, or None."""
    from app.core.config import settings
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        return f"Use at least {settings.PASSWORD_MIN_LENGTH} characters."
    if len(password) > 256:
        return "Use at most 256 characters."
    if username and username.lower() in password.lower():
        return "The password must not contain the username."
    if len(set(password)) < 5:
        return "Use a less repetitive password."
    return None


# Checked when the account does not exist, so a wrong username takes as long as a wrong password
_DUMMY_HASH = None


def verify_password(password: str, stored: Optional[str]) -> bool:
    global _DUMMY_HASH
    if not stored:
        _DUMMY_HASH = _DUMMY_HASH or hash_password(secrets.token_hex(8))
        stored, password = _DUMMY_HASH, password + "\0"  # always fails, same cost
        verify_password(password, stored)
        return False
    try:
        algo, rounds, salt, digest = (stored or "").split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
        return algo == "pbkdf2_sha256" and hmac.compare_digest(calc.hex(), digest)
    except ValueError:
        return False


# ---------- settings ----------

def get_auth_settings() -> Dict[str, Any]:
    conn = get_connection()
    row = conn.execute("""SELECT value_json FROM app_settings WHERE "key" = 'auth'""").fetchone()
    conn.close()
    stored = json.loads(row["value_json"]) if row else {}
    from app.core.ldap_auth import DEFAULT_LDAP_SETTINGS
    merged = json.loads(json.dumps(DEFAULT_AUTH_SETTINGS))
    merged["ldap"] = dict(DEFAULT_LDAP_SETTINGS)
    merged.update({k: v for k, v in stored.items() if k not in ("okta", "ldap")})
    merged["okta"].update(stored.get("okta", {}))
    merged["ldap"].update(stored.get("ldap", {}))
    from app.core.secret_box import decrypt
    merged["okta"]["client_secret"] = decrypt(merged["okta"].get("client_secret", ""))
    merged["ldap"]["bind_password"] = decrypt(merged["ldap"].get("bind_password", ""))
    return merged


def save_auth_settings(value: Dict[str, Any]):
    from app.core.secret_box import encrypt
    value = {**value, "okta": {**value.get("okta", {})}, "ldap": {**value.get("ldap", {})}}
    value["okta"]["client_secret"] = encrypt(value["okta"].get("client_secret", ""))
    value["ldap"]["bind_password"] = encrypt(value["ldap"].get("bind_password", ""))
    # Update-then-insert works the same on SQLite, PostgreSQL and SQL Server ("key" is quoted: reserved in SQL Server)
    conn = get_connection()
    if conn.execute("""SELECT 1 FROM app_settings WHERE "key" = 'auth'""").fetchone():
        conn.execute("""UPDATE app_settings SET value_json = ? WHERE "key" = 'auth'""", (json.dumps(value),))
    else:
        conn.execute("""INSERT INTO app_settings ("key", value_json) VALUES ('auth', ?)""", (json.dumps(value),))
    conn.commit()
    conn.close()


def role_for_groups(groups: List[str], auth: Optional[Dict[str, Any]] = None) -> Optional[str]:
    """Highest role any of the user's groups maps to (admin beats user); else the default role."""
    auth = auth or get_auth_settings()
    lowered = {g.lower() for g in groups}
    mapped = {m["role"] for m in auth.get("group_roles", []) if m.get("group", "").lower() in lowered}
    for role in ROLES:  # ordered highest first
        if role in mapped:
            return role
    default = auth.get("default_role", "user")
    return None if default == "none" else default


# ---------- users ----------

def _user_dict(r) -> Dict[str, Any]:
    return {
        "id": r["id"], "username": r["username"], "display_name": r["display_name"], "email": r["email"],
        "auth_source": r["auth_source"], "role": r["role"], "role_locked": bool(r["role_locked"]),
        "groups": json.loads(r["groups_json"] or "[]"), "is_active": bool(r["is_active"]),
        "created_at": r["created_at"], "last_login": r["last_login"],
        "must_change_password": bool(r["must_change_password"]) if "must_change_password" in r.keys() else False,
    }


def get_user(user_id: str) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    r = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return _user_dict(r) if r else None


def find_user(username: str, auth_source: Optional[str] = None) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    q = "SELECT * FROM users WHERE lower(username) = lower(?)" + (" AND auth_source = ?" if auth_source else "")
    r = conn.execute(q, (username, auth_source) if auth_source else (username,)).fetchone()
    conn.close()
    return _user_dict(r) if r else None


def list_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY created_at").fetchall()
    conn.close()
    return [_user_dict(r) for r in rows]


def create_user(username: str, role: str, auth_source: str = "local", password: Optional[str] = None,
                display_name: str = "", email: str = "", groups: Optional[List[str]] = None,
                role_locked: bool = False) -> Dict[str, Any]:
    user_id = f"usr_{uuid.uuid4().hex[:12]}"
    conn = get_connection()
    conn.execute("""
        INSERT INTO users (id, username, display_name, email, password_hash, auth_source, role, role_locked, groups_json, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
    """, (user_id, username, display_name or username, email, hash_password(password) if password else None,
          auth_source, role, 1 if role_locked else 0, json.dumps(groups or []), _now().isoformat()))
    conn.commit()
    conn.close()
    return get_user(user_id)


def update_user(user_id: str, **changes) -> Optional[Dict[str, Any]]:
    allowed = {"display_name", "email", "role", "role_locked", "is_active", "groups_json", "last_login", "password_hash",
               "must_change_password"}
    sets = {k: v for k, v in changes.items() if k in allowed}
    if sets:
        conn = get_connection()
        conn.execute(f"UPDATE users SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), user_id))
        if sets.get("is_active") == 0:
            conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    return get_user(user_id)


def encrypt_stored_secrets():
    """Re-saves sign-in settings whose secrets were stored before encryption existed."""
    conn = get_connection()
    row = conn.execute("""SELECT value_json FROM app_settings WHERE "key" = 'auth'""").fetchone()
    conn.close()
    if not row:
        return
    raw = json.loads(row["value_json"])
    plain = [v for v in (raw.get("okta", {}).get("client_secret"), raw.get("ldap", {}).get("bind_password"))
             if v and not v.startswith("enc:v1:")]
    if plain:
        save_auth_settings(get_auth_settings())
        logging.getLogger("idp.auth").warning("Encrypted %d stored sign-in secret(s)", len(plain))


def initial_password_file() -> str:
    return os.path.join(settings.STORAGE_DIR, "initial_admin_password.txt")


def ensure_bootstrap_admin():
    """
    The first run on a new database creates the local 'admin' account (the break-glass login) with a
    temporary password that must be changed at the first sign-in. The password comes from
    IDP_ADMIN_PASSWORD, or is generated and written once to storage/initial_admin_password.txt
    (owner-only); the file is deleted when the password is changed. The password is never logged.
    """
    conn = get_connection()
    has_admin = conn.execute("SELECT 1 FROM users WHERE auth_source = 'local' AND role = 'admin'").fetchone()
    conn.close()
    if not has_admin:
        password = os.getenv("IDP_ADMIN_PASSWORD") or secrets.token_urlsafe(12)
        user = create_user("admin", "admin", "local", password, display_name="Local Administrator", role_locked=True)
        update_user(user["id"], must_change_password=1)
        log = logging.getLogger("idp.auth")
        if not os.getenv("IDP_ADMIN_PASSWORD"):
            path = initial_password_file()
            with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
                f.write(f"username: admin\npassword: {password}\n"
                        "This is a temporary password: you will be asked to change it at the first sign-in,\n"
                        "and this file is deleted when you do.\n")
            log.warning("FIRST RUN: created the local administrator 'admin' with a temporary password, saved in %s "
                        "(readable only by the service account). Sign in and set a new password.", path)
        else:
            log.warning("FIRST RUN: created the local administrator 'admin' with the temporary password from "
                        "IDP_ADMIN_PASSWORD. Sign in and set a new password.")

    admin = find_user("admin", "local")
    conn = get_connection()
    conn.execute("UPDATE documents SET owner_id = ? WHERE owner_id IS NULL", (admin["id"],))
    conn.execute("UPDATE api_keys SET owner_id = ? WHERE owner_id IS NULL", (admin["id"],))
    conn.commit()
    conn.close()


# ---------- sessions ----------

def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()  # only the hash is stored
    conn = get_connection()
    conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                 (token_hash, user_id, _now().isoformat(), (_now() + timedelta(hours=SESSION_HOURS)).isoformat()))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now().isoformat(),))
    conn.commit()
    conn.close()
    update_user(user_id, last_login=_now().isoformat())
    return token


def user_for_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    conn = get_connection()
    r = conn.execute("SELECT user_id, expires_at FROM sessions WHERE token_hash = ?",
                     (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
    conn.close()
    if not r or r["expires_at"] < _now().isoformat():
        return None
    user = get_user(r["user_id"])
    return user if user and user["is_active"] else None


def end_other_sessions(user_id: str, keep_token: Optional[str] = None):
    """Signs a person out everywhere else (after a password change or reset)."""
    conn = get_connection()
    if keep_token:
        conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?",
                     (user_id, hashlib.sha256(keep_token.encode()).hexdigest()))
    else:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


def delete_session(token: Optional[str]):
    if token:
        conn = get_connection()
        conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hashlib.sha256(token.encode()).hexdigest(),))
        conn.commit()
        conn.close()
