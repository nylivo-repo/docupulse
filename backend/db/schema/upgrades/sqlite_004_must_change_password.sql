-- Upgrade 4: temporary passwords that must be changed at the next sign-in.
ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0;
