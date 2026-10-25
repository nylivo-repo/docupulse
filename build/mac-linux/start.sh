#!/usr/bin/env bash
# Starts the DocuPulse IDP API server in the background (Mac / Linux).
# Settings: backend/config/server.ini and database.ini. Log: backend/storage/logs/server.log
source "$(dirname "$0")/common.sh"

[[ -x "$PY" ]] || { echo "Not installed yet: run build/mac-linux/install.sh first."; exit 1; }
if is_running; then
  echo "Already running (process $(cat "$PID_FILE"))."
  exit 0
fi

mkdir -p "$LOG_DIR"
ADDRESS="$(server_address)"
cd "$BACKEND"
nohup "$PY" run.py >>"$LOG_FILE" 2>&1 </dev/null &
echo $! >"$PID_FILE"

for _ in $(seq 1 60); do
  if health "$ADDRESS"; then
    echo "DocuPulse is running at http://$ADDRESS (process $(cat "$PID_FILE"))."
    exit 0
  fi
  if ! is_running; then
    echo "The server stopped during start-up. Last log lines:"
    tail -n 20 "$LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
  fi
  sleep 1
done
echo "Started (process $(cat "$PID_FILE")) but http://$ADDRESS is not answering yet; see $LOG_FILE"
