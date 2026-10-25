-- Upgrade 3: favourite folders (up to 3 per person, shown as tabs in the Document Hub).
IF COL_LENGTH(N'dbo.folders', N'favorite_rank') IS NULL
ALTER TABLE dbo.folders ADD favorite_rank INT NULL;
GO
