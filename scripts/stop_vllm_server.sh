#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash stop_vllm_server.sh <port>" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PORT="$1"
RUN_DIR="$ROOT/run/vllm"

shopt -s nullglob
PID_FILES=("$RUN_DIR"/*_"$PORT".pid)
shopt -u nullglob

if [[ ${#PID_FILES[@]} -eq 0 ]]; then
  echo "No PID file found for port $PORT under $RUN_DIR" >&2
  echo "Please inspect the port manually." >&2
  exit 1
fi

if [[ ${#PID_FILES[@]} -gt 1 ]]; then
  echo "Multiple PID files found for port $PORT:" >&2
  printf '  %s\n' "${PID_FILES[@]}" >&2
  exit 1
fi

PID_FILE="${PID_FILES[0]}"
PID="$(cat "$PID_FILE")"

if [[ -z "$PID" || ! "$PID" =~ ^[0-9]+$ ]]; then
  echo "Invalid PID in $PID_FILE" >&2
  exit 1
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
fi

for _ in $(seq 1 30); do
  if ! kill -0 "$PID" 2>/dev/null && ! ss -ltn "( sport = :$PORT )" | tail -n +2 | grep -q .; then
    rm -f "$PID_FILE"
    echo "STOPPED=1"
    echo "PORT=$PORT"
    echo "PID=$PID"
    exit 0
  fi
  sleep 1
done

echo "Failed to confirm shutdown for PID $PID on port $PORT" >&2
exit 1
