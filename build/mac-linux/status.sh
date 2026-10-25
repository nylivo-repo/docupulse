#!/usr/bin/env bash
# Shows whether the DocuPulse IDP API server is running and answering (Mac / Linux).
source "$(dirname "$0")/common.sh"

ADDRESS="$(server_address)"
if is_running; then
  if health "$ADDRESS"; then
    echo "Running at http://$ADDRESS (process $(cat "$PID_FILE")), healthy."
  else
    echo "Process $(cat "$PID_FILE") is running but http://$ADDRESS is not answering; see $LOG_FILE"
    exit 1
  fi
else
  echo "Not running."
  exit 3
fi
