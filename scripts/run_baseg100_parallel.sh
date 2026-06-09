#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/whn/ACA_model"
SCRIPT_DIR="$ROOT/scripts"
LOG_DIR="$ROOT/outputs/baseg100/launcher_logs"
mkdir -p "$LOG_DIR"

MODEL_A="${MODEL_A:-qwen25-coder-7b}"
MODEL_B="${MODEL_B:-qwen35-9b}"
PORT_A="${PORT_A:-8017}"
PORT_B="${PORT_B:-8029}"
GPU_A="${GPU_A:-1}"
GPU_B="${GPU_B:-2}"

echo "Planned launches (managed pipeline v0):"
echo "  $MODEL_A on GPU $GPU_A port $PORT_A"
echo "  $MODEL_B on GPU $GPU_B port $PORT_B"
echo
bash "$SCRIPT_DIR/gpu_status.sh"
echo

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_A="$LOG_DIR/${MODEL_A//-/_}_${STAMP}.log"
LOG_B="$LOG_DIR/${MODEL_B//-/_}_${STAMP}.log"

(
  bash "$SCRIPT_DIR/run_baseg100_model.sh" "$MODEL_A" "$PORT_A" "$GPU_A"
) >"$LOG_A" 2>&1 &
PID_A=$!

(
  bash "$SCRIPT_DIR/run_baseg100_model.sh" "$MODEL_B" "$PORT_B" "$GPU_B"
) >"$LOG_B" 2>&1 &
PID_B=$!

echo "LAUNCH_A_PID=$PID_A LOG=$LOG_A"
echo "LAUNCH_B_PID=$PID_B LOG=$LOG_B"
echo "Each wrapper delegates to managed_run.py; managed_run_id will appear in the log."
echo "Use 'tail -f' on the launcher logs or monitor_run_progress.py on each run_dir after start."

wait "$PID_A"
STATUS_A=$?
wait "$PID_B"
STATUS_B=$?

echo "STATUS_A=$STATUS_A"
echo "STATUS_B=$STATUS_B"
exit $(( STATUS_A != 0 || STATUS_B != 0 ))
