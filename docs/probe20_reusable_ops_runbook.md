# Probe20 Reusable Ops Runbook

This runbook is the fixed entry for the current `20 tasks * 4 methods * (7B + 9B)` probe20 experiment.

The goal is simple:

- use one stable launcher path
- keep 7B and 9B in their own serving environments
- run models sequentially by default
- keep model-internal parallelism only
- make restart, monitoring, and post-run audit repeatable

## Canonical Workflow

Use this four-step flow:

1. inspect current GPU recommendation
2. launch with the safe wrapper or the printed command
3. watch progress from the built-in monitor
4. build the final audit from the finished run directories

## Stable Defaults

These are the current validated defaults and should be treated as the reusable baseline:

| Model | Conda env | max_model_len | llm_max_tokens | vllm_use_v1 |
|---|---|---:|---:|---:|
| `qwen25-coder-7b` | `ACAvllms124` | `8192` | `2048` | `0` |
| `qwen35-9b` | `vllm017_full` | `8192` | `2048` | unset |

Shared launch defaults:

- `MODEL_RUN_MODE=sequential`
- `MAX_WORKERS=2`
- `CONTINUE_ON_MODEL_FAILURE=1`
- `MONITOR_INTERVAL_SEC=10`

Meaning:

- `sequential`: 7B runs first, then 9B
- `MAX_WORKERS=2`: only method tasks inside one model run in parallel
- `CONTINUE_ON_MODEL_FAILURE=1`: if 7B startup fails, 9B still runs

## One-Key Launch

The simplest reusable entry is:

```bash
cd /data/whn/Projects/ACA_model
bash scripts/run_gtor4_probe20_dual_safe.sh
```

What it does:

- auto-plans GPUs from current free memory
- keeps the stable env split:
  - `7B -> ACAvllms124`
  - `9B -> vllm017_full`
- launches in sequential mode
- shows the progress bar, ETA, task counts, and final diagnosis

Useful overrides:

```bash
GPU_7B=2 GPU_9B=1 bash scripts/run_gtor4_probe20_dual_safe.sh
MAX_WORKERS=1 bash scripts/run_gtor4_probe20_dual_safe.sh
MONITOR_INTERVAL_SEC=15 bash scripts/run_gtor4_probe20_dual_safe.sh
```

## Recommendation-Then-Run

If you want to inspect the recommendation first:

```bash
cd /data/whn/Projects/ACA_model
bash scripts/recommend_gtor4_probe20_dual.sh
```

That prints:

- current GPU snapshot
- recommended GPU and `gpu_memory_utilization`
- one copy-paste command with the stable defaults filled in

## Progress and State Meaning

The launcher monitor shows, per model:

- `state`
- `progress`
- `status files`
- `terminal/running`
- `weighted progress`
- `elapsed`
- `eta`
- `vLLM alive`
- `run_experiment alive`

Read it like this:

- `vLLM alive: True`
  model service process is still alive
- `run_experiment alive: True`
  ACA experiment process is still running
- both `False`
  the run has stopped; then check `state`

Common cases:

- `state: COMPLETE`
  run finished normally
- `state: CHAT_CHECK_FAILED`
  startup failed before ACA really began
- `state: ACA_RUNNING`
  ACA is still running even if `vLLM alive` already turned `False`; wait for final state unless it stalls

## Failure Terms

Use these words consistently in reports and logs:

- `崩溃`: process or pipeline exited unexpectedly
- `无输出`: method produced no usable content
- `错误`: explicit error or exception
- `哑火`: run finished but produced almost no useful success

Do not mix them.

## Known Non-Reusable Setting

The following heavier unified setting was tested and is not currently reusable on this machine:

```text
max_model_len = 16384
llm_max_tokens = 4096
```

Observed result on `2026-06-09`:

- 7B: startup failed with GPU OOM / cache allocation failure
- 9B: startup failed with insufficient free GPU memory

The current reusable default is the aligned middle ground:

```text
max_model_len = 8192
llm_max_tokens = 2048
```

## Output Locations

Main paths:

- launcher logs:
  - `outputs/gtor4_probe20/launcher_logs/`
- managed runs:
  - `managed_runs/`
- compat outputs:
  - `outputs/gtor4_probe20/qwen25_coder_7b/`
  - `outputs/gtor4_probe20/qwen35_9b/`
- reports:
  - `reports/`

## Rebuild the Audit

After both runs finish, rebuild the flow audit with explicit run dirs:

```bash
python scripts/_build_flow_audit_scan.py \
  --run-dir-7b managed_runs/probe20_legacy_qwen25_coder_7b_20260609_154153/aca_output/runs/probe20_legacy_qwen25_coder_7b_20260609_154153_aca \
  --run-dir-9b managed_runs/probe20_legacy_qwen35_9b_20260609_161219/aca_output/runs/probe20_legacy_qwen35_9b_20260609_161219_aca \
  --managed-run-id-7b probe20_legacy_qwen25_coder_7b_20260609_154153 \
  --managed-run-id-9b probe20_legacy_qwen35_9b_20260609_161219 \
  --output reports/probe20_7b9b_4method_flow_audit_fresh_20260609.json \
  --scan-date 2026-06-09
```

Fresh reference audit:

- `reports/probe20_7b9b_4method_flow_audit_fresh_20260609.json`

## Restart Rule

If a previous run stopped halfway:

1. inspect the latest launcher log under `outputs/gtor4_probe20/launcher_logs/`
2. inspect the managed run diagnosis:

```bash
python scripts/aca_model_supervisor.py classify-run managed_runs/<managed_run_id>
```

3. relaunch with the same safe wrapper:

```bash
bash scripts/run_gtor4_probe20_dual_safe.sh
```

This keeps the restart path simple. Do not switch environments or context length casually during a restart.
