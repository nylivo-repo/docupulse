-- Upgrade 2: folders in the Document Hub. Run automatically once on an existing database.
CREATE TABLE IF NOT EXISTS folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    parent_id TEXT,
    owner_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_folders_owner ON folders(owner_id, parent_id);
ALTER TABLE documents ADD COLUMN folder_id TEXT;
