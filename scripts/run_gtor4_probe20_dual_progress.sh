#!/usr/bin/env bash
set -euo pipefail

ROOT="${ACA_MODEL_ROOT:-/data/whn/Projects/ACA_model}"
ACA_ROOT="${ACA_ROOT:-/data/whn/Projects/ACA}"
OLD_ROOT="${ACA_MODEL_COMPAT_ROOT:-/data/whn/ACA_model}"
OLD_ACA_ROOT="${ACA_COMPAT_ROOT:-/data/whn/ACA}"

MODEL_7B="${MODEL_7B:-qwen25-coder-7b}"
MODEL_9B="${MODEL_9B:-qwen35-9b}"
PORT_7B="${PORT_7B:-8017}"
PORT_9B="${PORT_9B:-8029}"
GPU_7B="${GPU_7B:-auto}"
GPU_9B="${GPU_9B:-auto}"
MAX_WORKERS="${MAX_WORKERS:-2}"
GTOR_PROMPT_PROFILE="${GTOR_PROMPT_PROFILE:-legacy}"
MONITOR_INTERVAL_SEC="${MONITOR_INTERVAL_SEC:-10}"
DEFAULT_GPU_MEMORY_UTILIZATION="${DEFAULT_GPU_MEMORY_UTILIZATION:-0.35}"
GPU_MEMORY_MARGIN_MIB="${GPU_MEMORY_MARGIN_MIB:-3072}"
MODEL_RUN_MODE="${MODEL_RUN_MODE:-sequential}"
VLLM_CONDA_ENV="${VLLM_CONDA_ENV:-}"
VLLM_CONDA_ENV_7B="${VLLM_CONDA_ENV_7B:-${VLLM_CONDA_ENV:-ACAvllms124}}"
VLLM_CONDA_ENV_9B="${VLLM_CONDA_ENV_9B:-${VLLM_CONDA_ENV:-vllm017_full}}"
CONTINUE_ON_MODEL_FAILURE="${CONTINUE_ON_MODEL_FAILURE:-0}"
LLM_MAX_TOKENS_7B="${LLM_MAX_TOKENS_7B:-2048}"
LLM_MAX_TOKENS_9B="${LLM_MAX_TOKENS_9B:-2048}"
MAX_MODEL_LEN_7B="${MAX_MODEL_LEN_7B:-8192}"
MAX_MODEL_LEN_9B="${MAX_MODEL_LEN_9B:-8192}"
VLLM_USE_V1_7B="${VLLM_USE_V1_7B:-0}"
VLLM_USE_V1_9B="${VLLM_USE_V1_9B:-}"

LOG_DIR="$ROOT/outputs/gtor4_probe20/launcher_logs"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
LOG_7B="$LOG_DIR/probe20_${MODEL_7B//-/_}_${RUN_TS}.log"
LOG_9B="$LOG_DIR/probe20_${MODEL_9B//-/_}_${RUN_TS}.log"
CLEANED_UP=0

usage() {
  cat <<EOF
Usage:
  bash $0

Runs GTOR probe20 for two models and prints weighted progress bars.
Default mode is sequential: 7B first, then 9B.

Environment overrides:
  ACA_MODEL_ROOT          default: /data/whn/Projects/ACA_model
  ACA_ROOT                default: /data/whn/Projects/ACA
  MODEL_7B                default: qwen25-coder-7b
  MODEL_9B                default: qwen35-9b
  PORT_7B                 default: 8017
  PORT_9B                 default: 8029
  GPU_7B                  default: auto
  GPU_9B                  default: auto
  GPU_MEMORY_UTILIZATION_7B
  GPU_MEMORY_UTILIZATION_9B
  DEFAULT_GPU_MEMORY_UTILIZATION default: 0.35
  GPU_MEMORY_MARGIN_MIB   default: 3072
  MAX_WORKERS             default: 2
  MODEL_RUN_MODE          default: sequential (or parallel)
  VLLM_CONDA_ENV          optional shared override for both models
  VLLM_CONDA_ENV_7B       default: ACAvllms124
  VLLM_CONDA_ENV_9B       default: vllm017_full
  CONTINUE_ON_MODEL_FAILURE default: 0
  LLM_MAX_TOKENS_7B       default: 2048
  LLM_MAX_TOKENS_9B       default: 2048
  MAX_MODEL_LEN_7B        default: 8192
  MAX_MODEL_LEN_9B        default: 8192
  VLLM_USE_V1_7B          default: 0
  VLLM_USE_V1_9B          default: unset
  GTOR_PROMPT_PROFILE     default: legacy
  MONITOR_INTERVAL_SEC    default: 10

ETA weights:
  BaseG=1 BaseCG=1 ITERG=5 AgentG=5
EOF
}

DRY_RUN=0
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
fi

gpu_table() {
  nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null || true
}

ensure_compat_link() {
  local target="$1"
  local link="$2"
  if [[ -e "$link" || -L "$link" ]]; then
    local resolved
    resolved="$(realpath "$link" 2>/dev/null || true)"
    if [[ "$resolved" != "$target" ]]; then
      echo "Compatibility path exists but does not point to expected target:" >&2
      echo "  path:   $link" >&2
      echo "  points: ${resolved:-unknown}" >&2
      echo "  expect: $target" >&2
      exit 1
    fi
    return 0
  fi
  ln -s "$target" "$link"
}

discover_managed_dir() {
  local log_path="$1"
  local raw
  raw="$(awk '/managed_dir:/ {print $2}' "$log_path" 2>/dev/null | tail -n 1 || true)"
  if [[ -z "$raw" ]]; then
    return 0
  fi
  printf '%s\n' "${raw/#$OLD_ROOT/$ROOT}"
}

json_field() {
  local path="$1"
  local field="$2"
  python - "$path" "$field" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
field = sys.argv[2]
if not path.exists():
    raise SystemExit(0)
obj = json.loads(path.read_text(encoding="utf-8"))
value = obj
for part in field.split("."):
    value = value.get(part) if isinstance(value, dict) else None
print("" if value is None else value)
PY
}

print_model_progress() {
  local label="$1"
  local log_path="$2"
  local managed_dir
  managed_dir="$(discover_managed_dir "$log_path")"

  echo "## $label"
  echo "launcher_log: $log_path"

  if [[ -z "$managed_dir" || ! -d "$managed_dir" ]]; then
    echo "managed_dir: pending"
    tail -n 4 "$log_path" 2>/dev/null || true
    echo
    return 0
  fi

  local state
  state="$(json_field "$managed_dir/run_status.json" state)"
  echo "managed_dir: $managed_dir"
  echo "state: ${state:-unknown}"
  case "$state" in
    SERVICE_START_FAILED|CHAT_CHECK_FAILED|SERVICE_CONTAMINATED|ACA_FAILED|ARTIFACT_INVALID|ANALYZER_FAILED|TASKSET_MISMATCH)
      echo "diagnosis:"
      python "$ROOT/scripts/aca_model_supervisor.py" classify-run "$managed_dir" | sed 's/^/  /' || true
      ;;
  esac

  local run_dir
  run_dir="$(json_field "$managed_dir/run_manifest.json" run_dir)"
  if [[ -n "$run_dir" ]]; then
    run_dir="${run_dir/#$OLD_ROOT/$ROOT}"
    python "$ROOT/scripts/monitor_run_progress.py" "$run_dir" || true
  else
    echo "run_dir: pending"
  fi
  echo
}

launch_model() {
  local model="$1"
  local port="$2"
  local gpu="$3"
  local gpu_mem_util="$4"
  local llm_max_tokens="$5"
  local max_model_len="$6"
  local vllm_use_v1="$7"
  local vllm_conda_env="$8"
  local log_path="$9"
  (
    cd "$ROOT"
    if [[ -n "$vllm_use_v1" ]]; then
      MAX_WORKERS="$MAX_WORKERS" GTOR_PROMPT_PROFILE="$GTOR_PROMPT_PROFILE" \
        VLLM_CONDA_ENV="$vllm_conda_env" \
        LLM_MAX_TOKENS="$llm_max_tokens" \
        GPU_MEMORY_UTILIZATION="$gpu_mem_util" \
        MAX_MODEL_LEN="$max_model_len" \
        VLLM_USE_V1="$vllm_use_v1" \
        bash "$ROOT/scripts/run_gtor4_probe20_model.sh" "$model" "$port" "$gpu"
    else
      MAX_WORKERS="$MAX_WORKERS" GTOR_PROMPT_PROFILE="$GTOR_PROMPT_PROFILE" \
        VLLM_CONDA_ENV="$vllm_conda_env" \
        LLM_MAX_TOKENS="$llm_max_tokens" \
        GPU_MEMORY_UTILIZATION="$gpu_mem_util" \
        MAX_MODEL_LEN="$max_model_len" \
        bash "$ROOT/scripts/run_gtor4_probe20_model.sh" "$model" "$port" "$gpu"
    fi
  ) >"$log_path" 2>&1 &
  LAUNCH_PID=$!
}

monitor_single_launcher() {
  local label="$1"
  local model="$2"
  local log_path="$3"
  local pid="$4"
  while true; do
    printf '\033[H\033[2J'
    echo "GTOR probe20 $MODEL_RUN_MODE progress - $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    print_model_progress "$label / $model" "$log_path"
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep "$MONITOR_INTERVAL_SEC"
  done
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM
  if [[ "$CLEANED_UP" -eq 1 ]]; then
    exit "$code"
  fi
  CLEANED_UP=1
  if [[ "$code" -ne 0 ]]; then
    echo
    echo "Interrupted or failed; terminating launch wrappers if still running."
    kill "${PID_7B:-0}" "${PID_9B:-0}" 2>/dev/null || true
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

mkdir -p "$LOG_DIR"
ensure_compat_link "$ROOT" "$OLD_ROOT"
ensure_compat_link "$ACA_ROOT" "$OLD_ACA_ROOT"

PLAN_JSON="$LOG_DIR/probe20_dual_plan_${RUN_TS}.json"
python "$ROOT/scripts/aca_model_supervisor.py" plan-probe20-dual \
  --gpu-7b "$GPU_7B" \
  --gpu-9b "$GPU_9B" \
  --default-gpu-memory-utilization "$DEFAULT_GPU_MEMORY_UTILIZATION" \
  --gpu-memory-margin-mib "$GPU_MEMORY_MARGIN_MIB" \
  --run-mode "$MODEL_RUN_MODE" \
  >"$PLAN_JSON"

GPU_7B="$(json_field "$PLAN_JSON" "plan.qwen25-coder-7b.gpu_id")"
GPU_9B="$(json_field "$PLAN_JSON" "plan.qwen35-9b.gpu_id")"
PLANNED_GPU_MEMORY_UTILIZATION_7B="$(json_field "$PLAN_JSON" "plan.qwen25-coder-7b.gpu_memory_utilization")"
PLANNED_GPU_MEMORY_UTILIZATION_9B="$(json_field "$PLAN_JSON" "plan.qwen35-9b.gpu_memory_utilization")"
GPU_MEMORY_UTILIZATION_7B="${GPU_MEMORY_UTILIZATION_7B:-$PLANNED_GPU_MEMORY_UTILIZATION_7B}"
GPU_MEMORY_UTILIZATION_9B="${GPU_MEMORY_UTILIZATION_9B:-$PLANNED_GPU_MEMORY_UTILIZATION_9B}"

echo "Starting GTOR probe20 dual-model run with weighted progress."
echo "  7B: $MODEL_7B GPU=$GPU_7B PORT=$PORT_7B"
echo "  9B: $MODEL_9B GPU=$GPU_9B PORT=$PORT_9B"
echo "  methods: BaseG BaseCG ITERG AgentG"
echo "  weights: BaseG=1 BaseCG=1 ITERG=5 AgentG=5"
echo "  gpu_mem_util_7b: $GPU_MEMORY_UTILIZATION_7B"
echo "  gpu_mem_util_9b: $GPU_MEMORY_UTILIZATION_9B"
echo "  llm_max_tokens_7b: $LLM_MAX_TOKENS_7B"
echo "  llm_max_tokens_9b: $LLM_MAX_TOKENS_9B"
echo "  max_model_len_7b: $MAX_MODEL_LEN_7B"
echo "  max_model_len_9b: $MAX_MODEL_LEN_9B"
echo "  vllm_use_v1_7b: ${VLLM_USE_V1_7B:-default}"
echo "  vllm_use_v1_9b: ${VLLM_USE_V1_9B:-default}"
echo "  max_workers: $MAX_WORKERS"
echo "  model_run_mode: $MODEL_RUN_MODE"
echo "  vllm_conda_env_7b: $VLLM_CONDA_ENV_7B"
echo "  vllm_conda_env_9b: $VLLM_CONDA_ENV_9B"
echo "  prompt_profile: $GTOR_PROMPT_PROFILE"
echo "  plan_json: $PLAN_JSON"
echo
echo "Current GPU memory snapshot:"
gpu_table | sed 's/^/  /'
echo

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "DRY_RUN=1; not launching."
  exit 0
fi

if [[ "$MODEL_RUN_MODE" == "sequential" ]]; then
  launch_model "$MODEL_7B" "$PORT_7B" "$GPU_7B" "$GPU_MEMORY_UTILIZATION_7B" "$LLM_MAX_TOKENS_7B" "$MAX_MODEL_LEN_7B" "$VLLM_USE_V1_7B" "$VLLM_CONDA_ENV_7B" "$LOG_7B"
  PID_7B="$LAUNCH_PID"
  echo "launcher_pid_7b=$PID_7B log=$LOG_7B"
  monitor_single_launcher "7B" "$MODEL_7B" "$LOG_7B" "$PID_7B"
  set +e
  wait "$PID_7B"
  STATUS_7B=$?
  set -e

  if [[ "$STATUS_7B" -ne 0 && "$CONTINUE_ON_MODEL_FAILURE" != "1" ]]; then
    STATUS_9B=125
    printf '\033[H\033[2J'
    echo "GTOR probe20 sequential stopped after 7B failure - $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    print_model_progress "7B / $MODEL_7B" "$LOG_7B"
    echo "9B / $MODEL_9B"
    echo "skipped: 7B launcher failed. Set CONTINUE_ON_MODEL_FAILURE=1 to run 9B anyway."
  else

    launch_model "$MODEL_9B" "$PORT_9B" "$GPU_9B" "$GPU_MEMORY_UTILIZATION_9B" "$LLM_MAX_TOKENS_9B" "$MAX_MODEL_LEN_9B" "$VLLM_USE_V1_9B" "$VLLM_CONDA_ENV_9B" "$LOG_9B"
    PID_9B="$LAUNCH_PID"
    echo "launcher_pid_9b=$PID_9B log=$LOG_9B"
    monitor_single_launcher "9B" "$MODEL_9B" "$LOG_9B" "$PID_9B"
    set +e
    wait "$PID_9B"
    STATUS_9B=$?
    set -e
  fi
else
  launch_model "$MODEL_7B" "$PORT_7B" "$GPU_7B" "$GPU_MEMORY_UTILIZATION_7B" "$LLM_MAX_TOKENS_7B" "$MAX_MODEL_LEN_7B" "$VLLM_USE_V1_7B" "$VLLM_CONDA_ENV_7B" "$LOG_7B"
  PID_7B="$LAUNCH_PID"
  launch_model "$MODEL_9B" "$PORT_9B" "$GPU_9B" "$GPU_MEMORY_UTILIZATION_9B" "$LLM_MAX_TOKENS_9B" "$MAX_MODEL_LEN_9B" "$VLLM_USE_V1_9B" "$VLLM_CONDA_ENV_9B" "$LOG_9B"
  PID_9B="$LAUNCH_PID"
  echo "launcher_pid_7b=$PID_7B log=$LOG_7B"
  echo "launcher_pid_9b=$PID_9B log=$LOG_9B"
  echo

  while true; do
    printf '\033[H\033[2J'
    echo "GTOR probe20 parallel progress - $(date '+%Y-%m-%d %H:%M:%S')"
    echo
    print_model_progress "7B / $MODEL_7B" "$LOG_7B"
    print_model_progress "9B / $MODEL_9B" "$LOG_9B"

    alive_7b=0
    alive_9b=0
    kill -0 "$PID_7B" 2>/dev/null && alive_7b=1 || true
    kill -0 "$PID_9B" 2>/dev/null && alive_9b=1 || true
    if [[ "$alive_7b" -eq 0 && "$alive_9b" -eq 0 ]]; then
      break
    fi
    sleep "$MONITOR_INTERVAL_SEC"
  done

  set +e
  wait "$PID_7B"
  STATUS_7B=$?
  wait "$PID_9B"
  STATUS_9B=$?
  set -e
fi

if [[ "$MODEL_RUN_MODE" == "sequential" ]]; then
  printf '\033[H\033[2J'
  echo "GTOR probe20 sequential final progress - $(date '+%Y-%m-%d %H:%M:%S')"
  echo
  print_model_progress "7B / $MODEL_7B" "$LOG_7B"
  print_model_progress "9B / $MODEL_9B" "$LOG_9B"
  fi

echo
echo "Final launcher status:"
echo "  7B status: $STATUS_7B log=$LOG_7B"
echo "  9B status: $STATUS_9B log=$LOG_9B"
echo
for item in "7B:$LOG_7B" "9B:$LOG_9B"; do
  label="${item%%:*}"
  log_path="${item#*:}"
  managed_dir="$(discover_managed_dir "$log_path")"
  if [[ -n "$managed_dir" && -d "$managed_dir" ]]; then
    echo "$label final diagnosis:"
    python "$ROOT/scripts/aca_model_supervisor.py" classify-run "$managed_dir" | sed 's/^/  /' || true
  fi
done

trap - EXIT INT TERM
exit $(( STATUS_7B != 0 || STATUS_9B != 0 ))
