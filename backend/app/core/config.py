"""
API server settings: backend/config/server.ini (created from server.example.ini on first start),
with environment variables taking precedence. The database has its own file, database.ini.
"""
import configparser
import os
import shutil
from typing import List

from pydantic import BaseModel

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CONFIG_DIR = os.path.join(_BACKEND_DIR, "config")


def _load_ini() -> configparser.ConfigParser:
    path = os.path.join(_CONFIG_DIR, "server.ini")
    example = os.path.join(_CONFIG_DIR, "server.example.ini")
    if not os.path.exists(path) and os.path.exists(example):
        shutil.copyfile(example, path)
    parser = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    parser.read(path)
    return parser


_INI = _load_ini()


def _get(env: str, section: str, key: str, default: str) -> str:
    value = os.getenv(env)
    if value is None:
        value = _INI.get(section, key, fallback=default)
    return (value or "").strip() or default


def _path(value: str) -> str:
    return value if os.path.isabs(value) else os.path.normpath(os.path.join(_BACKEND_DIR, value))


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


class Settings(BaseModel):
    API_V1_STR: str = "/api/v1"
    VERSION: str = "1.4.0"

    HOST: str = _get("IDP_HOST", "server", "host", "127.0.0.1")
    PORT: int = int(_get("IDP_PORT", "server", "port", "8000"))
    RELOAD: bool = _bool(_get("IDP_RELOAD", "server", "reload", "false"))

    SERVE_FRONTEND: bool = _bool(_get("IDP_SERVE_FRONTEND", "frontend", "serve_frontend", "true"))
    FRONTEND_DIST_DIR: str = _path(_get("IDP_FRONTEND_DIST", "frontend", "dist_dir", "../frontend/dist"))
    FRONTEND_URL: str = _get("IDP_FRONTEND_URL", "frontend", "frontend_url", "").rstrip("/")

    CORS_ORIGINS: List[str] = [o.strip().rstrip("/") for o in
                               _get("IDP_CORS_ORIGINS", "cors", "allowed_origins", "").split(",") if o.strip()]

    SESSION_HOURS: int = int(_get("IDP_SESSION_HOURS", "session", "hours", "12"))
    COOKIE_SAMESITE: str = _get("IDP_COOKIE_SAMESITE", "session", "cookie_samesite", "lax").lower()
    COOKIE_SECURE: str = _get("IDP_COOKIE_SECURE", "session", "cookie_secure", "auto").lower()

    STORAGE_DIR: str = _path(_get("IDP_STORAGE_DIR", "storage", "dir", "storage"))
    SAMPLE_DOCS_DIR: str = os.path.join(_BACKEND_DIR, "sample_docs")
    MAX_UPLOAD_MB: int = int(_get("IDP_MAX_UPLOAD_MB", "storage", "max_upload_mb", "25"))

    MAX_PAGES: int = int(_get("IDP_MAX_PAGES", "storage", "max_pages", "500"))

    # Logging: app.log (operations, errors) and audit.log (sign-ins, admin and data changes), rotated
    LOG_DIR: str = _path(_get("IDP_LOG_DIR", "logging", "dir", "storage/logs"))
    LOG_LEVEL: str = _get("IDP_LOG_LEVEL", "logging", "level", "INFO").upper()
    LOG_FORMAT: str = _get("IDP_LOG_FORMAT", "logging", "format", "json").lower()
    LOG_MAX_MB: int = int(_get("IDP_LOG_MAX_MB", "logging", "max_mb", "20"))
    LOG_BACKUPS: int = int(_get("IDP_LOG_BACKUPS", "logging", "backups", "10"))
    LOG_ACCESS: bool = _bool(_get("IDP_LOG_ACCESS", "logging", "access_log", "true"))

    # Security
    # Reverse proxies whose X-Forwarded-For / -Proto are trusted (comma-separated IPs, or * behind a private network)
    TRUSTED_PROXIES: str = _get("IDP_TRUSTED_PROXIES", "security", "trusted_proxies", "127.0.0.1")
    LOGIN_MAX_FAILURES: int = int(_get("IDP_LOGIN_MAX_FAILURES", "security", "login_max_failures", "5"))
    LOGIN_LOCKOUT_MINUTES: int = int(_get("IDP_LOGIN_LOCKOUT_MINUTES", "security", "login_lockout_minutes", "15"))
    LOGIN_MAX_FAILURES_PER_IP: int = int(_get("IDP_LOGIN_MAX_FAILURES_PER_IP", "security", "login_max_failures_per_ip", "30"))
    PASSWORD_MIN_LENGTH: int = int(_get("IDP_PASSWORD_MIN_LENGTH", "security", "password_min_length", "12"))
    # Key that encrypts stored secrets (Okta client secret, directory bind password). A file is created on first start.
    SECRET_KEY: str = _get("IDP_SECRET_KEY", "security", "secret_key", "")
    SECRET_KEY_FILE: str = _path(_get("IDP_SECRET_KEY_FILE", "security", "secret_key_file", "storage/secret.key"))
    # Content-Security-Policy for the web UI pages this server sends (empty = the built-in strict policy)
    CSP: str = _get("IDP_CSP", "security", "content_security_policy", "")

    # Feature flags ([features] in server.ini)
    # Instant demo: the sample-document buttons, the /documents/sample API and demo documents on an empty database
    DEMO_PRESETS: bool = _bool(_get("IDP_DEMO_PRESETS", "features", "demo_presets", "false"))

    # Documents whose overall confidence is below this go to human review
    REVIEW_CONFIDENCE_THRESHOLD: float = float(_get("IDP_REVIEW_THRESHOLD", "extraction", "review_threshold", "0.85"))

    # Optional local LLM (OpenAI-compatible server on your own network). Empty = disabled.
    LOCAL_LLM_URL: str = _get("LOCAL_LLM_URL", "local_llm", "url", "")
    LOCAL_LLM_MODEL: str = _get("LOCAL_LLM_MODEL", "local_llm", "model", "llama3.1:8b")
    LOCAL_LLM_TIMEOUT: float = float(_get("LOCAL_LLM_TIMEOUT", "local_llm", "timeout", "60"))
    LOCAL_LLM_MAX_CHARS: int = int(_get("LOCAL_LLM_MAX_CHARS", "local_llm", "max_chars", "12000"))


settings = Settings()

os.makedirs(settings.STORAGE_DIR, exist_ok=True)
os.makedirs(settings.SAMPLE_DOCS_DIR, exist_ok=True)
os.makedirs(os.path.join(settings.STORAGE_DIR, "uploads"), exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True)
