"""
Emergency reset of the local 'admin' password, run on the server itself:

    cd backend && ../venv/bin/python reset_admin.py

Uses the database configured in config/database.ini. Signs out the admin's open sessions.
"""
import getpass
import sys

from app.core.auth import find_user, hash_password, password_problem, update_user
from app.core.database import get_connection, init_db

init_db()
user = find_user("admin", "local")
if not user:
    sys.exit("No local 'admin' account exists. Start the server once and it will be created.")
password = getpass.getpass("New password for admin: ")
problem = password_problem(password, "admin")
if problem:
    sys.exit(f"{problem} Nothing changed.")
if password != getpass.getpass("Repeat it: "):
    sys.exit("The passwords do not match; nothing changed.")
update_user(user["id"], password_hash=hash_password(password), is_active=1, role="admin", must_change_password=0)
conn = get_connection()
conn.execute("DELETE FROM sessions WHERE user_id = ?", (user["id"],))
conn.commit()
conn.close()
print("The admin password has been reset.")
