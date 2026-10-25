-- Upgrade 4: temporary passwords that must be changed at the next sign-in.
ALTER TABLE users ADD COLUMN IF NOT EXISTS must_change_password INTEGER DEFAULT 0;
