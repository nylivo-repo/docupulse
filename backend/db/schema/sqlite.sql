-- DocuPulse IDP database schema: SQLite
-- Run automatically on the first server start when the tables do not exist yet.
-- Statements are separated by semicolons at line ends.

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    schema_id TEXT,
    status TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    page_count INTEGER DEFAULT 1,
    overall_confidence REAL DEFAULT 0.0,
    needs_review INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    processed_at TEXT,
    fields_json TEXT NOT NULL,
    raw_text TEXT,
    metadata_json TEXT DEFAULT '{}',
    owner_id TEXT,
    folder_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    "timestamp" TEXT NOT NULL,
    "user" TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_document ON audit_logs(document_id);

CREATE TABLE IF NOT EXISTS custom_schemas (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    document_type_code TEXT NOT NULL,
    description TEXT,
    fields_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    base_pipeline TEXT,
    fingerprint TEXT,
    api_endpoint TEXT,  -- lookup endpoint name (GET /api/v1/lookup/<name>), unique among active templates
    api_enabled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_keys (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL,
    key_prefix TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used TEXT,
    scopes_json TEXT NOT NULL,
    quota_limit INTEGER DEFAULT 10000,
    quota_used INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    owner_id TEXT
);

CREATE TABLE IF NOT EXISTS webhooks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    events_json TEXT NOT NULL,
    secret TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    successful_deliveries INTEGER DEFAULT 0,
    failed_deliveries INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id TEXT PRIMARY KEY,
    webhook_id TEXT NOT NULL,
    event TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    success INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    response_body TEXT,
    "timestamp" TEXT NOT NULL,
    duration_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    display_name TEXT,
    email TEXT,
    password_hash TEXT,
    auth_source TEXT NOT NULL,
    role TEXT NOT NULL,
    role_locked INTEGER DEFAULT 0,
    groups_json TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    last_login TEXT,
    must_change_password INTEGER DEFAULT 0,  -- 1: temporary password, must be changed at next sign-in
    UNIQUE (username, auth_source)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL
);

-- Folders (Document Hub): each person's own tree; parent_id NULL = top level
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    favorite_rank INTEGER  -- 1..3 when pinned as a favourite, else NULL
);
CREATE INDEX IF NOT EXISTS idx_folders_owner ON folders(owner_id, parent_id);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL
);
