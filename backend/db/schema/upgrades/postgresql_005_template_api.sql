-- Upgrade 5: a template can publish a lookup endpoint (GET /api/v1/lookup/<api_endpoint>).
ALTER TABLE custom_schemas ADD COLUMN IF NOT EXISTS api_endpoint VARCHAR(64);
ALTER TABLE custom_schemas ADD COLUMN IF NOT EXISTS api_enabled INTEGER DEFAULT 0;
