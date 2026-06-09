#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MAX_WORKERS="${MAX_WORKERS:-2}"
MONITOR_INTERVAL_SEC="${MONITOR_INTERVAL_SEC:-10}"
DEFAULT_GPU_MEMORY_UTILIZATION="${DEFAULT_GPU_MEMORY_UTILIZATION:-0.35}"
GPU_MEMORY_MARGIN_MIB="${GPU_MEMORY_MARGIN_MIB:-3072}"
GPU_7B="${GPU_7B:-auto}"
GPU_9B="${GPU_9B:-auto}"
MODEL_RUN_MODE="${MODEL_RUN_MODE:-sequential}"
VLLM_CONDA_ENV="${VLLM_CONDA_ENV:-}"
VLLM_CONDA_ENV_7B="${VLLM_CONDA_ENV_7B:-${VLLM_CONDA_ENV:-ACAvllms124}}"
VLLM_CONDA_ENV_9B="${VLLM_CONDA_ENV_9B:-${VLLM_CONDA_ENV:-vllm017_full}}"
CONTINUE_ON_MODEL_FAILURE="${CONTINUE_ON_MODEL_FAILURE:-1}"
LLM_MAX_TOKENS_7B="${LLM_MAX_TOKENS_7B:-2048}"
LLM_MAX_TOKENS_9B="${LLM_MAX_TOKENS_9B:-2048}"
MAX_MODEL_LEN_7B="${MAX_MODEL_LEN_7B:-8192}"
MAX_MODEL_LEN_9B="${MAX_MODEL_LEN_9B:-8192}"
VLLM_USE_V1_7B="${VLLM_USE_V1_7B:-0}"
VLLM_USE_V1_9B="${VLLM_USE_V1_9B:-}"

PLAN_JSON="$(mktemp)"
cleanup() {
  rm -f "$PLAN_JSON"
}
trap cleanup EXIT

python "$ROOT/scripts/aca_model_supervisor.py" plan-probe20-dual \
  --gpu-7b "$GPU_7B" \
  --gpu-9b "$GPU_9B" \
  --default-gpu-memory-utilization "$DEFAULT_GPU_MEMORY_UTILIZATION" \
  --gpu-memory-margin-mib "$GPU_MEMORY_MARGIN_MIB" \
  --run-mode "$MODEL_RUN_MODE" \
  >"$PLAN_JSON"

GPU_7B_AUTO="$(python - "$PLAN_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["plan"]["qwen25-coder-7b"]["gpu_id"])
PY
)"
GPU_9B_AUTO="$(python - "$PLAN_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["plan"]["qwen35-9b"]["gpu_id"])
PY
)"
GPU_MEMORY_UTILIZATION_7B_AUTO="$(python - "$PLAN_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["plan"]["qwen25-coder-7b"]["gpu_memory_utilization"])
PY
)"
GPU_MEMORY_UTILIZATION_9B_AUTO="$(python - "$PLAN_JSON" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["plan"]["qwen35-9b"]["gpu_memory_utilization"])
PY
)"

export GPU_7B="${GPU_7B_AUTO}"
export GPU_9B="${GPU_9B_AUTO}"
export GPU_MEMORY_UTILIZATION_7B="${GPU_MEMORY_UTILIZATION_7B:-$GPU_MEMORY_UTILIZATION_7B_AUTO}"
export GPU_MEMORY_UTILIZATION_9B="${GPU_MEMORY_UTILIZATION_9B:-$GPU_MEMORY_UTILIZATION_9B_AUTO}"
export MAX_WORKERS
export MONITOR_INTERVAL_SEC
export MODEL_RUN_MODE
export VLLM_CONDA_ENV_7B
export VLLM_CONDA_ENV_9B
export CONTINUE_ON_MODEL_FAILURE
export LLM_MAX_TOKENS_7B
export LLM_MAX_TOKENS_9B
export MAX_MODEL_LEN_7B
export MAX_MODEL_LEN_9B
export VLLM_USE_V1_7B
export VLLM_USE_V1_9B

echo "Safe probe20 dual-model launcher"
echo "  root: $ROOT"
echo "  mode: $MODEL_RUN_MODE"
echo "  7B: gpu=$GPU_7B env=$VLLM_CONDA_ENV_7B max_model_len=$MAX_MODEL_LEN_7B llm_max_tokens=$LLM_MAX_TOKENS_7B gpu_mem_util=$GPU_MEMORY_UTILIZATION_7B"
echo "  9B: gpu=$GPU_9B env=$VLLM_CONDA_ENV_9B max_model_len=$MAX_MODEL_LEN_9B llm_max_tokens=$LLM_MAX_TOKENS_9B gpu_mem_util=$GPU_MEMORY_UTILIZATION_9B"
echo "  continue_on_model_failure: $CONTINUE_ON_MODEL_FAILURE"
echo

exec bash "$ROOT/scripts/run_gtor4_probe20_dual_progress.sh"
