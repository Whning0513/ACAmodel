# qwen35-4b BaseG 5-task no-thinking mini-smoke

## Change

A minimal GTOR-only output constraint was added at prompt assembly tail for Qwen models:

`Return only short executable Python code for generator.py, with no reasoning, explanation, Markdown, comments, or copied solution code.`

Applied mode for this rerun:
- `qwen_output_constraint_mode = auto`
- model = `qwen35-4b`
- applied = `true`

Recorded in artifacts:
- task `config.json`
- `trajectory.jsonl` `prompt_built` events
- `method_config_snapshot.json`
- `method_registry_snapshot.json`

## Run Status

- Direct prompt probe: `PASS`
- BaseG 5-task old run: `/data/whn/ACA_model/outputs/qwen35_4b_baseg_5task_no_think/runs/baseg_5task_16seed_no_think`
- BaseG 5-task new run: `/data/whn/ACA_model/outputs/qwen35_4b_baseg_5task_no_think/runs/baseg_5task_16seed_no_think_qwen_constraint_auto`
- 4-method 5-task: `NOT RUN`
- probe20: `NOT RUN`

## Old vs New

| Metric | Old | New |
|---|---:|---:|
| reward_v1 T0 broken | 5 | 5 |
| generator_compile_error | 4 | 2 |
| no_inputs_generated | 1 | 3 |
| extraction_failed | 0 | 0 |
| thinking block in service/direct probe | fixed before run | fixed before run |

## Interpretation

The new tail constraint helped a little, but not enough.

What improved:
- Compile failures dropped from `4` to `2`.
- More tasks now produce syntactically valid generator files.
- Generator extraction is still correct: `GENERATOR_OK` on all 5 tasks.
- No evidence of student-solution mis-extraction.

What did not improve enough:
- reward_v1 tier did not move: still `5/5 = T0 broken`.
- Instead of failing at compile, three tasks now fail later as `no_inputs_generated`.
- Long analysis/comment behavior is reduced on some tasks, but not eliminated.

## Evidence

### No-thinking status
- direct probe remains clean: no `Thinking Process`, no `<think>`.
- run output grep also did not show thinking markers.

### Generator behavior
- `codecontests_incorrect__002576ec6455`
  - old: compile error
  - new: compile error
  - still comment-heavy (`35` lines, `30` comment lines), truncated before executable body
- `codecontests_incorrect__00685e80e643`
  - old: compile error
  - new: compile error
  - still truncated mid-string / mid-return
- `codecontests_incorrect__00375773f01f`
  - old: no inputs generated
  - new: no inputs generated
  - compile now OK, but generator still ends before useful emission path
- `codecontests_incorrect__00379fb3e876`
  - old: compile error
  - new: no inputs generated
  - improvement in syntax only
- `codecontests_incorrect__0073cf0d3bc4`
  - old: compile error
  - new: no inputs generated
  - improvement in syntax only

## Verdict

- `T0` did not decrease.
- Long-form analysis/comment output was partially reduced, but it still consumes too much of the 512-token budget on hard tasks.
- Correct generator extraction is not the blocker.
- The current blocker is now narrower:
  - `qwen35-4b` under BaseG still tends to emit incomplete or non-productive generator programs even with a minimal tail constraint.

## Next Step

Only one next step is justified:
- tighten generator post-processing / execution guard before compile-run, specifically to catch truncated comment-heavy generators and fail them as a prompt-contract issue before broader reruns.
