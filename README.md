# ACA Model

ACA Model is a research codebase for studying how language-model agents find faults in competitive-programming submissions. It compares eight test-generation strategies, from single-pass baselines to coverage-guided generators and tool-using feedback agents.

The project focuses on a concrete code-intelligence problem: given a candidate program and a reference implementation, can an agent generate inputs that expose wrong behavior? The repository contains the experiment runner, sandboxed execution and tracing tools, agent implementations, a reproducible task subset, and scripts for running the same study against Qwen models served on local hardware.

## What is implemented

- Eight canonical methods: `Base`, `BaseC`, `ITER`, `Agent`, `BaseG`, `BaseCG`, `ITERG`, and `AgentG`.
- Sandboxed candidate/reference execution with verdicts, trace coverage, and per-case artifacts.
- Task-level parallel scheduling, resumable runs, service health checks, and artifact verification.
- Local OpenAI-compatible model serving workflows for Qwen2.5-Coder and Qwen3.5 through vLLM.
- Metrics and reports for hit rate, validator coverage, iteration behavior, and generator failures.

The current three-model probe and its limitations are recorded in [`reports/gtor4_probe20_three_model_report.md`](reports/gtor4_probe20_three_model_report.md).

## Run an experiment

Use Python 3.11 for the orchestration environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

export LLM_API_BASE=http://127.0.0.1:8000/v1
export LLM_API_KEY=local-vllm
export LLM_MODEL=your-served-model-name

python -m ACA.run_experiment \
  --methods BaseG BaseCG ITERG AgentG \
  --data-base ACA/data/waFocusedData_submit_0526_final \
  --submission-ids "$(paste -sd, tasksets/gtor_probe20_ids.txt)" \
  --output outputs/probe20
```

Model checkpoints and vLLM environments are separate from the Python dependencies above. The repository does not contain model weights.

For a managed run that starts the server, checks its identity, watches the process, and verifies the output, see [`docs/probe20_reusable_ops_runbook.md`](docs/probe20_reusable_ops_runbook.md). Machine setup and portability notes live in [`docs/portability_handoff.md`](docs/portability_handoff.md).

## Repository layout

```text
ACA/        experiment runner, agents, tracing tools, metrics, and task data
scripts/    model serving, managed runs, monitoring, and verification
tasksets/   fixed submission sets used by the reported experiments
reports/    curated experiment summaries and environment checks
docs/       reproducibility and machine handoff guides
tests/      orchestration and artifact-verification tests
```

Generated runs, logs, caches, checkpoints, and model files are excluded through `.gitignore`.

## Verification

Install the development requirements and run:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```
