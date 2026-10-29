"""
Lookup endpoints published by templates.

A template with its API switched on answers GET /api/v1/lookup/<endpoint>?documentId=… or ?<searchKey>=…
(and POST with a JSON body, which sensitive search keys such as an SSN must use, so they stay out of URLs and
proxy logs). Rules, also in /docs section 6.1:
- an API key needs the scope lookup:<endpoint> or lookup:*; a signed-in session needs doc:read
- only the caller's own documents (the key acts as its creator), only approved ones, only this template's
- matching is exact, ignoring case, spaces and punctuation ("123-45-6789" = "123456789"); several keys are ANDed
- sensitive fields come back masked (*****6789) unless the key also has pii:read
- every lookup is written to audit.log (searched values as names only, never the values), and each returned
  document gets an "API lookup" entry in its own audit trail
"""
import json
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from fastapi import APIRouter, Body, HTTPException, Request, Security
from app.core.database import get_connection
from app.core.logging_config import audit
from app.core.security import verify_api_key
from app.services.document_service import _audit

router = APIRouter(prefix="/lookup", tags=["Lookup endpoints (from templates)"])

RESERVED_PARAMS = {"documentid": "documentId", "limit": "limit", "offset": "offset"}
DEFAULT_LIMIT, MAX_LIMIT = 20, 100
MAX_VALUE_LEN = 200


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def camel(name: str) -> str:
    """Field name as a query parameter: last_name → lastName."""
    head, *rest = name.split("_")
    return head + "".join(p[:1].upper() + p[1:] for p in rest)


def _param_key(name: str) -> str:
    return name.replace("_", "").lower()


def normalize(value: Any) -> str:
    """Exact match ignoring case, spaces and punctuation: 'O'Brien' = 'obrien', '123-45-6789' = '123456789'."""
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", str(value))).casefold()


def mask(value: Any) -> Any:
    if value in (None, ""):
        return value
    text = str(value)
    tail = re.sub(r"[\W_]+", "", text)[-4:] if len(re.sub(r"[\W_]+", "", text)) > 6 else ""
    return "*****" + tail


def _templates(endpoint: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    rows = conn.execute("SELECT id, name, document_type_code, description, fields_json, api_endpoint FROM custom_schemas "
                        "WHERE is_active = 1 AND api_enabled = 1 AND api_endpoint IS NOT NULL").fetchall()
    conn.close()
    out = []
    for r in rows:
        if endpoint and r["api_endpoint"].lower() != endpoint.lower():
            continue
        out.append({"id": r["id"], "name": r["name"], "code": r["document_type_code"], "description": r["description"] or "",
                    "endpoint": r["api_endpoint"], "fields": json.loads(r["fields_json"])})
    return out


def _may_call(auth: dict, endpoint: str) -> bool:
    if auth.get("key_id"):
        return f"lookup:{endpoint}" in auth["scopes"] or "lookup:*" in auth["scopes"]
    return "doc:read" in auth["scopes"]  # a signed-in person, reading their own documents


def describe(t: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "endpoint": t["endpoint"],
        "path": f"/api/v1/lookup/{t['endpoint']}",
        "template": t["name"],
        "template_id": t["id"],
        "document_type_code": t["code"],
        "scope": f"lookup:{t['endpoint']}",
        "search_keys": [{"param": "documentId", "field": None, "label": "Document ID", "sensitive": False}] +
                       [{"param": camel(f["name"]), "field": f["name"], "label": f.get("label") or f["name"],
                         "sensitive": bool(f.get("sensitive"))} for f in t["fields"] if f.get("api_search")],
        "fields": [{"name": f["name"], "label": f.get("label") or f["name"], "sensitive": bool(f.get("sensitive"))}
                   for f in t["fields"]],
    }


@router.get("")
def list_lookup_endpoints(auth: dict = Security(verify_api_key)):
    """
    Lists the lookup endpoints that templates publish: path, required scope, search keys (query parameter names)
    and returned fields. `allowed` says whether the caller may use each one.
    """
    if not auth["scopes"]:
        raise HTTPException(status_code=403, detail="Missing permission: 'doc:read'")
    return [{**describe(t), "allowed": _may_call(auth, t["endpoint"])} for t in _templates()]


def _parse(t: Dict[str, Any], params: List[Tuple[str, Any]], via_get: bool) -> Tuple[Optional[str], Dict[str, str], int, int]:
    """Splits the request into documentId, search keys (field name → normalised value), limit and offset."""
    keys = {_param_key(f["name"]): f for f in t["fields"] if f.get("api_search")}
    seen, doc_id, search, limit, offset = set(), None, {}, DEFAULT_LIMIT, 0
    for raw_name, raw_value in params:
        k = _param_key(raw_name)
        if k in seen:
            raise HTTPException(status_code=400, detail=f"'{raw_name}' is given more than once.")
        seen.add(k)
        value = "" if raw_value is None else str(raw_value).strip()
        if k in ("limit", "offset"):
            try:
                n = int(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"'{raw_name}' must be a whole number.")
            if k == "limit":
                if not 1 <= n <= MAX_LIMIT:
                    raise HTTPException(status_code=400, detail=f"limit must be between 1 and {MAX_LIMIT}.")
                limit = n
            else:
                if n < 0:
                    raise HTTPException(status_code=400, detail="offset cannot be negative.")
                offset = n
            continue
        if len(value) > MAX_VALUE_LEN:
            raise HTTPException(status_code=400, detail=f"'{raw_name}' is too long.")
        if k == "documentid":
            if not value:
                raise HTTPException(status_code=400, detail="documentId is empty.")
            doc_id = value
            continue
        f = keys.get(k)
        if not f:
            allowed = ", ".join(["documentId"] + [camel(x["name"]) for x in keys.values()])
            raise HTTPException(status_code=400, detail=f"'{raw_name}' is not a search key of {t['endpoint']}. Use: {allowed}.")
        if f.get("sensitive") and via_get:
            raise HTTPException(status_code=400, detail=f"'{camel(f['name'])}' is sensitive: send it in a POST body, not in the URL.")
        if not normalize(value):
            raise HTTPException(status_code=400, detail=f"'{raw_name}' is empty.")
        search[f["name"]] = normalize(value)
    if not doc_id and not search:
        allowed = ", ".join(["documentId"] + [camel(x["name"]) for x in keys.values()])
        raise HTTPException(status_code=400, detail=f"Give documentId or at least one search key: {allowed}.")
    return doc_id, search, limit, offset


def _lookup(endpoint: str, params: List[Tuple[str, Any]], auth: dict, via_get: bool) -> Dict[str, Any]:
    found = _templates(endpoint)
    names = sorted({n for n, _ in params})
    if not found:
        audit("lookup.query", outcome="not_found", user=auth["username"], endpoint=endpoint, key=auth.get("key_id"))
        raise HTTPException(status_code=404, detail="No lookup endpoint by that name.")
    t = found[0]
    if not _may_call(auth, t["endpoint"]):
        audit("lookup.query", outcome="denied", user=auth["username"], endpoint=t["endpoint"], key=auth.get("key_id"))
        raise HTTPException(status_code=403, detail=f"Missing permission: 'lookup:{t['endpoint']}'")
    try:
        doc_id, search, limit, offset = _parse(t, params, via_get)
    except HTTPException:
        audit("lookup.query", outcome="invalid", user=auth["username"], endpoint=t["endpoint"], key=auth.get("key_id"), params=names)
        raise

    # Only the caller's own approved documents read with this template
    sql = ("SELECT id, title, status, created_at, processed_at, fields_json FROM documents "
           "WHERE owner_id = ? AND status = 'approved' AND (schema_id = ? OR doc_type = ?)")
    args: List[Any] = [auth["user_id"], t["id"], t["code"]]
    if doc_id:
        sql += " AND id = ?"
        args.append(doc_id)
    conn = get_connection()
    rows = conn.execute(sql + " ORDER BY created_at DESC", args).fetchall()
    matches = []
    for r in rows:
        fields = json.loads(r["fields_json"] or "{}")
        if all(normalize((fields.get(name) or {}).get("value") or "") == want for name, want in search.items()):
            matches.append((r, fields))
    page = matches[offset:offset + limit]

    unmask = "pii:read" in auth["scopes"]
    results = []
    for r, fields in page:
        values, masked = {}, []
        for f in t["fields"]:
            v = (fields.get(f["name"]) or {}).get("value")
            if f.get("sensitive") and not unmask and v not in (None, ""):
                v = mask(v)
                masked.append(f["name"])
            values[f["name"]] = v
        results.append({"documentId": r["id"], "title": r["title"], "status": r["status"],
                        "createdAt": r["created_at"], "processedAt": r["processed_at"],
                        "fields": values, "maskedFields": masked})

    # Each returned document records that it was read through the API, by whom and on which keys
    actor = f'{auth["username"]} (API key {auth["key_name"]})' if auth.get("key_id") else auth["username"]
    cursor = conn.cursor()
    for r, _ in page:
        _audit(cursor, r["id"], actor, "API lookup", {"endpoint": t["endpoint"], "matched_on": names,
                                                      "unmasked": unmask})
    if auth.get("key_id"):
        conn.execute("UPDATE api_keys SET quota_used = quota_used + 1, last_used = ? WHERE id = ?", (_now(), auth["key_id"]))
    conn.commit()
    conn.close()
    audit("lookup.query", user=auth["username"], endpoint=t["endpoint"], key=auth.get("key_id"), params=names,
          total=len(matches), returned=[r["id"] for r, _ in page], unmasked=unmask)
    return {"endpoint": t["endpoint"], "template": t["name"], "total": len(matches), "limit": limit, "offset": offset,
            "results": results}


@router.get("/{endpoint}")
def lookup_get(endpoint: str, request: Request, auth: dict = Security(verify_api_key)):
    """
    Looks up approved documents of the template that publishes this endpoint, by `documentId` and/or its search
    keys (e.g. `?lastName=Doe&firstName=Jane`), and returns their fields as JSON. Matching is exact, ignoring
    case, spaces and punctuation; several keys must all match. `limit` (1–100, default 20) and `offset` page the
    results. Needs scope `lookup:<endpoint>` or `lookup:*` on an API key. Sensitive search keys must use POST.
    Sensitive fields are masked unless the key has `pii:read`. Each call is audited.
    """
    return _lookup(endpoint, list(request.query_params.multi_items()), auth, via_get=True)


@router.post("/{endpoint}")
def lookup_post(endpoint: str, body: Dict[str, Any] = Body(..., examples=[{"ssn": "123-45-6789", "limit": 20}]),
                auth: dict = Security(verify_api_key)):
    """
    The same lookup with the search keys in a JSON body, e.g. `{"ssn": "123-45-6789"}` or
    `{"documentId": "doc_…"}`. Required for sensitive search keys such as an SSN, so the value never appears
    in a URL, browser history or proxy log.
    """
    for k, v in body.items():
        if isinstance(v, (dict, list)):
            raise HTTPException(status_code=400, detail=f"'{k}' must be a single value.")
    return _lookup(endpoint, list(body.items()), auth, via_get=False)


def openapi_paths() -> Dict[str, Any]:
    """One documented path per published endpoint, merged into /openapi.json so the API docs list them."""
    paths: Dict[str, Any] = {}
    for t in _templates():
        d = describe(t)
        props = {f["name"]: {"type": "string", "description": f["label"] + (" (sensitive: masked without pii:read)" if f["sensitive"] else "")}
                 for f in d["fields"]}
        result = {"type": "object", "properties": {
            "endpoint": {"type": "string"}, "template": {"type": "string"}, "total": {"type": "integer"},
            "limit": {"type": "integer"}, "offset": {"type": "integer"},
            "results": {"type": "array", "items": {"type": "object", "properties": {
                "documentId": {"type": "string"}, "title": {"type": "string"}, "status": {"type": "string"},
                "createdAt": {"type": "string"}, "processedAt": {"type": "string"},
                "fields": {"type": "object", "properties": props},
                "maskedFields": {"type": "array", "items": {"type": "string"}}}}}}}
        plain = [k for k in d["search_keys"] if not k["sensitive"]]
        params = [{"name": k["param"], "in": "query", "required": False, "schema": {"type": "string"},
                   "description": k["label"]} for k in plain]
        params += [{"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": DEFAULT_LIMIT, "maximum": MAX_LIMIT}},
                   {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer", "default": 0}}]
        keys = ", ".join(k["param"] + (" (sensitive, POST only)" if k["sensitive"] else "") for k in d["search_keys"])
        example = "&".join(f"{k['param']}=…" for k in plain[1:3]) or "documentId=doc_…"
        desc = (f"Published by the template '{t['name']}' ({t['code']}). Returns the template's fields for your approved "
                f"documents that match. Search keys: {keys}. Example: GET {d['path']}?{example}. "
                f"Needs scope {d['scope']} (or lookup:*). Exact match ignoring case, spaces and punctuation; keys are ANDed.")
        ok = {"200": {"description": "Matching documents", "content": {"application/json": {"schema": result}}}}
        tag = ["Lookup endpoints (from templates)"]
        body_props = {k["param"]: {"type": "string"} for k in d["search_keys"]}
        body_props.update({"limit": {"type": "integer"}, "offset": {"type": "integer"}})
        paths[d["path"]] = {
            "get": {"tags": tag, "summary": f"{t['endpoint']}: look up {t['name']} documents", "description": desc,
                    "operationId": f"lookup_{t['endpoint']}_get", "parameters": params, "responses": ok},
            "post": {"tags": tag, "summary": f"{t['endpoint']} (search keys in the body)",
                     "description": desc + " POST keeps values (required for sensitive keys) out of URLs.",
                     "operationId": f"lookup_{t['endpoint']}_post",
                     "requestBody": {"required": True, "content": {"application/json": {"schema": {"type": "object", "properties": body_props}}}},
                     "responses": ok},
        }
    return paths
