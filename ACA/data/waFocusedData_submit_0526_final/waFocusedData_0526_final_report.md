# WA-Focused Dataset Export — alldata_0526_final → waFocusedData_0526_final

- generated_at: 2026-05-26 21:16:37
- wa_focus_version: 0526_final
- source: alldata_submit_0526_final

## Files

| File | Rows | Size | SHA256 |
|------|:----:|:----:|:-------|
| waFocusedData_submit_0526_final.ndjson | 21,623 | 99,020,727 bytes | 41a4cdc604b6e556... |
| waFocusedData_problem_0526_final.ndjson | 1,109 | 22,906,747 bytes | 440e8451064ed48b... |

## Basic Statistics

| Metric | Value |
|--------|:-----:|
| Original submissions | 21,623 |
| After TLE/MLE filter | 21,623 |
| Removed TLE/MLE | 0 |
| Problems | 1,109 |
| Problems with remaining submissions | 1,109 |
| Problems without remaining submissions | 0 |

## Split Statistics

| Split | Kept |
|-------|:----:|
| main | 8,236 |
| easy | 9,608 |
| pending_ref | 31 |
| pending_validator | 163 |
| pending_blind | 2,084 |
| hard_tail | 1,501 |

## Label Statistics

| Category | Count |
|----------|:-----:|
| Original AC | 2,794 |
| Original WA | 18,829 |
| RE → WA | 0 |
| Unknown | 0 |
| Normalized AC (wa_focus_label) | 2,794 |
| Normalized WA (wa_focus_label) | 18,829 |
| Normalized UNKNOWN (wa_focus_label) | 0 |

## Removal Details

| Type | Count |
|------|:-----:|
| TLE removed | 0 |
| MLE removed | 0 |
| TRACE_TLE removed | 0 |
| TRACE_MLE removed | 0 |

### Removed by Field

| Field | Count |
|-------|:-----:|

### Removed by Split

| Split | Count |
|-------|:-----:|

## Validation Results

| Check | Result |
|-------|:------:|
| submit_json_parseable | PASS |
| problem_json_parseable | PASS |
| candidate_id_unique | PASS |
| global_pid_unique | PASS |
| global_pid_coverage | PASS |
| no_tle_mle_remaining | PASS |
| re_mapped_to_wa | PASS |
| original_verdict_preserved | PASS |
| main_blind_hackable_false | PASS |
| easy_blind_hackable_true | PASS |
| pending_reason_nonempty | PASS |
| problem_count_1109 | PASS |

### All checks pass: **YES**

### WA_FOCUS_EXPORT_STATUS = **READY**

## Experiment Runner Design

### Double-Run (default)

```
1. ref_run        — run reference solution → expected_output
2. student_trace_run — run student submission with coverage → actual_output + coverage
3. compare         — compare expected_output vs actual_output
                    → if different: WA
                    → if student RE: normalized label = WA, raw_runtime_status preserved as "RE"
                    → TLE/MLE: filtered at dataset level; unexpected → unexpected_tle_mle
```

**New fields consumed by runner:**
- `normalized_error_type`: AC / WA
- `wa_focus_label`: AC / WA
- `re_mapped_to_wa`: boolean
- `original_error_type`: preserved original error diagnosis

### Four-Run (diagnostic mode)

```
1. ref_run
2. student_trace_run
3. student_time_run        — bare run, record wall time
4. student_memory_run      — bare run, record peak memory
```

Used for trace overhead analysis and performance profiling.

**WA-focused pipeline default: double-run.** Four-run is an opt-in diagnostic mode.

### Verdict Handling

| Student Runtime | Normalized Label | Runner Action |
|:---|:---|:---|
| AC | AC | Pass |
| WA | WA | Report WA (improvement opportunity) |
| RE | WA | Log raw RE, count as WA |
| TLE | (filtered) | Should not appear; if seen → unexpected_tle_mle |
| MLE | (filtered) | Should not appear; if seen → unexpected_tle_mle |
