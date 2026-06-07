#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: bash /data/whn/ACA_model/scripts/start_acavllms_vllm.sh <model_alias> <port> <gpu_id>" >&2
  exit 2
fi

MODEL_ALIAS="$1"
PORT="$2"
GPU_ID="$3"

case "$MODEL_ALIAS" in
  qwen35-4b)
    MODEL_PATH="/data/LLMs/Qwen3.5-4B"
    DEFAULT_ENV="vllm017_full"
    DEFAULT_FALLBACK_ENV="vllm_test_017"
    ;;
  qwen35-9b)
    MODEL_PATH="/data/LLMs/Qwen3.5-9B"
    DEFAULT_ENV="vllm017_full"
    DEFAULT_FALLBACK_ENV="vllm_test_017"
    ;;
  qwen25-coder-7b)
    MODEL_PATH="/data/LLMs/Qwen2.5-Coder-7B-Instruct"
    DEFAULT_ENV="vllm017_full"
    DEFAULT_FALLBACK_ENV="vllm_test_017"
    ;;
  *)
    echo "Unsupported model alias: $MODEL_ALIAS" >&2
    exit 2
    ;;
esac

if [[ ! -d "$MODEL_PATH" ]]; then
  echo "Model path does not exist: $MODEL_PATH" >&2
  exit 1
fi

if ! [[ "$PORT" =~ ^[0-9]+$ ]]; then
  echo "Invalid port: $PORT" >&2
  exit 2
fi

if ! [[ "$GPU_ID" =~ ^[0-9]+$ ]]; then
  echo "Invalid gpu_id: $GPU_ID" >&2
  exit 2
fi

HOST="${HOST:-127.0.0.1}"
API_KEY="${API_KEY:-local-vllm}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.35}"
DTYPE="${DTYPE:-auto}"
ENFORCE_EAGER="${ENFORCE_EAGER:-1}"
ENABLE_AUTO_TOOL_CHOICE="${ENABLE_AUTO_TOOL_CHOICE:-1}"
TOOL_CALL_PARSER="${TOOL_CALL_PARSER:-hermes}"
STARTUP_TIMEOUT_SEC="${STARTUP_TIMEOUT_SEC:-240}"
PREFERRED_ENV="${VLLM_CONDA_ENV:-$DEFAULT_ENV}"
FALLBACK_ENV="${VLLM_FALLBACK_CONDA_ENV:-$DEFAULT_FALLBACK_ENV}"

RUN_DIR="/data/whn/ACA_model/run/vllm"
LOG_DIR="/data/whn/ACA_model/logs/vllm"
PID_FILE="$RUN_DIR/${MODEL_ALIAS}_${PORT}.pid"
LOG_FILE="$LOG_DIR/${MODEL_ALIAS}_${PORT}.log"

if ss -ltn "( sport = :$PORT )" | tail -n +2 | grep -q .; then
  echo "Port $PORT is already in use. Refusing to start." >&2
  exit 1
fi

mkdir -p "$RUN_DIR" "$LOG_DIR" /data/whn/tmp/acavllms-pip-cache /data/whn/tmp/acavllms-hf /data/whn/tmp/acavllms-xdg

export PYTHONNOUSERSITE=1
if [[ -d /data/package/cuda-12.4 ]]; then
  export CUDA_HOME=/data/package/cuda-12.4
  export PATH="/data/package/cuda-12.4/bin:${PATH}"
  export LD_LIBRARY_PATH="/data/package/cuda-12.4/lib64${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
fi

check_env_candidate() {
  local env_name="$1"
  source /data/miniconda3/bin/activate "$env_name" >/dev/null 2>&1 || return 1
  python - <<'PY' >/dev/null 2>&1
import importlib.metadata as m
import torch
import vllm  # noqa: F401

assert m.version("vllm")
assert torch.cuda.is_available()
torch.cuda.init()
torch.cuda.get_device_name(0)
PY
}

SELECTED_ENV=""
ENV_REASON=""
if check_env_candidate "$PREFERRED_ENV"; then
  SELECTED_ENV="$PREFERRED_ENV"
  ENV_REASON="preferred_env_ok"
elif [[ "$FALLBACK_ENV" != "$PREFERRED_ENV" ]] && check_env_candidate "$FALLBACK_ENV"; then
  SELECTED_ENV="$FALLBACK_ENV"
  ENV_REASON="preferred_env_unusable_fallback_ok"
else
  echo "No usable vLLM conda env found. Tried: $PREFERRED_ENV, $FALLBACK_ENV" >&2
  echo "Hint: candidate env must import vllm and report torch.cuda.is_available() == True" >&2
  exit 1
fi

source /data/miniconda3/bin/activate "$SELECTED_ENV"

export TMPDIR=/data/whn/tmp
export PIP_CACHE_DIR=/data/whn/tmp/acavllms-pip-cache
export HF_HOME=/data/whn/tmp/acavllms-hf
export XDG_CACHE_HOME=/data/whn/tmp/acavllms-xdg
export TRANSFORMERS_CACHE=/data/whn/tmp/acavllms-hf/transformers

unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export HOST PORT API_KEY MAX_MODEL_LEN GPU_MEMORY_UTILIZATION DTYPE
export ENFORCE_EAGER ENABLE_AUTO_TOOL_CHOICE TOOL_CALL_PARSER

VLLM_BIN="$(command -v vllm || true)"
if [[ -z "$VLLM_BIN" ]]; then
  echo "vllm is not installed in selected env: $SELECTED_ENV" >&2
  exit 1
fi

rm -f "$PID_FILE"

NOHUP_CMD=("$VLLM_BIN" "serve" "$MODEL_PATH"
  "--host" "$HOST"
  "--port" "$PORT"
  "--dtype" "$DTYPE"
  "--api-key" "$API_KEY"
  "--served-model-name" "$MODEL_ALIAS"
  "--tensor-parallel-size" "1"
  "--gpu-memory-utilization" "$GPU_MEMORY_UTILIZATION"
  "--max-model-len" "$MAX_MODEL_LEN")

if [[ "$MODEL_ALIAS" == qwen35-* ]]; then
  NOHUP_CMD+=(
    "--reasoning-parser" "qwen3"
    "--default-chat-template-kwargs" '{"enable_thinking": false}'
  )
fi

if [[ "$ENABLE_AUTO_TOOL_CHOICE" == "1" ]]; then
  NOHUP_CMD+=("--enable-auto-tool-choice" "--tool-call-parser" "$TOOL_CALL_PARSER")
fi

if [[ "$ENFORCE_EAGER" == "1" ]]; then
  NOHUP_CMD+=("--enforce-eager")
fi

nohup "${NOHUP_CMD[@]}" >"$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" >"$PID_FILE"

READY=0
for _ in $(seq 1 "$STARTUP_TIMEOUT_SEC"); do
  if ! kill -0 "$PID" 2>/dev/null; then
    break
  fi
  if curl -fsS -H "Authorization: Bearer $API_KEY" "http://$HOST:$PORT/v1/models" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 1
done

if [[ "$READY" != "1" ]]; then
  echo "vLLM failed to become ready for $MODEL_ALIAS on port $PORT" >&2
  echo "===== last 80 log lines =====" >&2
  tail -n 80 "$LOG_FILE" >&2 || true
  exit 1
fi

echo "VLLM_READY=1"
echo "MODEL_ALIAS=$MODEL_ALIAS"
echo "MODEL_PATH=$MODEL_PATH"
echo "PORT=$PORT"
echo "GPU_ID=$GPU_ID"
echo "CONDA_ENV=$SELECTED_ENV"
echo "ENV_REASON=$ENV_REASON"
echo "API_BASE=http://$HOST:$PORT/v1"
echo "PID=$PID"
echo "LOG=$LOG_FILE"
echo "STARTUP_TIMEOUT_SEC=$STARTUP_TIMEOUT_SEC"
