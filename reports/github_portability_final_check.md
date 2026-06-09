# GitHub Portability Final Check

## 1. Repository Root

- `pwd`: `/data/whn/Projects/ACA_model`
- `git rev-parse --show-toplevel`: `/data/whn/Projects/ACA_model`

Final answer:

- repository root = `/data/whn/Projects/ACA_model`
- not `/data/whn/ACA_model`

## 2. Large File Check

### Files larger than 50 MB in working tree

Observed:

- many historical adapter-cache files above `250 MB`
- all are under `managed_runs/` or `outputs/`

These are not acceptable for ordinary GitHub push and must remain ignored / unstaged.

### Files larger than 95 MB in working tree

Observed:

- the same ignored historical cache files above `250 MB`
- vendored dataset main file:
  - `ACA/data/waFocusedData_submit_0526_final/waFocusedData_submit_0526_final.ndjson`
  - `99,078,945 bytes`

### Files larger than 100 MB

Yes, but only in ignored historical run artifacts:

- `managed_runs/.../_wa_focused_adapter_cache/waFocused_clean_main_runner_ready.ndjson`
- `outputs/.../_wa_focused_adapter_cache/waFocused_clean_main_runner_ready.ndjson`

Consequence:

- ordinary GitHub push is safe **only if these files are not staged**
- if they get staged, push will fail

### Largest vendored dataset file

- `ACA/data/waFocusedData_submit_0526_final/waFocusedData_submit_0526_final.ndjson`
- size: `99,078,945 bytes`

Risk note:

- this is under the GitHub `100 MB` limit
- but it is close enough that it should be called out explicitly as a push-risk file

## 3. `.gitignore` Check

Confirmed ignored from [.gitignore](/data/whn/Projects/ACA_model/.gitignore):

- `managed_runs/`
- `outputs/`
- `logs/`
- `run/`
- `tests/__pycache__/`
- `ACA/**/__pycache__/`
- `.pytest_cache/`
- `.venv/`
- `venv/`
- `env/`
- `tmp/`
- `.cache/`
- `models/`
- `checkpoints/`

Important limitation:

- model checkpoints and conda envs are outside the repo root already
- so they are not commit candidates from this repo anyway

## 4. Git Staging Risk

Current `git status --short` shows many tracked historical files under `outputs/` as deleted.

This means:

- `git add -A` would stage those deletions
- that is not the right move for the portability packaging commit

Recommended approach:

- use the whitelist from [github_commit_plan.md](/data/whn/Projects/ACA_model/reports/github_commit_plan.md)
- do not use blanket staging

## 5. White List Summary

Should be committed:

- vendored `ACA/` minimal runtime subset
- vendored `ACA/data/waFocusedData_submit_0526_final/`
- `scripts/`
- `tests/`
- `tasksets/`
- `requirements.txt`
- `requirements-dev.txt`
- `README.md`
- `how_to_use.md`
- `docs/portability_handoff.md`
- `docs/probe20_reusable_ops_runbook.md`
- a small curated report subset

## 6. Validation

### Shell syntax

Ran:

```bash
bash -n scripts/*.sh
```

Result:

- passed

### Python tests

Ran:

```bash
python -m pytest -q
```

Result:

- `29 passed`
- `4 failed`

Failure cause:

- all 4 failures come from `tests/test_report_gtor4_probe20_small_model_minimal.py`
- they fail because the file
  `/data/whn/ACA_model/scripts/report_gtor4_probe20_small_model_minimal.py`
  does not exist

Interpretation:

- this is **not** a GPU / vLLM / runtime dependency issue
- this is **not** a vendored-ACA path issue
- this is a missing local script file referenced by the test

### Repo-local ACA import check

Ran a Python path check with repo root inserted into `sys.path`.

Results:

- `ACA` package directory exists in repo: yes
- `import ACA`: success
- `import ACA.run_experiment`: failed

Failure:

- `ModuleNotFoundError: No module named 'langchain_core'`

Interpretation:

- path wiring is correct
- vendored `ACA/` is being found
- failure is due to missing Python dependency in the current environment
- this is an environment issue, not a repository layout issue

## 7. Remote Status

Ran:

```bash
git remote -v
```

Result:

- no output

Interpretation:

- no Git remote is configured yet
- do not run `git push` until the GitHub repository URL is chosen and added

## 8. Final Portability Judgment

The repository is now substantially more portable:

- ACA runtime code is vendored
- main wa-focused text dataset is vendored
- managed scripts prefer repo-local ACA paths
- heavy run artifacts are ignored

But it is not fully standalone for execution because it still requires external:

- model checkpoints
- vLLM environments
- CUDA / NVIDIA stack

## 9. Pre-Commit Recommendation

Before committing:

1. use the whitelist in [github_commit_plan.md](/data/whn/Projects/ACA_model/reports/github_commit_plan.md)
2. do not use `git add -A`
3. expect push risk from the `99,078,945` byte vendored ndjson
4. expect no push at all until a remote is configured
