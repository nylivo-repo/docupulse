#!/usr/bin/env bash
# Builds a clean, portable install package of DocuPulse IDP for another server, next to this folder:
#
#   build/mac-linux/make-package.sh [target] [python-version] [extra packages...]
#     target:  windows (default) | linux | mac-arm | mac-intel
#     python:  3.12 (default) or 3.11 — must match the Python installed on the target server
#     extra:   database driver, e.g. pymssql (SQL Server, the default for windows) or "psycopg[binary]"
#
# Result: ../IDP_dist/DocuPulse-IDP-<version>-<target>/ and a .zip of it, containing the source, the built
# web UI (frontend/dist), config templates, scripts, docs, and every Python package for the target
# (build/wheels) so the target needs no internet. Never included: this machine's Python environment,
# node_modules, documents, databases and backups, logs, secret.key, the first-run password file, and
# the live config files (the target creates its own from the .example templates).
source "$(dirname "$0")/common.sh"

TARGET="${1:-windows}"; PYVER="${2:-3.12}"
if (( $# >= 2 )); then shift 2; else shift $#; fi
EXTRAS=("$@")
if (( ${#EXTRAS[@]} == 0 )) && [[ "$TARGET" == windows ]]; then EXTRAS=(pymssql); fi
case "$TARGET" in
  linux)     PLATFORMS=(--platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64) ;;
  windows)   PLATFORMS=(--platform win_amd64) ;;
  mac-arm)   PLATFORMS=(--platform macosx_11_0_arm64) ;;
  mac-intel) PLATFORMS=(--platform macosx_10_15_x86_64) ;;
  *) echo "Unknown target '$TARGET' (windows | linux | mac-arm | mac-intel)"; exit 1 ;;
esac

VERSION="$(cd "$BACKEND" && "$PY" -c 'from app.core.config import settings; print(settings.VERSION)' 2>/dev/null || echo dev)"
NAME="DocuPulse-IDP-$VERSION-$TARGET"
OUT_ROOT="$(dirname "$ROOT")/IDP_dist"
OUT="$OUT_ROOT/$NAME"

# 1. The web UI, built here (the target needs no Node.js)
if node_ok; then
  echo "Building the web UI"
  (cd "$ROOT/frontend" && npm ci --silent && npm run build >/dev/null)
elif [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "frontend/dist is missing and Node.js 22/24 is not available to build it."; exit 1
fi

# 2. A clean copy of the project
echo "Copying the project to $OUT"
rm -rf "$OUT" "$OUT_ROOT/$NAME.zip"
mkdir -p "$OUT"
rsync -a \
  --exclude '/venv*' --exclude '/.claude' --exclude 'node_modules' --exclude '/frontend/.angular' \
  --exclude '/backend/storage' --exclude '/backend/sample_docs/*.pdf' \
  --exclude '/backend/config/server.ini' --exclude '/backend/config/database.ini' --exclude '/backend/config/auth.ini' \
  --exclude '/build/wheels' --exclude '__pycache__' --exclude '*.pyc' --exclude '.DS_Store' \
  --exclude '*.bak' --exclude '*.db' --exclude '*.log' --exclude 'secret.key' --exclude 'initial_admin_password.txt' \
  "$ROOT/" "$OUT/"
mkdir -p "$OUT/backend/storage"

# 3. Every Python package for the target (offline install)
echo "Downloading Python $PYVER packages for $TARGET (+ ${EXTRAS[*]:-no extras})"
EXTRA=(pip)
[[ "$TARGET" != mac-* ]] && EXTRA+=(opencv-python-headless)
(( ${#EXTRAS[@]} )) && EXTRA+=("${EXTRAS[@]}")
"$PY" -m pip download -q -d "$OUT/build/wheels" "${PLATFORMS[@]}" --python-version "$PYVER" --only-binary=:all: \
  -r "$BACKEND/requirements.txt" "${EXTRA[@]}"

# 4. A note for whoever installs it, and the zip
cat > "$OUT/INSTALL.txt" <<NOTE
DocuPulse IDP $VERSION — install package for $TARGET (Python $PYVER)

Needs on the server: Python $PYVER (python.org installer; tick "Add python.exe to PATH" on Windows).
Windows also needs the Microsoft Visual C++ Redistributable 2015-2022 (x64), used by the OCR engine;
most servers have it already. Nothing else: no internet, no Node.js. OCR models are inside the packages.

Windows:      build\\windows\\install.bat   then   build\\windows\\start.bat
Linux / Mac:  build/mac-linux/install.sh   then   build/mac-linux/start.sh

The first start creates backend\\config\\server.ini, database.ini and auth.ini from the .example files
(edit them, then restart) and a temporary admin password in backend\\storage\\initial_admin_password.txt.
Full guide: README.md and, once running, http://<server>:8000/docs (admin sign-in).
Packages included for: ${EXTRAS[*]:-SQLite only} (database drivers).
NOTE
(cd "$OUT_ROOT" && zip -qr "$NAME.zip" "$NAME")
echo "Done: $OUT ($(du -sh "$OUT" | cut -f1)) and $OUT_ROOT/$NAME.zip ($(du -sh "$OUT_ROOT/$NAME.zip" | cut -f1))"
