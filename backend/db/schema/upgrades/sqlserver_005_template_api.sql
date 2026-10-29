-- Upgrade 5: a template can publish a lookup endpoint (GET /api/v1/lookup/<api_endpoint>).
IF COL_LENGTH(N'dbo.custom_schemas', N'api_endpoint') IS NULL
ALTER TABLE dbo.custom_schemas ADD api_endpoint NVARCHAR(64) NULL;
GO
IF COL_LENGTH(N'dbo.custom_schemas', N'api_enabled') IS NULL
ALTER TABLE dbo.custom_schemas ADD api_enabled INT DEFAULT 0;
GO
