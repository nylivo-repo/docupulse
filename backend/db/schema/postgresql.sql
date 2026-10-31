-- IDP database schema: PostgreSQL (11 or later)
-- Run automatically on the first server start when the tables do not exist yet,
-- or give it to your DBA to run by hand. Create the database and login first, e.g.:
--   CREATE DATABASE docupulse;  CREATE USER idp_app WITH PASSWORD '...';
--   GRANT ALL ON DATABASE docupulse TO idp_app;   (then run this file as idp_app)

CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(64) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    doc_type VARCHAR(100) NOT NULL,
    schema_id VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    file_name VARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_path TEXT NOT NULL,
    page_count INTEGER DEFAULT 1,
    overall_confidence DOUBLE PRECISION DEFAULT 0.0,
    needs_review INTEGER DEFAULT 0,
    created_at VARCHAR(40) NOT NULL,
    processed_at VARCHAR(40),
    fields_json TEXT NOT NULL,
    raw_text TEXT,
    metadata_json TEXT DEFAULT '{}',
    owner_id VARCHAR(64),
    folder_id VARCHAR(64)
);
CREATE INDEX IF NOT EXISTS idx_documents_owner ON documents(owner_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL,
    "timestamp" VARCHAR(40) NOT NULL,
    "user" VARCHAR(255) NOT NULL,
    action VARCHAR(255) NOT NULL,
    details_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_document ON audit_logs(document_id);

CREATE TABLE IF NOT EXISTS custom_schemas (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    document_type_code VARCHAR(200) NOT NULL,
    description TEXT,
    fields_json TEXT NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    updated_at VARCHAR(40) NOT NULL,
    is_active INTEGER DEFAULT 1,
    base_pipeline VARCHAR(32),
    fingerprint TEXT,
    api_endpoint VARCHAR(64),  -- lookup endpoint name (GET /api/v1/lookup/<name>), unique among active templates
    api_enabled INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS api_keys (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    key_hash VARCHAR(128) NOT NULL,
    key_prefix VARCHAR(32) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    last_used VARCHAR(40),
    scopes_json TEXT NOT NULL,
    quota_limit INTEGER DEFAULT 10000,
    quota_used INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    owner_id VARCHAR(64)
);

CREATE TABLE IF NOT EXISTS webhooks (
    id VARCHAR(64) PRIMARY KEY,
    url TEXT NOT NULL,
    events_json TEXT NOT NULL,
    secret VARCHAR(255) NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at VARCHAR(40) NOT NULL,
    successful_deliveries INTEGER DEFAULT 0,
    failed_deliveries INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS webhook_logs (
    id VARCHAR(64) PRIMARY KEY,
    webhook_id VARCHAR(64) NOT NULL,
    event VARCHAR(100) NOT NULL,
    status_code INTEGER NOT NULL,
    success INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    response_body TEXT,
    "timestamp" VARCHAR(40) NOT NULL,
    duration_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    email VARCHAR(255),
    password_hash VARCHAR(255),
    auth_source VARCHAR(16) NOT NULL,
    role VARCHAR(16) NOT NULL,
    role_locked INTEGER DEFAULT 0,
    groups_json TEXT DEFAULT '[]',
    is_active INTEGER DEFAULT 1,
    created_at VARCHAR(40) NOT NULL,
    last_login VARCHAR(40),
    must_change_password INTEGER DEFAULT 0,  -- 1: temporary password, must be changed at next sign-in
    UNIQUE (username, auth_source)
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    expires_at VARCHAR(40) NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(100) PRIMARY KEY,
    value_json TEXT NOT NULL
);

-- Folders (Document Hub): each person's own tree; parent_id NULL = top level
CREATE TABLE IF NOT EXISTS folders (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    parent_id VARCHAR(64),
    owner_id VARCHAR(64) NOT NULL,
    created_at VARCHAR(40) NOT NULL,
    favorite_rank INTEGER  -- 1..3 when pinned as a favourite, else NULL
);
CREATE INDEX IF NOT EXISTS idx_folders_owner ON folders(owner_id, parent_id);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at VARCHAR(40) NOT NULL
);
