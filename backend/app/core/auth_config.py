"""
Sign-in method from a file at server start: backend/config/auth.ini (created from auth.example.ini).

mode = local | ldap | okta : the file wins. On every start it sets the sign-in method and its Okta /
    LDAP settings (and the group roles, if [roles] lists any) in the database, and Admin Settings shows
    them read-only. Secrets come from IDP_OKTA_CLIENT_SECRET / IDP_LDAP_BIND_PASSWORD (or the file).
mode = ui : the file is ignored and administrators choose in Admin Settings.

A missing file behaves as mode = local.
"""
import configparser
import logging
import os
import shutil
from typing import Any, Dict, Optional

from app.core.config import _CONFIG_DIR

log = logging.getLogger("idp.auth")
MODES = ("local", "ldap", "okta")
PATH = os.path.join(_CONFIG_DIR, "auth.ini")
_BOOL = {"ldap": ("use_starttls", "verify_tls", "nested_groups")}
_INT = {"ldap": ("timeout",)}


def _read() -> configparser.ConfigParser:
    example = os.path.join(_CONFIG_DIR, "auth.example.ini")
    if not os.path.exists(PATH) and os.path.exists(example):
        shutil.copyfile(example, PATH)
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    parser.optionxform = str  # group names keep their case
    parser.read(PATH, encoding="utf-8")
    return parser


def _value(parser, section: str, key: str) -> str:
    env = os.getenv(f"IDP_{section.upper()}_{key.upper()}")
    return (env if env is not None else parser.get(section, key, fallback="")).strip()


def file_settings() -> Optional[Dict[str, Any]]:
    """The sign-in settings the file manages, or None when mode = ui (Admin Settings decides)."""
    parser = _read()
    mode = (os.getenv("IDP_AUTH_MODE") or parser.get("signin", "mode", fallback="local") or "local").strip().lower()
    if mode == "ui":
        return None
    if mode not in MODES:
        log.error("auth.ini: unknown mode '%s'; using local sign-in", mode)
        mode = "local"
    out: Dict[str, Any] = {"mode": mode, "okta": {}, "ldap": {}}
    for section in ("okta", "ldap"):
        keys = set(parser.options(section)) if parser.has_section(section) else set()
        keys |= {"client_secret"} if section == "okta" else {"bind_password"}
        for key in keys:
            raw = _value(parser, section, key)
            if key in _BOOL.get(section, ()):
                out[section][key] = raw.lower() in ("1", "true", "yes", "on")
            elif key in _INT.get(section, ()):
                out[section][key] = int(raw or 8)
            else:
                out[section][key] = raw
    if parser.has_section("roles"):
        roles = [{"group": g.strip(), "role": r.strip().lower()} for g, r in parser.items("roles")
                 if g != "default_role" and r.strip()]
        if roles:
            out["group_roles"] = roles
        default = parser.get("roles", "default_role", fallback="").strip().lower()
        if default:
            out["default_role"] = default
    return out


def apply_file_settings():
    """At start: writes the file's sign-in settings into the database (the file wins)."""
    from app.core import auth as A
    managed = file_settings()
    if managed is None:
        log.info("Sign-in method: set in Admin Settings (auth.ini mode = ui)")
        return
    current = A.get_auth_settings()
    new = {**current, "mode": managed["mode"],
           "okta": {**current["okta"], **managed["okta"]}, "ldap": {**current["ldap"], **managed["ldap"]}}
    # An empty secret in the file / environment keeps the stored one
    if not managed["okta"].get("client_secret"):
        new["okta"]["client_secret"] = current["okta"].get("client_secret", "")
    if not managed["ldap"].get("bind_password"):
        new["ldap"]["bind_password"] = current["ldap"].get("bind_password", "")
    for key in ("group_roles", "default_role"):
        if key in managed:
            new[key] = managed[key]
    problems = []
    if new["mode"] == "okta":
        problems = [k for k in ("issuer", "client_id", "client_secret", "redirect_uri") if not new["okta"].get(k)]
    elif new["mode"] == "ldap":
        problems = [k for k in ("server_url", "user_base_dn") if not new["ldap"].get(k)]
        if "{username}" not in new["ldap"].get("user_filter", ""):
            problems.append("user_filter must contain {username}")
    A.save_auth_settings(new)
    if problems:
        log.error("auth.ini: sign-in mode '%s' is missing %s; only local administrators can sign in until it is fixed",
                  new["mode"], ", ".join(problems))
    else:
        log.info("Sign-in method from auth.ini: %s", new["mode"])


def managed_sections() -> Dict[str, bool]:
    """Which parts of Admin Settings → Users & Sign-in are controlled by auth.ini (shown read-only)."""
    managed = file_settings()
    if managed is None:
        return {"method": False, "group_roles": False, "default_role": False}
    return {"method": True, "group_roles": "group_roles" in managed, "default_role": "default_role" in managed}
