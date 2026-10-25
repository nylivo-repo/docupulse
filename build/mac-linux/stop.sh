#!/usr/bin/env bash
# Stops the DocuPulse IDP API server started with start.sh (Mac / Linux).
source "$(dirname "$0")/common.sh"

if ! is_running; then
  echo "Not running."
  rm -f "$PID_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE")"
kill "$PID"
for _ in $(seq 1 15); do
  kill -0 "$PID" 2>/dev/null || { rm -f "$PID_FILE"; echo "Stopped."; exit 0; }
  sleep 1
done
echo "Still running after 15 s; forcing it to stop."
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "Stopped."
