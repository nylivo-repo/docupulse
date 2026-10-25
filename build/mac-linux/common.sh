#!/usr/bin/env bash
# Shared paths and helpers for the Mac / Linux scripts. Not run directly.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND="$ROOT/backend"
VENV="$ROOT/venv"
PY="$VENV/bin/python"
PID_FILE="$BACKEND/storage/server.pid"
LOG_DIR="$BACKEND/storage/logs"
LOG_FILE="$LOG_DIR/server.log"

# Host and port as the server will use them (config/server.ini, overridden by environment variables)
server_address() {
  (cd "$BACKEND" && "$PY" -c "from app.core.config import settings; h = settings.HOST; print(('127.0.0.1' if h in ('0.0.0.0', '::') else h) + ':' + str(settings.PORT))")
}

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

health() {
  "$PY" - "$1" <<'EOF'
import sys, urllib.request
try:
    with urllib.request.urlopen(f"http://{sys.argv[1]}/api/health", timeout=3) as r:
        sys.exit(0 if r.status == 200 else 1)
except Exception:
    sys.exit(1)
EOF
}

# The web UI (Angular) builds with Node.js 22 or 24 and newer even (LTS) releases only
node_ok() {
  command -v npm >/dev/null 2>&1 || return 1
  local major
  major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null)" || return 1
  [[ "$major" -ge 22 && $((major % 2)) -eq 0 ]]
}
