"""
Logging for operations and audit, written to rotating files in [logging] dir (server.ini):

  app.log    operations: start-up, requests (access log), warnings, errors with stack traces
  audit.log  who did what: sign-ins and failures, sign-outs, admin changes, deletes, moves

Lines are JSON by default (one object per line, ready for Splunk / ELK / Graylog) or plain text.
Every line written while handling a request carries its request_id, which is also sent to the
client in the X-Request-ID header and in error responses, so a user's report can be traced.
Passwords, tokens, API keys and document contents are never logged; a filter masks anything
that looks like a credential in case a library logs one.
"""
import contextvars
import json
import logging
import logging.handlers
import os
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.config import settings

# Per-request context (request id, signed-in user, client address). A dict, so the sign-in check deep
# inside a request can fill in the user and the access log written afterwards still sees it.
request_ctx: contextvars.ContextVar[dict] = contextvars.ContextVar("request_ctx", default={})


def set_request_user(username: str):
    ctx = request_ctx.get()
    if ctx:
        ctx["user"] = username

_SECRET = re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization|cookie|idp_session)(\"?\s*[:=]\s*\"?)([^\s\",;&]+)")


class _Context(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        ctx = request_ctx.get()
        record.request_id = ctx.get("request_id", "-")
        record.user = ctx.get("user", "-")
        record.client_ip = ctx.get("client_ip", "-")
        return True


class _Redact(logging.Filter):
    """Masks credential-looking values, so a stray log call can never leak one."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and _SECRET.search(record.msg):
            record.msg = _SECRET.sub(r"\1\2***", record.msg)
        if record.args:
            try:
                record.msg = _SECRET.sub(r"\1\2***", record.getMessage())
                record.args = ()
            except Exception:
                pass
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "user": getattr(record, "user", "-"),
            "client_ip": getattr(record, "client_ip", "-"),
        }
        extra = getattr(record, "fields", None)
        if extra:
            out.update(extra)
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extra = getattr(record, "fields", None)
        return f"{line} {json.dumps(extra, default=str)}" if extra else line


def _handler(name: str, formatter: logging.Formatter) -> logging.Handler:
    h = logging.handlers.RotatingFileHandler(os.path.join(settings.LOG_DIR, name), maxBytes=settings.LOG_MAX_MB * 1024 * 1024,
                                             backupCount=settings.LOG_BACKUPS, encoding="utf-8")
    h.setFormatter(formatter)
    h.addFilter(_Context())
    h.addFilter(_Redact())
    return h


_configured = False


def setup_logging():
    global _configured
    if _configured:
        return
    _configured = True
    os.makedirs(settings.LOG_DIR, exist_ok=True)
    fmt = _JsonFormatter() if settings.LOG_FORMAT == "json" else _TextFormatter(
        "%(asctime)s %(levelname)s %(name)s [%(request_id)s %(user)s %(client_ip)s] %(message)s")

    root = logging.getLogger()
    root.setLevel(settings.LOG_LEVEL if settings.LOG_LEVEL in logging._nameToLevel else "INFO")
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(_handler("app.log", fmt))
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.addFilter(_Context())
    console.addFilter(_Redact())
    root.addHandler(console)

    audit = logging.getLogger("idp.audit")
    audit.setLevel(logging.INFO)
    audit.propagate = False
    audit.addHandler(_handler("audit.log", _JsonFormatter()))  # always JSON: it is evidence

    # Uvicorn's own access log is replaced by ours (it would log query strings); its errors go to app.log
    logging.getLogger("uvicorn.access").disabled = True
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    # Chatty third-party libraries
    for name in ("pdfminer", "PIL", "httpx", "httpcore", "multipart", "rapidocr", "RapidOCR"):
        logging.getLogger(name).setLevel(logging.WARNING)


def audit(event: str, outcome: str = "success", user: Optional[str] = None, **fields: Any):
    """One line in audit.log: what happened, to what, by whom, from where, and whether it worked."""
    data = {"event": event, "outcome": outcome, **{k: v for k, v in fields.items() if v is not None}}
    if user:
        data["actor"] = user
    logging.getLogger("idp.audit").info(event, extra={"fields": data})
