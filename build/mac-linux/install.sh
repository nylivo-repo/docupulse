#!/usr/bin/env bash
# Installs DocuPulse IDP on Mac or Linux: Python environment, packages, and the web UI build.
#   build/mac-linux/install.sh            uses build/wheels/ if present (offline), else the internet
# Needs Python 3.11+ (3.12 recommended; set PYTHON=python3.12). Building the UI needs Node.js 22 or 24 (an even, LTS release; Angular does not support odd ones),
# unless frontend/dist is already there.
source "$(dirname "$0")/common.sh"

PYTHON_BIN="${PYTHON:-$(command -v python3.12 || command -v python3.11 || echo python3)}"
"$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || { echo "Python 3.11 or newer is required, 3.12 recommended (set PYTHON=/path/to/python3.12). 3.9 and 3.10 no longer get security fixes."; exit 1; }

if [[ ! -x "$PY" ]]; then
  echo "Creating the Python environment in $VENV"
  "$PYTHON_BIN" -m venv "$VENV"
fi

WHEELS="$ROOT/build/wheels"
PIP_SOURCE=(--disable-pip-version-check)
if [[ -d "$WHEELS" ]]; then
  echo "Installing packages offline from $WHEELS"
  PIP_SOURCE+=(--no-index --find-links "$WHEELS")
fi
"$PY" -m pip install "${PIP_SOURCE[@]}" -r "$BACKEND/requirements.txt"

# Servers have no display libraries: use the headless OpenCV build (same module, no libGL needed)
if [[ "$(uname -s)" == "Linux" ]]; then
  "$PY" -m pip uninstall -y opencv-python >/dev/null 2>&1 || true
  "$PY" -m pip install "${PIP_SOURCE[@]}" opencv-python-headless
fi

if [[ -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "Web UI already built (frontend/dist)."
elif node_ok; then
  echo "Building the web UI"
  (cd "$ROOT/frontend" && npm ci && npm run build)
elif command -v node >/dev/null 2>&1; then
  echo "Note: Node.js $(node -v) cannot build the UI; it needs version 22 or 24. Install one of those, or build"
  echo "      the UI on another machine (build/mac-linux/make-package.sh) and copy frontend/dist here."
else
  echo "Note: frontend/dist is missing and Node.js is not installed. Build the UI on another machine"
  echo "      (build/mac-linux/make-package.sh) and copy frontend/dist here."
fi

echo
echo "Installed. Review backend/config/server.ini and database.ini (created on first start), then run:"
echo "  build/mac-linux/start.sh"
