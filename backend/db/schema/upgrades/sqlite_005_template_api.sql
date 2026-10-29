-- Upgrade 5: a template can publish a lookup endpoint (GET /api/v1/lookup/<api_endpoint>).
ALTER TABLE custom_schemas ADD COLUMN api_endpoint TEXT;
ALTER TABLE custom_schemas ADD COLUMN api_enabled INTEGER DEFAULT 0;
