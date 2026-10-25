#!/bin/sh
# Prepares the config and storage volumes, then runs the API as an unprivileged user (PUID:PGID,
# the owner of the NAS folder). The server creates server.ini, database.ini and auth.ini from the
# .example.ini templates on its first start; after that they are only ever edited by you.
set -e
CFG=/app/backend/config
STORE=/app/backend/storage
mkdir -p "$CFG" "$STORE"
cp -f /app/config-defaults/*.example.ini "$CFG/"
find "$CFG" "$STORE" \( ! -user "$PUID" -o ! -group "$PGID" \) -exec chown "$PUID:$PGID" {} +
exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
