#!/usr/bin/env bash
set -euo pipefail

ROOT="${ACA_MODEL_ROOT:-/data/whn/Projects/ACA_model}"
MAX_WORKERS="${MAX_WORKERS:-2}"
MONITOR_INTERVAL_SEC="${MONITOR_INTERVAL_SEC:-10}"
DEFAULT_GPU_MEMORY_UTILIZATION="${DEFAULT_GPU_MEMORY_UTILIZATION:-0.35}"
GPU_MEMORY_MARGIN_MIB="${GPU_MEMORY_MARGIN_MIB:-3072}"
GPU_7B="${GPU_7B:-auto}"
GPU_9B="${GPU_9B:-auto}"
VLLM_CONDA_ENV="${VLLM_CONDA_ENV:-}"
VLLM_CONDA_ENV_7B="${VLLM_CONDA_ENV_7B:-${VLLM_CONDA_ENV:-ACAvllms124}}"
VLLM_CONDA_ENV_9B="${VLLM_CONDA_ENV_9B:-${VLLM_CONDA_ENV:-vllm017_full}}"

python "$ROOT/scripts/aca_model_supervisor.py" recommend-probe20-dual \
  --root "$ROOT" \
  --gpu-7b "$GPU_7B" \
  --gpu-9b "$GPU_9B" \
  --default-gpu-memory-utilization "$DEFAULT_GPU_MEMORY_UTILIZATION" \
  --gpu-memory-margin-mib "$GPU_MEMORY_MARGIN_MIB" \
  --max-workers "$MAX_WORKERS" \
  --monitor-interval-sec "$MONITOR_INTERVAL_SEC" \
  --vllm-conda-env-7b "$VLLM_CONDA_ENV_7B" \
  --vllm-conda-env-9b "$VLLM_CONDA_ENV_9B"
