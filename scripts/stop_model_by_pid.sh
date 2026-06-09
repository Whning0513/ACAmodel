#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: bash /data/whn/ACA_model/scripts/stop_model_by_pid.sh <pid|pidfile> [grace_sec]" >&2
  exit 2
fi

TARGET="$1"
GRACE_SEC="${2:-30}"

if [[ -f "$TARGET" ]]; then
  PID="$(cat "$TARGET")"
  PIDFILE="$TARGET"
else
  PID="$TARGET"
  PIDFILE=""
fi

if [[ -z "$PID" || ! "$PID" =~ ^[0-9]+$ ]]; then
  echo "Invalid PID: $PID" >&2
  exit 1
fi

if ! kill -0 "$PID" 2>/dev/null; then
  [[ -n "$PIDFILE" ]] && rm -f "$PIDFILE"
  echo "PID $PID is not running"
  exit 0
fi

kill "$PID"
for _ in $(seq 1 "$GRACE_SEC"); do
  if ! kill -0 "$PID" 2>/dev/null; then
    [[ -n "$PIDFILE" ]] && rm -f "$PIDFILE"
    echo "STOPPED=1"
    echo "PID=$PID"
    exit 0
  fi
  sleep 1
done

echo "Failed to stop PID $PID within ${GRACE_SEC}s" >&2
exit 1
