# ACA_model Portability And Handoff

This document is the handoff note for moving `ACA_model` to another machine or publishing it to GitHub.

## Current Goal

Make this repository as self-contained as practical for:

- downloading
- reading
- rerunning the managed experiment pipeline
- handing off to another person

## What Is Now Vendored Into This Repo

The following external dependency has been copied into this repository under [ACA](/data/whn/Projects/ACA_model/ACA):

- `ACA/__init__.py`
- `ACA/run_experiment.py`
- `ACA/agent/`
- `ACA/tool/`
- `ACA/stat/`
- `ACA/scripts/analyze_generator_reward_v1.py`
- `ACA/data/waFocusedData_submit_0526_final/`

This is the minimum practical subset needed by the current `ACA_model` managed pipeline.

### Vendored dataset

Included:

- [waFocusedData_submit_0526_final.ndjson](/data/whn/Projects/ACA_model/ACA/data/waFocusedData_submit_0526_final/waFocusedData_submit_0526_final.ndjson)
- [waFocusedData_problem_0526_final.ndjson](/data/whn/Projects/ACA_model/ACA/data/waFocusedData_submit_0526_final/waFocusedData_problem_0526_final.ndjson)

Size notes:

- dataset directory: about `117 MB`
- largest single file: about `99,078,945 bytes`

That largest file is still below the GitHub `100 MB` single-file limit, so normal Git push is still possible.

## What Is Still External

This repo is now much more self-contained, but it is still not fully standalone.

These parts are intentionally **not** vendored:

### 1. Model checkpoints

Expected external model paths:

- `/data/LLMs/Qwen2.5-Coder-7B-Instruct`
- `/data/LLMs/Qwen3.5-9B`
- `/data/LLMs/Qwen3.5-4B`

These are too large to commit into this repository.

### 2. vLLM serving environments

Expected external conda environments:

- `ACAvllms124`
- `vllm017_full`

These are machine environments, not repository assets.

### 3. NVIDIA driver / CUDA runtime

The serving layer still assumes a working NVIDIA stack on the target machine.

## Runtime Path Resolution

The main managed pipeline now prefers the vendored local copy:

- local ACA root: `ACA/`
- local default data base:
  `ACA/data/waFocusedData_submit_0526_final`

If the local copy is missing, scripts fall back to the old external path layout.

Patched scripts:

- [scripts/_managed_pipeline.py](/data/whn/Projects/ACA_model/scripts/_managed_pipeline.py)
- [scripts/managed_run.py](/data/whn/Projects/ACA_model/scripts/managed_run.py)
- [scripts/run_gtor4_probe20_model.sh](/data/whn/Projects/ACA_model/scripts/run_gtor4_probe20_model.sh)
- [scripts/run_baseg100_model.sh](/data/whn/Projects/ACA_model/scripts/run_baseg100_model.sh)
- [scripts/verify_taskset_against_adapter.py](/data/whn/Projects/ACA_model/scripts/verify_taskset_against_adapter.py)
- [scripts/qwen35_direct_prompt_probe.py](/data/whn/Projects/ACA_model/scripts/qwen35_direct_prompt_probe.py)

## Git Hygiene

The repository previously contained many large local outputs under:

- `outputs/`
- `managed_runs/`
- generated report folders

These are now ignored in [.gitignore](/data/whn/Projects/ACA_model/.gitignore) so the repository can be pushed without dragging local experiment artifacts along.

Recommended Git policy:

- commit code
- commit docs
- commit tasksets
- commit vendored ACA subset
- commit the small wa-focused text dataset
- do **not** commit local runs, logs, checkpoints, or GPU artifacts

## Python Requirements

Two layers matter here.

### A. Orchestration / ACA pipeline Python

This is the Python environment used for:

- `managed_run.py`
- `ACA.run_experiment`
- analyzer scripts
- audit scripts

Recommended:

- Python `3.11`

Minimal pip requirements are listed in:

- [requirements.txt](/data/whn/Projects/ACA_model/requirements.txt)
- [requirements-dev.txt](/data/whn/Projects/ACA_model/requirements-dev.txt)

Key runtime libraries:

- `openai`
- `httpx`
- `langchain-core`
- `langgraph`
- `typing-extensions`
- `tqdm`

### B. vLLM serving Python

This is separate from the orchestration layer.

Recommended split:

- `qwen25-coder-7b` -> `ACAvllms124`
- `qwen35-9b` / `qwen35-4b` -> `vllm017_full`

Do not force these into one environment unless you revalidate the whole serving stack.

Observed working version matrix:

| Env | Python | torch | transformers | vllm | CUDA runtime |
|---|---|---|---|---|---|
| `ACAvllms124` | `3.11` | `2.6.0+cu124` | `5.2.0` | `0.8.5` | `12.4` |
| `vllm017_full` | `3.11` | `2.10.0+cu128` | `4.57.6` | `0.17.0` | `12.8` |

## Driver / CUDA Recommendations

Validated / observed on the current machine:

- NVIDIA driver: `545.29.06`
- host CUDA capability from `nvidia-smi`: `12.3`
- user-space CUDA toolkit used in one path: `12.4`

Serving notes:

- `ACAvllms124` is the preferred 7B serving env
- `vllm017_full` is the preferred Qwen3.5 serving env
- Qwen3.5 service support depends more on the `vLLM + transformers` combination than on this repo itself

Practical recommendation for handoff:

- Linux
- NVIDIA GPU
- driver compatible with CUDA 12.x
- Python 3.11
- at least one working vLLM environment per model family

## What To Install On A Fresh Machine

### Minimum for code and audits

1. clone repo
2. create Python 3.11 env
3. install [requirements.txt](/data/whn/Projects/ACA_model/requirements.txt)

### Minimum for full experiment execution

1. do the above
2. place model checkpoints somewhere reachable
3. set up serving envs:
   - `ACAvllms124`
   - `vllm017_full`
4. ensure `nvidia-smi`, `ss`, `curl`, and `gpustat` are available

## Recommended Command Flow

### Safe dual-model launcher

```bash
cd /path/to/ACA_model
bash scripts/run_gtor4_probe20_dual_safe.sh
```

### Recommendation only

```bash
cd /path/to/ACA_model
bash scripts/recommend_gtor4_probe20_dual.sh
```

## Honest Limitation

This repo is now:

- self-contained for ACA pipeline code
- self-contained for the main small text dataset
- much easier to move

But it is still **not** self-contained for:

- model weights
- CUDA drivers
- vLLM binary environments

That is the correct boundary. Trying to commit those into this repo would make handoff worse, not better.
