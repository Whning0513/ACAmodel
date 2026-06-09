#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: bash check_vllm_server.sh <port>" >&2
  exit 2
fi

TMP_ROOT="${TMP_ROOT:-/data/whn/tmp}"
PORT="$1"
HOST="${HOST:-127.0.0.1}"
API_KEY="${API_KEY:-local-vllm}"

unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
export PYTHONNOUSERSITE=1

MODELS_JSON="$(curl -fsS -H "Authorization: Bearer $API_KEY" "http://$HOST:$PORT/v1/models")"

mkdir -p "$TMP_ROOT"
TMP_CHAT_REQ="$(mktemp "$TMP_ROOT/check_vllm_req.XXXXXX.json")"
TMP_CHAT_RES="$(mktemp "$TMP_ROOT/check_vllm_res.XXXXXX.json")"
trap 'rm -f "$TMP_CHAT_REQ" "$TMP_CHAT_RES"' EXIT

MODELS_JSON="$MODELS_JSON" python - <<'PY' >"$TMP_CHAT_REQ"
import json
import os

models = json.loads(os.environ["MODELS_JSON"])
model_id = models["data"][0]["id"]
payload = {
    "model": model_id,
    "messages": [{"role": "user", "content": "Say hello in one short sentence."}],
    "max_tokens": 32,
    "temperature": 0.2,
}
print(json.dumps(payload, ensure_ascii=False))
PY

curl -fsS \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  "http://$HOST:$PORT/v1/chat/completions" \
  --data @"$TMP_CHAT_REQ" >"$TMP_CHAT_RES"

MODELS_JSON="$MODELS_JSON" TMP_CHAT_RES="$TMP_CHAT_RES" python - <<'PY'
import json
import os
import sys

models = json.loads(os.environ["MODELS_JSON"])
chat = json.load(open(os.environ["TMP_CHAT_RES"]))
content = (((chat.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()

models_ok = int(bool(models.get("data")))
chat_ok = int(bool(content))
print(f"MODELS_OK={models_ok}")
print(f"CHAT_OK={chat_ok}")
print(f"CONTENT_LEN={len(content)}")
if content:
    print(f"CONTENT_PREVIEW={content[:200]}")
if not (models_ok and chat_ok):
    sys.exit(1)
PY
