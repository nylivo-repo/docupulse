-- Upgrade 2: folders in the Document Hub. Run automatically once on an existing database.
IF OBJECT_ID(N'dbo.folders', N'U') IS NULL
CREATE TABLE dbo.folders (
    id NVARCHAR(64) NOT NULL PRIMARY KEY,
    name NVARCHAR(255) NOT NULL,
    parent_id NVARCHAR(64) NULL,
    owner_id NVARCHAR(64) NOT NULL,
    created_at NVARCHAR(40) NOT NULL
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'idx_folders_owner')
CREATE INDEX idx_folders_owner ON dbo.folders(owner_id, parent_id);
GO
IF COL_LENGTH(N'dbo.documents', N'folder_id') IS NULL
ALTER TABLE dbo.documents ADD folder_id NVARCHAR(64) NULL;
GO
