#!/usr/bin/env bash
set -euo pipefail

ROOT="/data/whn/ACA_model"
SCRIPT_DIR="$ROOT/scripts"

GPU_ID="${GPU_ID:-0}"

models=(
  "qwen35-4b"
  "qwen25-coder-7b"
  "qwen35-9b"
)

for model in "${models[@]}"; do
  if ! bash "$SCRIPT_DIR/run_gtor4_probe20_model.sh" "$model" "" "$GPU_ID"; then
    echo "MODEL_FAILED=$model"
  fi
done

python "$SCRIPT_DIR/summarize_gtor4_probe20.py"
