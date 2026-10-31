-- IDP database schema: Microsoft SQL Server (2016 or later)
-- Run automatically on the first server start when the tables do not exist yet,
-- or give it to your DBA (sqlcmd / SSMS). Batches are separated by GO lines.
-- Create the database and login first, e.g.:
--   CREATE DATABASE idp;  CREATE LOGIN idp_app WITH PASSWORD = '...';
--   USE idp; CREATE USER idp_app FOR LOGIN idp_app; ALTER ROLE db_owner ADD MEMBER idp_app;

SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.documents', N'U') IS NULL
CREATE TABLE dbo.documents (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    title NVARCHAR(500) NOT NULL,
    doc_type NVARCHAR(100) NOT NULL,
    schema_id NVARCHAR(64) NULL,
    status NVARCHAR(32) NOT NULL,
    file_name NVARCHAR(500) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    file_path NVARCHAR(MAX) NOT NULL,
    page_count INT DEFAULT 1,
    overall_confidence FLOAT DEFAULT 0.0,
    needs_review INT DEFAULT 0,
    created_at NVARCHAR(40) NOT NULL,
    processed_at NVARCHAR(40) NULL,
    fields_json NVARCHAR(MAX) NOT NULL,
    raw_text NVARCHAR(MAX) NULL,
    metadata_json NVARCHAR(MAX) DEFAULT '{}',
    owner_id NVARCHAR(64) NULL,
    folder_id NVARCHAR(64) NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_documents_owner')
CREATE INDEX idx_documents_owner ON dbo.documents(owner_id);
GO

IF OBJECT_ID(N'dbo.audit_logs', N'U') IS NULL
CREATE TABLE dbo.audit_logs (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    document_id NVARCHAR(64) NOT NULL,
    "timestamp" NVARCHAR(40) NOT NULL,
    "user" NVARCHAR(255) NOT NULL,
    action NVARCHAR(255) NOT NULL,
    details_json NVARCHAR(MAX) NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_audit_document')
CREATE INDEX idx_audit_document ON dbo.audit_logs(document_id);
GO

IF OBJECT_ID(N'dbo.custom_schemas', N'U') IS NULL
CREATE TABLE dbo.custom_schemas (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    name NVARCHAR(255) NOT NULL,
    document_type_code NVARCHAR(200) NOT NULL,
    description NVARCHAR(MAX) NULL,
    fields_json NVARCHAR(MAX) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    updated_at NVARCHAR(40) NOT NULL,
    is_active INT DEFAULT 1,
    base_pipeline NVARCHAR(32) NULL,
    fingerprint NVARCHAR(MAX) NULL,
    api_endpoint NVARCHAR(64) NULL,  -- lookup endpoint name (GET /api/v1/lookup/<name>), unique among active templates
    api_enabled INT DEFAULT 0
);
GO

IF OBJECT_ID(N'dbo.api_keys', N'U') IS NULL
CREATE TABLE dbo.api_keys (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    name NVARCHAR(255) NOT NULL,
    key_hash NVARCHAR(128) NOT NULL,
    key_prefix NVARCHAR(32) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    last_used NVARCHAR(40) NULL,
    scopes_json NVARCHAR(MAX) NOT NULL,
    quota_limit INT DEFAULT 10000,
    quota_used INT DEFAULT 0,
    is_active INT DEFAULT 1,
    owner_id NVARCHAR(64) NULL
);
GO

IF OBJECT_ID(N'dbo.webhooks', N'U') IS NULL
CREATE TABLE dbo.webhooks (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    url NVARCHAR(MAX) NOT NULL,
    events_json NVARCHAR(MAX) NOT NULL,
    secret NVARCHAR(255) NOT NULL,
    is_active INT DEFAULT 1,
    created_at NVARCHAR(40) NOT NULL,
    successful_deliveries INT DEFAULT 0,
    failed_deliveries INT DEFAULT 0
);
GO

IF OBJECT_ID(N'dbo.webhook_logs', N'U') IS NULL
CREATE TABLE dbo.webhook_logs (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    webhook_id NVARCHAR(64) NOT NULL,
    event NVARCHAR(100) NOT NULL,
    status_code INT NOT NULL,
    success INT NOT NULL,
    payload_json NVARCHAR(MAX) NOT NULL,
    response_body NVARCHAR(MAX) NULL,
    "timestamp" NVARCHAR(40) NOT NULL,
    duration_ms INT NOT NULL
);
GO

IF OBJECT_ID(N'dbo.users', N'U') IS NULL
CREATE TABLE dbo.users (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    username NVARCHAR(255) NOT NULL,
    display_name NVARCHAR(255) NULL,
    email NVARCHAR(255) NULL,
    password_hash NVARCHAR(255) NULL,
    auth_source NVARCHAR(16) NOT NULL,
    role NVARCHAR(16) NOT NULL,
    role_locked INT DEFAULT 0,
    groups_json NVARCHAR(MAX) DEFAULT '[]',
    is_active INT DEFAULT 1,
    created_at NVARCHAR(40) NOT NULL,
    last_login NVARCHAR(40) NULL,
    must_change_password INT DEFAULT 0,  -- 1: temporary password, must be changed at next sign-in
    CONSTRAINT uq_users_username_source UNIQUE (username, auth_source)
);
GO

IF OBJECT_ID(N'dbo.sessions', N'U') IS NULL
CREATE TABLE dbo.sessions (
    token_hash NVARCHAR(128) NOT NULL PRIMARY KEY,
    user_id NVARCHAR(64) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    expires_at NVARCHAR(40) NOT NULL
);
GO

IF OBJECT_ID(N'dbo.app_settings', N'U') IS NULL
CREATE TABLE dbo.app_settings (
    [key] NVARCHAR(100) NOT NULL PRIMARY KEY,
    value_json NVARCHAR(MAX) NOT NULL
);
GO

-- Folders (Document Hub): each person's own tree; parent_id NULL = top level
IF OBJECT_ID(N'dbo.folders', N'U') IS NULL
CREATE TABLE dbo.folders (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    name NVARCHAR(255) NOT NULL,
    parent_id NVARCHAR(64) NULL,
    owner_id NVARCHAR(64) NOT NULL,
    created_at NVARCHAR(40) NOT NULL,
    favorite_rank INT NULL  -- 1..3 when pinned as a favourite, else NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_folders_owner')
CREATE INDEX idx_folders_owner ON dbo.folders(owner_id, parent_id);
GO

IF OBJECT_ID(N'dbo.schema_version', N'U') IS NULL
CREATE TABLE dbo.schema_version (
    version INT NOT NULL,
    applied_at NVARCHAR(40) NOT NULL
);
GO
