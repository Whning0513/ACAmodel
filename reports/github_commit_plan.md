# GitHub Commit Plan

## Repository Root

- `pwd`: `/data/whn/Projects/ACA_model`
- `git rev-parse --show-toplevel`: `/data/whn/Projects/ACA_model`

The correct repository root is:

- `/data/whn/Projects/ACA_model`

It is **not**:

- `/data/whn/ACA_model`

## Important Warning

Do **not** use:

```bash
git add -A
```

right now.

Reason:

- this working tree still contains many tracked historical output files under `outputs/`
- they currently show up as `D` in `git status --short`
- `git add -A` would stage those deletions together with the portability packaging work

## GitHub Size Risk

### Files larger than 100 MB in the working tree

These exist under ignored run/output artifacts and are not suitable for ordinary GitHub push:

- multiple `waFocused_clean_main_runner_ready.ndjson` files under `managed_runs/` and `outputs/`
- largest observed sizes:
  - `260766748 bytes`
  - `253422773 bytes`

These must stay ignored and must not be staged.

### Vendored dataset risk

Included vendored dataset file:

- `ACA/data/waFocusedData_submit_0526_final/waFocusedData_submit_0526_final.ndjson`
- size: `99078945 bytes`

This is still below GitHub's `100 MB` hard limit, but it is close enough that it should be treated as a push-risk item.

## Recommended White List

Stage only the portability / packaging files.

### Core vendored ACA subset

- `ACA/__init__.py`
- `ACA/run_experiment.py`
- `ACA/agent/`
- `ACA/tool/`
- `ACA/stat/`
- `ACA/scripts/analyze_generator_reward_v1.py`
- `ACA/data/waFocusedData_submit_0526_final/`

### Experiment and service scripts

- `scripts/_build_flow_audit_scan.py`
- `scripts/_managed_pipeline.py`
- `scripts/aca_model_supervisor.py`
- `scripts/check_vllm_server.sh`
- `scripts/finalize_managed_run.py`
- `scripts/gpu_status.sh`
- `scripts/health_check_vllm.py`
- `scripts/managed_run.py`
- `scripts/monitor_run_progress.py`
- `scripts/qwen35_direct_prompt_probe.py`
- `scripts/recommend_gtor4_probe20_dual.sh`
- `scripts/report_acavllms_versions.sh`
- `scripts/run_baseg100_model.sh`
- `scripts/run_baseg100_parallel.sh`
- `scripts/run_gtor4_probe20_dual_progress.sh`
- `scripts/run_gtor4_probe20_dual_safe.sh`
- `scripts/run_gtor4_probe20_model.sh`
- `scripts/start_acavllms_vllm.sh`
- `scripts/stop_model_by_pid.sh`
- `scripts/stop_vllm_server.sh`
- `scripts/verify_run_artifacts.py`
- `scripts/verify_taskset_against_adapter.py`

### Tests

- `tests/`

### Tasksets

- `tasksets/gtor_probe20_ids.txt`
- `tasksets/baseg100_ids.txt`
- `tasksets/baseg100_ids_current.txt`
- `tasksets/gtor_probe100_0608.txt`
- `tasksets/gtor_smoke5_0608.txt`

### Docs and requirements

- `.gitignore`
- `README.md`
- `how_to_use.md`
- `requirements.txt`
- `requirements-dev.txt`
- `docs/portability_handoff.md`
- `docs/probe20_reusable_ops_runbook.md`

### Small curated reports only

- `reports/github_commit_plan.md`
- `reports/github_portability_final_check.md`
- `reports/probe20_7b9b_status_matrix.csv`
- `reports/probe20_7b9b_status_table.md`

## Suggested `git add` Command

```bash
git add \
  .gitignore \
  README.md \
  how_to_use.md \
  requirements.txt \
  requirements-dev.txt \
  ACA \
  docs/portability_handoff.md \
  docs/probe20_reusable_ops_runbook.md \
  scripts \
  tests \
  tasksets/gtor_probe20_ids.txt \
  tasksets/baseg100_ids.txt \
  tasksets/baseg100_ids_current.txt \
  tasksets/gtor_probe100_0608.txt \
  tasksets/gtor_smoke5_0608.txt \
  reports/github_commit_plan.md \
  reports/github_portability_final_check.md \
  reports/probe20_7b9b_status_matrix.csv \
  reports/probe20_7b9b_status_table.md
```

## Do Not Stage

- `managed_runs/`
- `outputs/`
- `logs/`
- `run/`
- any large adapter cache under historical run folders
- model checkpoints
- conda envs
- tmp/cache directories

## Remote Status

`git remote -v` currently prints nothing.

That means:

- there is currently no configured remote in this repository
- do not run `git push` until the target GitHub remote is explicitly set
