"""
Sign-in against Active Directory / LDAP, entirely inside the network.

Flow: bind with the service account (or anonymously), find the user with the search filter,
then bind as that user with the password they typed. Their groups come from memberOf (and, for AD,
optionally nested groups), and map to a role through the same group-role table Okta uses.
"""
import ssl
from typing import Any, Dict, List, Optional, Tuple

from ldap3 import NONE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from ldap3.utils.dn import parse_dn

DEFAULT_LDAP_SETTINGS: Dict[str, Any] = {
    "server_url": "",  # ldaps://dc01.corp.local:636 or ldap://dc01.corp.local:389
    "use_starttls": False,  # upgrade ldap:// to TLS
    "verify_tls": True,
    "ca_cert_path": "",  # your internal CA certificate, if the server's certificate is not publicly trusted
    "bind_dn": "",  # service account, e.g. CN=svc-idp,OU=Service Accounts,DC=corp,DC=local (empty: anonymous search)
    "bind_password": "",
    "user_base_dn": "",  # e.g. DC=corp,DC=local
    "user_filter": "(&(objectClass=user)(sAMAccountName={username}))",
    "group_attribute": "memberOf",
    "nested_groups": True,  # AD only: include groups the user belongs to through other groups
    "timeout": 8,
}


def _connect(cfg: Dict[str, Any], user: Optional[str], password: Optional[str]) -> Connection:
    """Opens and binds a connection. Separate so tests can swap in a mock directory."""
    tls = None
    url = cfg["server_url"].strip()
    if url.startswith("ldaps://") or cfg.get("use_starttls"):
        tls = Tls(validate=ssl.CERT_REQUIRED if cfg.get("verify_tls", True) else ssl.CERT_NONE,
                  ca_certs_file=cfg.get("ca_cert_path") or None)
    server = Server(url, use_ssl=url.startswith("ldaps://"), tls=tls, get_info=NONE,
                    connect_timeout=int(cfg.get("timeout") or 8))
    conn = Connection(server, user=user or None, password=password or None,
                      receive_timeout=int(cfg.get("timeout") or 8), raise_exceptions=True)
    conn.open()
    if cfg.get("use_starttls") and not url.startswith("ldaps://"):
        conn.start_tls()
    conn.bind()
    return conn


def _cn(dn: str) -> str:
    """'CN=IDP-Admins,OU=Groups,DC=corp,DC=local' -> 'IDP-Admins'."""
    try:
        for attr, value, _ in parse_dn(dn):
            if attr.lower() == "cn":
                return value.replace("\\,", ",")
    except Exception:
        pass
    return dn


def authenticate(cfg: Dict[str, Any], username: str, password: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """
    Returns (person, "") on success, where person has username, display_name, email, groups and dn;
    or (None, reason) when the directory refuses or cannot be reached. Reasons never include the password.
    """
    if not password:
        return None, "Enter your password."  # an empty password would be an anonymous bind, which always "succeeds"
    if not cfg.get("server_url") or not cfg.get("user_base_dn"):
        return None, "Directory sign-in is not configured."
    try:
        service = _connect(cfg, cfg.get("bind_dn"), cfg.get("bind_password"))
    except LDAPException as e:
        return None, f"The directory could not be reached or refused the service account ({type(e).__name__})."
    try:
        flt = (cfg.get("user_filter") or DEFAULT_LDAP_SETTINGS["user_filter"]).replace("{username}", escape_filter_chars(username))
        group_attr = cfg.get("group_attribute") or "memberOf"
        service.search(cfg["user_base_dn"], flt, SUBTREE,
                       attributes=[group_attr, "displayName", "cn", "mail", "userPrincipalName", "sAMAccountName", "uid"])
        if len(service.entries) != 1:
            return None, "Wrong username or password."
        entry = service.entries[0]
        dn = entry.entry_dn
        attrs = entry.entry_attributes_as_dict

        def first(name):
            v = attrs.get(name) or []
            return str(v[0]) if v else ""

        group_dns: List[str] = [str(g) for g in attrs.get(group_attr, [])]
        if cfg.get("nested_groups"):
            try:
                service.search(cfg["user_base_dn"], f"(member:1.2.840.113556.1.4.1941:={escape_filter_chars(dn)})",
                               SUBTREE, attributes=["cn"])
                group_dns += [e.entry_dn for e in service.entries]
            except LDAPException:
                pass  # not Active Directory: direct memberships only
    except LDAPException as e:
        return None, f"Directory search failed ({type(e).__name__})."
    finally:
        try:
            service.unbind()
        except Exception:
            pass

    try:
        user_conn = _connect(cfg, dn, password)  # proves the password
        user_conn.unbind()
    except LDAPException:
        return None, "Wrong username or password."

    groups = sorted({_cn(g) for g in group_dns})
    return {
        "username": first("sAMAccountName") or first("uid") or username,
        "display_name": first("displayName") or first("cn") or username,
        "email": first("mail") or first("userPrincipalName"),
        "groups": groups,
        "dn": dn,
    }, ""


def test_connection(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Checks the server is reachable and the service account (or anonymous) bind works."""
    try:
        conn = _connect(cfg, cfg.get("bind_dn"), cfg.get("bind_password"))
        conn.search(cfg["user_base_dn"], "(objectClass=*)", SUBTREE, attributes=[], size_limit=1) if cfg.get("user_base_dn") else None
        conn.unbind()
        return {"ok": True}
    except LDAPException as e:
        return {"ok": False, "error": f"{type(e).__name__}: could not connect or bind. Check the server address, port, TLS and service account."}
