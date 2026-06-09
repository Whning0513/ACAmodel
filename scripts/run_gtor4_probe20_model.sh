#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: bash run_gtor4_probe20_model.sh <model_alias> [port] [gpu_id]" >&2
  exit 2
fi

MODEL_ALIAS="$1"
PORT_ARG="${2:-}"
GPU_ID="${3:-${GPU_ID:-0}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_DIR="$ROOT/scripts"
TASKSET_FILE="$ROOT/tasksets/gtor_probe20_ids.txt"
REPORT_DIR="$ROOT/reports"
DEFAULT_ACA_DATA_BASE="$ROOT/ACA/data/waFocusedData_submit_0526_final"
if [[ ! -d "$DEFAULT_ACA_DATA_BASE" ]]; then
  DEFAULT_ACA_DATA_BASE="/data/whn/ACA/data/waFocusedData_submit_0526_final"
fi
ACA_DATA_BASE="${ACA_DATA_BASE:-$DEFAULT_ACA_DATA_BASE}"
GTOR_PROMPT_PROFILE="${GTOR_PROMPT_PROFILE:-legacy}"
MAX_WORKERS="${MAX_WORKERS:-8}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.35}"
VLLM_USE_V1="${VLLM_USE_V1:-}"

if [[ "$GTOR_PROMPT_PROFILE" == "small_model_minimal" ]]; then
  OUTPUT_BASE="$ROOT/outputs/gtor4_probe20_small_prompt"
  RUN_LABEL_PREFIX="gtor4_probe20_small_prompt"
else
  OUTPUT_BASE="$ROOT/outputs/gtor4_probe20"
  RUN_LABEL_PREFIX="gtor4_probe20"
fi

case "$MODEL_ALIAS" in
  qwen35-4b)
    MODEL_KEY="qwen35-4b"
    PREFERRED_PORT=8024
    MODEL_DIR_KEY="qwen35_4b"
    DEFAULT_MAX_MODEL_LEN=8192
    ;;
  qwen25-coder-7b)
    MODEL_KEY="qwen25-coder-7b"
    PREFERRED_PORT=8017
    MODEL_DIR_KEY="qwen25_coder_7b"
    DEFAULT_MAX_MODEL_LEN=8192
    ;;
  qwen35-9b)
    MODEL_KEY="qwen35-9b"
    PREFERRED_PORT=8029
    MODEL_DIR_KEY="qwen35_9b"
    DEFAULT_MAX_MODEL_LEN=8192
    ;;
  *)
    echo "Unsupported model alias: $MODEL_ALIAS" >&2
    exit 2
    ;;
esac

LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-2048}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-$DEFAULT_MAX_MODEL_LEN}"

PORT="${PORT_ARG:-$PREFERRED_PORT}"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
PROFILE_TAG="${GTOR_PROMPT_PROFILE//-/_}"
MANAGED_RUN_ID="probe20_${PROFILE_TAG}_${MODEL_ALIAS//-/_}_${RUN_STAMP}"
MANAGED_RUN_PY="$SCRIPT_DIR/managed_run.py"
MANAGED_DIR="$ROOT/managed_runs/$MANAGED_RUN_ID"
MODEL_OUT="$OUTPUT_BASE/$MODEL_DIR_KEY"
BLOCKER_MD="$REPORT_DIR/probe20_blocker_${MODEL_ALIAS}.md"

rm -f "$BLOCKER_MD"

if [[ ! -f "$TASKSET_FILE" ]]; then
  echo "Missing taskset: $TASKSET_FILE" >&2
  exit 1
fi

echo "=== managed probe20 wrapper ==="
echo "  model_alias:  $MODEL_ALIAS"
echo "  model_key:    $MODEL_KEY"
echo "  port:         $PORT"
echo "  gpu_id:       $GPU_ID"
echo "  prompt_prof:  $GTOR_PROMPT_PROFILE"
echo "  max_workers:  $MAX_WORKERS"
echo "  llm_max_tokens: $LLM_MAX_TOKENS"
echo "  gpu_mem_util: $GPU_MEMORY_UTILIZATION"
echo "  max_model_len: $MAX_MODEL_LEN"
echo "  vllm_use_v1:  ${VLLM_USE_V1:-default}"
echo "  managed_id:   $MANAGED_RUN_ID"
echo "  managed_dir:  $MANAGED_DIR"
echo "  compat_out:   $MODEL_OUT"
echo

set +e
MANAGED_CMD=(
python "$MANAGED_RUN_PY" run
  --managed-run-id "$MANAGED_RUN_ID" \
  --label "${RUN_LABEL_PREFIX}_${MODEL_ALIAS//-/_}" \
  --model-key "$MODEL_KEY" \
  --port "$PORT" \
  --gpu-id "$GPU_ID" \
  --data-base "$ACA_DATA_BASE" \
  --taskset "$TASKSET_FILE" \
  --task-limit 20 \
  --methods BaseG BaseCG ITERG AgentG \
  --max-rounds 4 \
  --llm-max-tokens "$LLM_MAX_TOKENS" \
  --qwen-output-constraint auto \
  --gtor-prompt-profile "$GTOR_PROMPT_PROFILE" \
  --watchdog-interval-sec 60 \
  --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
  --max-model-len "$MAX_MODEL_LEN" \
  --parallel \
  --max-workers "$MAX_WORKERS" \
  --debug
)
if [[ -n "$VLLM_USE_V1" ]]; then
  MANAGED_CMD+=(--vllm-use-v1 "$VLLM_USE_V1")
fi
"${MANAGED_CMD[@]}"
MANAGED_EXIT=$?
set -e

mkdir -p "$MODEL_OUT" "$MODEL_OUT/runs" "$MODEL_OUT/logs" "$REPORT_DIR"

if [[ -f "$MANAGED_DIR/final_report.md" ]] && [[ -f "$MANAGED_DIR/artifact_verification.json" ]]; then
  RUN_DIR=$(python -c "import json; print(json.load(open('$MANAGED_DIR/artifact_verification.json'))['run_dir'])")
  RUN_NAME=$(basename "$RUN_DIR")
  ln -sfn "$RUN_DIR" "$MODEL_OUT/runs/$RUN_NAME"

  python - "$MANAGED_DIR" "$MODEL_OUT" "$MODEL_ALIAS" "$PORT" "$MANAGED_EXIT" "$RUN_DIR" "$GTOR_PROMPT_PROFILE" "$MAX_WORKERS" "$LLM_MAX_TOKENS" <<'PY'
import json, sys
from pathlib import Path

managed_dir = Path(sys.argv[1])
model_out = Path(sys.argv[2])
model_alias = sys.argv[3]
port = sys.argv[4]
managed_exit = int(sys.argv[5])
run_dir = sys.argv[6]
gtor_prompt_profile = sys.argv[7]
max_workers = int(sys.argv[8])
llm_max_tokens = int(sys.argv[9])

try:
    final = json.loads((managed_dir / "artifact_verification.json").read_text(encoding="utf-8"))
except Exception:
    final = {}
try:
    status = json.loads((managed_dir / "run_status.json").read_text(encoding="utf-8"))
except Exception:
    status = {}
try:
    service = json.loads((managed_dir / "service_status.json").read_text(encoding="utf-8"))
except Exception:
    service = {}

state = status.get("state", "UNKNOWN")
aca_run_ok = state == "COMPLETE" and managed_exit == 0 and final.get("usable_for_model_quality", False)

payload = {
    "model_alias": model_alias,
    "model_key": model_alias.replace("-", "_"),
    "preferred_port": int(port),
    "actual_port": int(port),
    "gpu_id": 0,
    "env": "managed_pipeline_v0",
    "service_ok": bool(service.get("service_ok", False)),
    "chat_ok": bool(service.get("chat_ok", False)),
    "aca_run_ok": aca_run_ok,
    "stage": state,
    "run_name": Path(run_dir).name,
    "run_dir": run_dir,
    "data_base": "${ACA_DATA_BASE}",
    "taskset_file": str(Path("${TASKSET_FILE}")),
    "notes": f"managed_pipeline_v0 managed_run_id={managed_dir.name}",
    "llm_max_tokens": llm_max_tokens,
    "qwen_output_constraint_mode": "auto",
    "gtor_prompt_profile": gtor_prompt_profile,
    "max_workers": max_workers,
    "managed_run_id": managed_dir.name,
    "managed_dir": str(managed_dir),
}
(model_out / "service_status.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"  compat service_status.json written to {model_out / 'service_status.json'}")
PY

  echo "=== managed probe20 done ==="
  echo "  state: $(python -c "import json; print(json.load(open('$MANAGED_DIR/run_status.json'))['state'])")"
  echo "  usable_for_model_quality: $(python -c "import json; print(json.load(open('$MANAGED_DIR/artifact_verification.json'))['usable_for_model_quality'])")"
  echo "  run_dir: $RUN_DIR"
  echo "  compat_out: $MODEL_OUT"
  exit 0
else
  cat >"$BLOCKER_MD" <<EOF
# probe20 blocker: ${MODEL_ALIAS}

失败阶段：managed_run.py returned ${MANAGED_EXIT}

managed_run_id：${MANAGED_RUN_ID}

日志路径：${MANAGED_DIR}/logs/
EOF
  echo "Managed run failed. See $BLOCKER_MD" >&2
  exit 1
fi
