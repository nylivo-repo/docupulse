-- Upgrade 3: favourite folders (up to 3 per person, shown as tabs in the Document Hub).
ALTER TABLE folders ADD COLUMN IF NOT EXISTS favorite_rank INTEGER;
