# ACA_model Archive Scope

This repository is an archive of:

- experiment entry scripts under `scripts/`
- fixed tasksets under `tasksets/`
- human-written reports under `reports/`
- selected compact run summaries under `outputs/`

This repository intentionally excludes:

- vLLM service logs under `logs/`
- PID/runtime state under `run/`
- task-level artifacts under `outputs/**/runs/*/tasks/`
- large adapter caches under `outputs/**/_wa_focused_adapter_cache/`

The goal is to preserve the experiment configuration, summaries, and conclusions
without checking multi-GB generated artifacts into git.
