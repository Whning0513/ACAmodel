#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 3 ]]; then
  echo "Usage: bash /data/whn/ACA_model/scripts/run_gtor4_probe20_model.sh <model_alias> [port] [gpu_id]" >&2
  exit 2
fi

MODEL_ALIAS="$1"
PORT_ARG="${2:-}"
GPU_ID="${3:-${GPU_ID:-0}}"

ROOT="/data/whn/ACA_model"
ACA_ROOT="/data/whn/ACA"
TASKSET_FILE="$ROOT/tasksets/gtor_probe20_ids.txt"
OUTPUT_BASE="$ROOT/outputs/gtor4_probe20"
REPORT_DIR="$ROOT/reports"
SCRIPT_DIR="$ROOT/scripts"
DATA_BASE="${ACA_DATA_BASE:-/data/whn/ACA/data/waFocusedData_submit_0526_final}"
LLM_TEMPERATURE="${LLM_TEMPERATURE:-0.2}"
LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-1024}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-8192}"
QWEN_OUTPUT_CONSTRAINT_MODE="${QWEN_OUTPUT_CONSTRAINT_MODE:-auto}"

case "$MODEL_ALIAS" in
  qwen35-4b)
    MODEL_KEY="qwen35_4b"
    PREFERRED_PORT=8024
    RUN_NAME="gtor4_probe20_qwen35_4b_16seed_ctx8192_tok1024_r4"
    ;;
  qwen25-coder-7b)
    MODEL_KEY="qwen25_coder_7b"
    PREFERRED_PORT=8017
    RUN_NAME="gtor4_probe20_qwen25_coder_7b_16seed_ctx8192_tok1024_r4"
    ;;
  qwen35-9b)
    MODEL_KEY="qwen35_9b"
    PREFERRED_PORT=8029
    RUN_NAME="gtor4_probe20_qwen35_9b_16seed_ctx8192_tok1024_r4"
    ;;
  *)
    echo "Unsupported model alias: $MODEL_ALIAS" >&2
    exit 2
    ;;
esac

PORT="${PORT_ARG:-$PREFERRED_PORT}"
MODEL_OUT="$OUTPUT_BASE/$MODEL_KEY"
RUN_DIR="$MODEL_OUT/runs/$RUN_NAME"
LOG_DIR="$MODEL_OUT/logs"
SERVICE_JSON="$MODEL_OUT/service_status.json"
BLOCKER_MD="$REPORT_DIR/probe20_blocker_${MODEL_ALIAS}.md"
RUN_LOG="$LOG_DIR/${RUN_NAME}.log"
ANALYZE_LOG="$LOG_DIR/${RUN_NAME}_analyze.log"
START_LOG="$LOG_DIR/${RUN_NAME}_start.log"
CHECK_LOG="$LOG_DIR/${RUN_NAME}_check.log"

mkdir -p "$OUTPUT_BASE" "$REPORT_DIR" "$MODEL_OUT" "$LOG_DIR"

find_free_port() {
  local port="$1"
  local candidate
  for candidate in "$port" $(seq $((port + 1)) $((port + 30))); do
    if ! ss -ltn "( sport = :$candidate )" | tail -n +2 | grep -q .; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

write_service_json() {
  local service_ok="$1"
  local chat_ok="$2"
  local aca_run_ok="$3"
  local stage="$4"
  local notes="$5"
  python - <<PY
import json
from pathlib import Path
payload = {
    "model_alias": "${MODEL_ALIAS}",
    "model_key": "${MODEL_KEY}",
    "preferred_port": ${PREFERRED_PORT},
    "actual_port": ${PORT},
    "gpu_id": ${GPU_ID},
    "env": "${SELECTED_ENV_NAME:-unknown}",
    "service_ok": bool(${service_ok}),
    "chat_ok": bool(${chat_ok}),
    "aca_run_ok": bool(${aca_run_ok}),
    "stage": "${stage}",
    "run_name": "${RUN_NAME}",
    "run_dir": "${RUN_DIR}",
    "data_base": "${DATA_BASE}",
    "taskset_file": "${TASKSET_FILE}",
    "notes": "${notes}",
    "llm_max_tokens": ${LLM_MAX_TOKENS},
    "qwen_output_constraint_mode": "${QWEN_OUTPUT_CONSTRAINT_MODE}",
}
Path("${SERVICE_JSON}").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
PY
}

write_blocker() {
  local stage="$1"
  local cmd="$2"
  local log_path="$3"
  local error_summary="$4"
  local impact="$5"
  local next_step="$6"
  cat >"$BLOCKER_MD" <<EOF
# probe20 blocker: ${MODEL_ALIAS}

失败阶段：
  ${stage}

命令：
\`\`\`bash
${cmd}
\`\`\`

日志路径：
  ${log_path}

错误摘要：
  ${error_summary}

是否影响其他模型：
  ${impact}

建议下一步：
  ${next_step}
EOF
}

cleanup_service() {
  bash "$SCRIPT_DIR/stop_vllm_server.sh" "$PORT" >/dev/null 2>&1 || true
}

if [[ ! -f "$TASKSET_FILE" ]]; then
  echo "Missing taskset: $TASKSET_FILE" >&2
  exit 1
fi

if [[ ! -d "$DATA_BASE" ]]; then
  echo "Missing data base: $DATA_BASE" >&2
  exit 1
fi

if ss -ltn "( sport = :$PORT )" | tail -n +2 | grep -q .; then
  ALT_PORT="$(find_free_port "$PORT")"
  if [[ -z "$ALT_PORT" ]]; then
    echo "No free port available near $PORT" >&2
    exit 1
  fi
  PORT="$ALT_PORT"
fi

rm -f "$BLOCKER_MD"
NOTE_TEXT=""
if [[ "$PORT" != "$PREFERRED_PORT" ]]; then
  NOTE_TEXT="preferred port ${PREFERRED_PORT} busy; used ${PORT}"
fi

START_CMD="bash $SCRIPT_DIR/start_acavllms_vllm.sh $MODEL_ALIAS $PORT $GPU_ID"
CHECK_CMD="bash $SCRIPT_DIR/check_vllm_server.sh $PORT"
RUN_CMD="python $ACA_ROOT/run_experiment.py --methods BaseG BaseCG ITERG AgentG --data-base $DATA_BASE --submission-ids \$(paste -sd, $TASKSET_FILE) --output $MODEL_OUT --run-id $RUN_NAME --generator-seeds-per-round 16 --max-rounds 4 --llm-model $MODEL_ALIAS --llm-temperature $LLM_TEMPERATURE --llm-max-tokens $LLM_MAX_TOKENS --qwen-output-constraint $QWEN_OUTPUT_CONSTRAINT_MODE --debug"
ANALYZE_CMD="python $ACA_ROOT/scripts/analyze_generator_reward_v1.py $RUN_DIR"

export MAX_MODEL_LEN
if ! bash "$SCRIPT_DIR/start_acavllms_vllm.sh" "$MODEL_ALIAS" "$PORT" "$GPU_ID" >"$START_LOG" 2>&1; then
  write_service_json 0 0 0 "start_vllm" "$NOTE_TEXT"
  write_blocker "start_vllm" "$START_CMD" "$START_LOG" "vLLM failed to start." "No. Other models can continue." "Inspect the start log and the vLLM service log under /data/whn/ACA_model/logs/vllm."
  exit 1
fi

SELECTED_ENV_NAME="$(grep '^CONDA_ENV=' "$START_LOG" | tail -n 1 | cut -d= -f2- || true)"
ENV_REASON="$(grep '^ENV_REASON=' "$START_LOG" | tail -n 1 | cut -d= -f2- || true)"
if [[ -n "$SELECTED_ENV_NAME" ]]; then
  if [[ -n "$NOTE_TEXT" ]]; then
    NOTE_TEXT="${NOTE_TEXT}; "
  fi
  NOTE_TEXT="${NOTE_TEXT}env=${SELECTED_ENV_NAME}"
fi
if [[ -n "$ENV_REASON" ]]; then
  NOTE_TEXT="${NOTE_TEXT} reason=${ENV_REASON}"
fi

if ! bash "$SCRIPT_DIR/check_vllm_server.sh" "$PORT" >"$CHECK_LOG" 2>&1; then
  write_service_json 0 0 0 "check_chat" "$NOTE_TEXT"
  write_blocker "check_chat" "$CHECK_CMD" "$CHECK_LOG" "Server responded but /v1/models or /v1/chat/completions check failed." "No. Other models can continue." "Inspect the health-check log and only proceed after chat completion succeeds."
  cleanup_service
  exit 1
fi

export LLM_API_BASE="http://127.0.0.1:${PORT}/v1"
export LLM_API_KEY="local-vllm"
export LLM_MODEL="$MODEL_ALIAS"
export CHATANYWHERE_API_BASE="$LLM_API_BASE"
export CHATANYWHERE_API_KEY="$LLM_API_KEY"
export CHATANYWHERE_MODEL="$LLM_MODEL"
export PYTHONNOUSERSITE=1
unset ALL_PROXY all_proxy HTTPS_PROXY https_proxy HTTP_PROXY http_proxy

write_service_json 1 1 0 "$([[ -d "$RUN_DIR" ]] && echo "pre_run" || echo "ready")" "$NOTE_TEXT"

(
  cd /data/whn
  if ! python -m ACA.run_experiment \
    --methods BaseG BaseCG ITERG AgentG \
    --data-base "$DATA_BASE" \
    --submission-ids "$(paste -sd, "$TASKSET_FILE")" \
    --output "$MODEL_OUT" \
    --run-id "$RUN_NAME" \
    --generator-seeds-per-round 16 \
    --max-rounds 4 \
    --llm-model "$MODEL_ALIAS" \
    --llm-temperature "$LLM_TEMPERATURE" \
    --llm-max-tokens "$LLM_MAX_TOKENS" \
    --qwen-output-constraint "$QWEN_OUTPUT_CONSTRAINT_MODE" \
    --debug >"$RUN_LOG" 2>&1; then
    exit 1
  fi
)
RUN_STATUS=$?
if [[ "$RUN_STATUS" -ne 0 ]]; then
  write_service_json 1 1 0 "ACA_run" "$NOTE_TEXT"
  write_blocker "ACA_run" "$RUN_CMD" "$RUN_LOG" "ACA runner failed before completing probe20." "No. Other models can continue unless the shared runner is broken." "Inspect the runner log; if this is a shared-code failure, fix it before the next model."
  cleanup_service
  exit 1
fi

(
  cd /data/whn
  if ! python /data/whn/ACA/scripts/analyze_generator_reward_v1.py "$RUN_DIR" >"$ANALYZE_LOG" 2>&1; then
    exit 1
  fi
)
ANALYZE_STATUS=$?
if [[ "$ANALYZE_STATUS" -ne 0 ]]; then
  write_service_json 1 1 0 "reward_analyzer" "$NOTE_TEXT"
  write_blocker "reward_analyzer" "$ANALYZE_CMD" "$ANALYZE_LOG" "reward_v1 analyzer failed." "Yes. This blocks meaningful comparison for later models." "Fix the analyzer or its assumptions before continuing to the next model."
  cleanup_service
  exit 1
fi

python - <<PY
from pathlib import Path
run_dir = Path("${RUN_DIR}")
required_run = [
    "config.json",
    "summary.json",
    "run_matrix.json",
    "failure_modes.json",
    "reward_v1_summary.json",
    "reward_v1_table.csv",
    "reward_v1_by_round.jsonl",
    "reward_v1_summary.md",
]
missing = [name for name in required_run if not (run_dir / name).exists()]
task_dirs = list(run_dir.glob("tasks/*/*"))
for task_dir in task_dirs:
    required_task = [
        "trajectory.jsonl",
        "trace.json",
        "result.json",
        "task_status.json",
        "config.json",
        "seed_records.jsonl",
        "generated_cases.jsonl",
        "generator_compile_status.json",
    ]
    for name in required_task:
        if not (task_dir / name).exists():
            missing.append(str(task_dir / name))
    if not list(task_dir.glob("generator_code_round_*.py")):
        missing.append(str(task_dir / "generator_code_round_*.py"))
if missing:
    print("MISSING_ARTIFACTS")
    for item in missing:
        print(item)
    raise SystemExit(1)
print(f"ARTIFACT_CHECK_OK task_dirs={len(task_dirs)}")
PY
VERIFY_STATUS=$?
if [[ "$VERIFY_STATUS" -ne 0 ]]; then
  write_service_json 1 1 0 "artifact_check" "$NOTE_TEXT"
  write_blocker "artifact_check" "python <inline artifact verifier>" "$RUN_DIR" "Run completed but required artifacts are missing." "Potentially. Fix before trusting comparisons." "Inspect the run directory and backfill the missing artifacts before proceeding."
  cleanup_service
  exit 1
fi

write_service_json 1 1 1 "completed" "$NOTE_TEXT"
cleanup_service
exit 0
