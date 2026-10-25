-- Upgrade 4: temporary passwords that must be changed at the next sign-in.
IF COL_LENGTH(N'dbo.users', N'must_change_password') IS NULL
ALTER TABLE dbo.users ADD must_change_password INT DEFAULT 0;
GO
