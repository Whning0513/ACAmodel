#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: bash /data/whn/ACA_model/scripts/run_baseg100_model.sh <model_alias> [port] [gpu_id]" >&2
  exit 2
fi

MODEL_ALIAS="$1"
PORT_ARG="${2:-}"
GPU_ID="${3:-${GPU_ID:-0}}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRIPT_DIR="$ROOT/scripts"
REPORT_DIR="$ROOT/reports"
OUTPUT_BASE="$ROOT/outputs/baseg100"
DEFAULT_ACA_DATA_BASE="$ROOT/ACA/data/waFocusedData_submit_0526_final"
if [[ ! -d "$DEFAULT_ACA_DATA_BASE" ]]; then
  DEFAULT_ACA_DATA_BASE="/data/whn/ACA/data/waFocusedData_submit_0526_final"
fi
DATA_BASE="${ACA_DATA_BASE:-$DEFAULT_ACA_DATA_BASE}"
TASKSET_FILE="${TASKSET_FILE:-$ROOT/tasksets/baseg100_ids.txt}"
TASK_COUNT="${TASK_COUNT:-100}"
SEED_COUNT="${SEED_COUNT:-16}"
LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-1024}"
LLM_TEMPERATURE="${LLM_TEMPERATURE:-0.2}"
MAX_WORKERS="${MAX_WORKERS:-2}"
QWEN_OUTPUT_CONSTRAINT_MODE="${QWEN_OUTPUT_CONSTRAINT_MODE:-auto}"

case "$MODEL_ALIAS" in
  qwen35-4b)
    MODEL_KEY="qwen35-4b"
    PREFERRED_PORT=8024
    MODEL_DIR_KEY="qwen35_4b"
    ;;
  qwen25-coder-7b)
    MODEL_KEY="qwen25-coder-7b"
    PREFERRED_PORT=8017
    MODEL_DIR_KEY="qwen25_coder_7b"
    ;;
  qwen35-9b)
    MODEL_KEY="qwen35-9b"
    PREFERRED_PORT=8029
    MODEL_DIR_KEY="qwen35_9b"
    ;;
  *)
    echo "Unsupported model alias: $MODEL_ALIAS" >&2
    exit 2
    ;;
esac

PORT="${PORT_ARG:-$PREFERRED_PORT}"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
MANAGED_RUN_ID="baseg100_${MODEL_ALIAS//-/_}_${RUN_STAMP}"
MANAGED_RUN_PY="$SCRIPT_DIR/managed_run.py"
MANAGED_DIR="$ROOT/managed_runs/$MANAGED_RUN_ID"
MODEL_OUT="$OUTPUT_BASE/$MODEL_DIR_KEY"
BLOCKER_MD="$REPORT_DIR/baseg100_blocker_${MODEL_ALIAS}.md"

rm -f "$BLOCKER_MD"
mkdir -p "$(dirname "$TASKSET_FILE")"

ensure_taskset() {
  if [[ -f "$TASKSET_FILE" ]]; then
    return 0
  fi
  python - <<PY
from pathlib import Path
import json

src = Path("${DATA_BASE}") / "waFocusedData_submit_0526_final.ndjson"
target = Path("${TASKSET_FILE}")
task_count = int("${TASK_COUNT}")
submission_ids = []
with src.open(encoding="utf-8") as fh:
    for line in fh:
        obj = json.loads(line)
        sid = obj.get("submission_id")
        if sid:
            submission_ids.append(sid)
submission_ids = sorted(dict.fromkeys(submission_ids))[:task_count]
target.write_text("\\n".join(submission_ids) + "\\n", encoding="utf-8")
print(f"  generated taskset: {target} ({len(submission_ids)} ids)")
PY
}

ensure_taskset

if [[ ! -d "$DATA_BASE" ]]; then
  echo "Missing data base: $DATA_BASE" >&2
  exit 1
fi

echo "=== managed baseg100 wrapper ==="
echo "  model_alias:  $MODEL_ALIAS"
echo "  model_key:    $MODEL_KEY"
echo "  port:         $PORT"
echo "  gpu_id:       $GPU_ID"
echo "  managed_id:   $MANAGED_RUN_ID"
echo "  taskset:      $TASKSET_FILE"
echo "  task_count:   $TASK_COUNT"
echo "  max_workers:  $MAX_WORKERS"
echo

set +e
python "$MANAGED_RUN_PY" run \
  --managed-run-id "$MANAGED_RUN_ID" \
  --label "baseg100_${MODEL_ALIAS//-/_}" \
  --model-key "$MODEL_KEY" \
  --port "$PORT" \
  --gpu-id "$GPU_ID" \
  --data-base "$DATA_BASE" \
  --taskset "$TASKSET_FILE" \
  --task-limit "$TASK_COUNT" \
  --methods BaseG \
  --max-rounds 4 \
  --llm-max-tokens "$LLM_MAX_TOKENS" \
  --qwen-output-constraint "$QWEN_OUTPUT_CONSTRAINT_MODE" \
  --watchdog-interval-sec 60 \
  --parallel \
  --max-workers "$MAX_WORKERS" \
  --debug
MANAGED_EXIT=$?
set -e

mkdir -p "$MODEL_OUT" "$MODEL_OUT/runs" "$MODEL_OUT/logs" "$REPORT_DIR"

if [[ -f "$MANAGED_DIR/final_report.md" ]] && [[ -f "$MANAGED_DIR/artifact_verification.json" ]]; then
  RUN_DIR=$(python -c "import json; print(json.load(open('$MANAGED_DIR/artifact_verification.json'))['run_dir'])")
  RUN_NAME=$(basename "$RUN_DIR")
  ln -sfn "$RUN_DIR" "$MODEL_OUT/runs/$RUN_NAME"

  python - "$MANAGED_DIR" "$MODEL_OUT" "$MODEL_ALIAS" "$PORT" "$MANAGED_EXIT" "$RUN_DIR" "$TASK_COUNT" "$SEED_COUNT" "$LLM_MAX_TOKENS" "$QWEN_OUTPUT_CONSTRAINT_MODE" "$MAX_WORKERS" <<'PY'
import json, sys
from pathlib import Path

managed_dir = Path(sys.argv[1])
model_out = Path(sys.argv[2])
model_alias = sys.argv[3]
port = sys.argv[4]
managed_exit = int(sys.argv[5])
run_dir = sys.argv[6]
task_count = sys.argv[7]
seed_count = sys.argv[8]
llm_max_tokens = sys.argv[9]
qwen_mode = sys.argv[10]
max_workers = sys.argv[11]

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
    "data_base": "${DATA_BASE}",
    "taskset_file": str(Path("${TASKSET_FILE}")),
    "notes": f"managed_pipeline_v0 managed_run_id={managed_dir.name}",
    "method": "BaseG",
    "task_count": int(task_count),
    "seed_count": int(seed_count),
    "llm_max_tokens": int(llm_max_tokens),
    "qwen_output_constraint_mode": qwen_mode,
    "max_workers": int(max_workers),
    "managed_run_id": managed_dir.name,
    "managed_dir": str(managed_dir),
}
(model_out / "service_status.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"  compat service_status.json written to {model_out / 'service_status.json'}")
PY

  echo "=== managed baseg100 done ==="
  echo "  state: $(python -c "import json; print(json.load(open('$MANAGED_DIR/run_status.json'))['state'])")"
  echo "  usable_for_model_quality: $(python -c "import json; print(json.load(open('$MANAGED_DIR/artifact_verification.json'))['usable_for_model_quality'])")"
  echo "  run_dir: $RUN_DIR"
  echo "  compat_out: $MODEL_OUT"
  exit 0
else
  cat >"$BLOCKER_MD" <<EOF
# baseg100 blocker: ${MODEL_ALIAS}

失败阶段：managed_run.py returned ${MANAGED_EXIT}

managed_run_id：${MANAGED_RUN_ID}

日志路径：${MANAGED_DIR}/logs/
EOF
  echo "Managed run failed. See $BLOCKER_MD" >&2
  exit 1
fi
