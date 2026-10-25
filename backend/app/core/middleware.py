"""
HTTP hardening applied to every request:

- request id: taken from a well-formed X-Request-ID (e.g. set by nginx) or generated; returned in the
  X-Request-ID response header and attached to every log line written for the request
- access log: method, path (never the query string), status, duration, user, client address
- security headers: no MIME sniffing, no framing, no referrer leakage, HSTS over HTTPS, and a strict
  Content-Security-Policy for the pages this server sends
- cross-site request check: a state-changing request authenticated by the sign-in cookie must come
  from this server's own pages or an allowed UI origin ([cors]), whatever the cookie's SameSite setting
- request size limit: bodies larger than the upload limit are refused before they are read
- errors: unexpected exceptions are logged with a stack trace and answered with a generic message
  and the request id; validation errors never echo the submitted values (they may be passwords)
"""
import logging
import re
import time
import uuid
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.config import settings
from app.core.logging_config import audit, request_ctx

log = logging.getLogger("idp.http")
access = logging.getLogger("idp.access")

_RID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# The web UI uses Angular (component styles are inline <style> tags) and loads everything from this server
_UI_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
           "font-src 'self' data:; connect-src 'self'; worker-src 'self'; manifest-src 'self'; object-src 'none'; "
           "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
# The technical documentation page (/docs) is one self-contained file with inline script and styles
_DOCS_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
             "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")


def _origin_allowed(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        ref = request.headers.get("referer")
        if not ref:
            return True  # not a browser form/fetch from another site (e.g. curl, scripts); SameSite still applies
        p = urlsplit(ref)
        origin = f"{p.scheme}://{p.netloc}"
    origin = origin.rstrip("/")
    if origin in settings.CORS_ORIGINS:
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    return urlsplit(origin).netloc.lower() == host.lower()


def install(app: FastAPI):
    max_body = (settings.MAX_UPLOAD_MB + 1) * 1024 * 1024

    @app.middleware("http")
    async def hardening(request: Request, call_next):
        rid = request.headers.get("x-request-id", "")
        rid = rid if _RID.match(rid) else uuid.uuid4().hex[:16]
        client = request.client.host if request.client else "-"
        token = request_ctx.set({"request_id": rid, "user": "-", "client_ip": client})
        start = time.perf_counter()
        status = 500
        try:
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > max_body:
                response = JSONResponse({"detail": f"Request is larger than {settings.MAX_UPLOAD_MB} MB.", "request_id": rid}, 413)
            elif (request.method in _UNSAFE and request.cookies.get("idp_session")
                  and not request.headers.get("x-api-key") and not request.headers.get("authorization")
                  and not _origin_allowed(request)):
                log.warning("Blocked cross-site %s %s from origin %s", request.method, request.url.path,
                            request.headers.get("origin") or request.headers.get("referer"))
                response = JSONResponse({"detail": "Cross-site request refused.", "request_id": rid}, 403)
            else:
                response = await call_next(request)
            status = response.status_code
        except Exception:
            log.exception("Unhandled error on %s %s", request.method, request.url.path)
            response = JSONResponse({"detail": "Something went wrong on the server. Quote this reference to your administrator.",
                                     "request_id": rid}, 500)
        finally:
            # Every change made through the API is an audit event: who, what (method + path), result.
            # Sign-ins and admin settings write their own, more detailed events.
            path = request.url.path
            if request.method in _UNSAFE and path.startswith("/api/v1/") and not path.endswith("/webhooks/echo"):
                ctx = request_ctx.get()
                audit("api_change", "success" if status < 400 else "failure", user=ctx.get("user"),
                      method=request.method, path=path, status=status)
            if settings.LOG_ACCESS:
                ms = round((time.perf_counter() - start) * 1000, 1)
                access.info("%s %s %s", request.method, request.url.path, status,
                            extra={"fields": {"method": request.method, "path": request.url.path, "status": status, "ms": ms}})
        _security_headers(request, response, rid)
        request_ctx.reset(token)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 500:
            log.error("HTTP %s on %s %s: %s", exc.status_code, request.method, request.url.path, exc.detail)
        body = {"detail": exc.detail, "request_id": request_ctx.get().get("request_id")}
        return JSONResponse(body, exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Field and problem only: the submitted values are not echoed back (they may be passwords)
        errors = [{"field": ".".join(str(p) for p in e.get("loc", []) if p != "body"), "problem": e.get("msg")}
                  for e in exc.errors()]
        return JSONResponse({"detail": "Some fields are missing or invalid.", "errors": errors,
                             "request_id": request_ctx.get().get("request_id")}, 422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse({"detail": "Something went wrong on the server. Quote this reference to your administrator.",
                             "request_id": request_ctx.get().get("request_id")}, 500)


def _security_headers(request: Request, response, rid: str):
    h = response.headers
    h["X-Request-ID"] = rid
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "same-origin")
    h.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=(), usb=()")
    h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.scheme == "https":
        h.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    path = request.url.path
    if path.startswith("/api/"):
        h.setdefault("Cache-Control", "no-store")  # documents and personal data are never cached
        h.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    elif path == "/docs":
        h.setdefault("Content-Security-Policy", _DOCS_CSP)
    else:
        h.setdefault("Content-Security-Policy", settings.CSP or _UI_CSP)
