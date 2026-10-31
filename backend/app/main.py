import copy
import logging
import os
from contextlib import asynccontextmanager
import shutil
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.auth_config import apply_file_settings
from app.core import middleware as hardening
from app.core.database import init_db, get_connection, DIALECT
from app.api.v1.documents import router as documents_router
from app.api.v1.schemas import router as schemas_router
from app.api.v1.apikeys import router as apikeys_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.analytics import router as analytics_router
from app.api.v1.admin import router as admin_router
from app.api.v1.folders import router as folders_router
from app.api.v1.lookup import router as lookup_router, openapi_paths as lookup_openapi_paths
from app.api.auth_routes import router as auth_router
from app.core.auth import encrypt_stored_secrets, ensure_bootstrap_admin, find_user, user_for_session, SESSION_COOKIE
from app.engine.sample_generator import create_all_samples
from app.engine.ocr_extractor import LocalOCR
from app.engine.local_llm import LocalLLM
from app.services.document_service import DocumentService

setup_logging()
log = logging.getLogger("idp")


@asynccontextmanager
async def lifespan(_app):
    await on_startup()
    yield
    log.info("IDP stopping")


app = FastAPI(
    lifespan=lifespan,
    title="IDP Intelligent Document Processing API",
    description="""
# IDP API

Offline intelligent document processing: text-layer and local OCR extraction, rule-based pipelines,
user-defined templates, human-in-the-loop review and webhooks. Makes no internet calls.

* **Any document** (`doc_type=auto` or `generic`): detects the type, applies a matching template, or extracts every labelled value.
* **Templates**: define the fields to extract (labels, aliases, types, regex, page regions), or save one from a reviewed document.
* **Contracts, Passports (ICAO 9303 MRZ with all check digits), Invoices (math reconciliation)**: built-in pipelines.
* **Lookup endpoints**: a template can publish `GET/POST /api/v1/lookup/<name>` (e.g. getPassportDetails) that finds approved documents by `documentId` or the template's search keys and returns their fields. API keys need scope `lookup:<name>` (or `lookup:*`); sensitive fields are masked unless the key has `pii:read`.
* **Folders**: each user's own folder tree (`/folders`), `folder_id` on upload, `POST /documents/move`.
* **Errors**: JSON `{"detail", "request_id"}`; every response carries `X-Request-ID`. Browser (cookie) requests that change data must come from an allowed origin; API keys are unaffected.
* **Optional local LLM**: set `LOCAL_LLM_URL` to an OpenAI-compatible server on your network to fill fields rules miss.
    """,
    version=settings.VERSION,
    docs_url=None,  # the stock Swagger page loads from a CDN; /docs below is served locally
    redoc_url=None,
    openapi_url=None,  # served below, to administrators only
)

# A separately deployed UI calls this API from its own origin with sign-in cookies, so only the
# origins listed in config/server.ini [cors] are allowed (credentials cannot be combined with "*")
if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
        expose_headers=["Content-Disposition"],
    )

hardening.install(app)

app.include_router(documents_router, prefix=settings.API_V1_STR)
app.include_router(schemas_router, prefix=settings.API_V1_STR)
app.include_router(apikeys_router, prefix=settings.API_V1_STR)
app.include_router(webhooks_router, prefix=settings.API_V1_STR)
app.include_router(analytics_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(folders_router, prefix=settings.API_V1_STR)
app.include_router(lookup_router, prefix=settings.API_V1_STR)
app.include_router(auth_router)


@app.get("/api/health", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "service": "IDP API",
        "version": settings.VERSION,
        "engine": "Text layer + local OCR + rule-based pipelines",
        "ocr_engine": LocalOCR.engine_name(),
        "local_llm": settings.LOCAL_LLM_URL if LocalLLM.enabled() else None,
        "internet_required": False,
        "database": DIALECT,
        "serves_frontend": settings.SERVE_FRONTEND,
        "features": {"demo_presets": settings.DEMO_PRESETS},
    }


# Architecture, design, database, deployment and operations guide, with the live API list (offline, inline SVG)
_DOCS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "docs.html")


def _require_admin_session(request: Request):
    user = user_for_session(request.cookies.get(SESSION_COOKIE))
    if not user or user["role"] != "admin":
        raise HTTPException(status_code=403, detail="API documentation is for administrators. Sign in as an admin.")


@app.get("/docs", include_in_schema=False)
def api_docs(request: Request):
    _require_admin_session(request)
    return FileResponse(_DOCS_FILE, media_type="text/html", headers={"Cache-Control": "no-cache"})


@app.get("/openapi.json", include_in_schema=False)
def openapi_spec(request: Request):
    _require_admin_session(request)
    # Lookup endpoints come and go with templates, so their paths are added on every request
    spec = copy.deepcopy(app.openapi())
    spec["paths"].update(lookup_openapi_paths())
    return JSONResponse(spec)


async def on_startup():
    log.info("IDP %s starting", settings.VERSION)
    init_db()
    apply_file_settings()  # sign-in method from config/auth.ini (local unless changed)
    ensure_bootstrap_admin()
    encrypt_stored_secrets()
    if not settings.DEMO_PRESETS:
        return  # [features] demo_presets is off: no sample files, no demo documents
    samples = create_all_samples()

    conn = get_connection()
    count = conn.execute("SELECT COUNT(*) as cnt FROM documents").fetchone()["cnt"]
    conn.close()
    if count:
        return

    log.info("Seeding demo documents")
    preset_items = [
        ("doc_sample_contract_init", "Master Services Agreement", "contracts", samples["contract"]),
        ("doc_sample_passport_init", "US Passport KYC Verification", "identity", samples["passport"]),
        ("doc_sample_invoice_init", "CloudScale Networks Invoice", "invoices", samples["invoice"]),
    ]
    for d_id, title, d_type, s_path in preset_items:
        fname = os.path.basename(s_path)
        dest = os.path.join(settings.STORAGE_DIR, "uploads", f"{d_id}_{fname}")
        shutil.copyfile(s_path, dest)
        conn = get_connection()
        conn.execute("""
            INSERT INTO documents (id, title, doc_type, schema_id, status, file_name, file_size_bytes, file_path, page_count, overall_confidence, needs_review, created_at, fields_json, raw_text, metadata_json, owner_id)
            VALUES (?, ?, ?, NULL, 'queued', ?, ?, ?, 1, 0.0, 0, ?, '{}', '', '{}', ?)
        """, (d_id, title, d_type, fname, os.path.getsize(dest), dest, datetime.now(timezone.utc).isoformat(),
              find_user("admin", "local")["id"]))
        conn.commit()
        conn.close()
        await DocumentService.process_document_pipeline(d_id, dest, d_type)
    log.info("Demo documents seeded")


# Serve the built frontend from this same server, so one process and one port cover the whole intranet install
if settings.SERVE_FRONTEND and os.path.isdir(settings.FRONTEND_DIST_DIR):
    _NO_CACHE = {"config.js", "ngsw-worker.js", "ngsw.json", "safety-worker.js", "manifest.webmanifest"}
    assets_dir = os.path.join(settings.FRONTEND_DIST_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = os.path.realpath(os.path.join(settings.FRONTEND_DIST_DIR, full_path))
        if full_path and candidate.startswith(os.path.realpath(settings.FRONTEND_DIST_DIR)) and os.path.isfile(candidate):
            # config.js holds editable settings, and the service worker files decide when an installed app
            # updates: never cached, so an edit or a new build takes effect on reload
            no_cache = full_path in _NO_CACHE or full_path.startswith("branding/")  # replaceable logo and icons
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"} if no_cache else None)
        # Never cache the page itself, so browsers pick up a new build at once (assets are content-hashed)
        return FileResponse(os.path.join(settings.FRONTEND_DIST_DIR, "index.html"), headers={"Cache-Control": "no-cache"})
