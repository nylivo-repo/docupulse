-- Upgrade 2: folders in the Document Hub. Run automatically once on an existing database.
CREATE TABLE IF NOT EXISTS folders (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    parent_id VARCHAR(64),
    owner_id VARCHAR(64) NOT NULL,
    created_at VARCHAR(40) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_folders_owner ON folders(owner_id, parent_id);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS folder_id VARCHAR(64);
