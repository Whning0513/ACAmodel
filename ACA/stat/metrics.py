"""Metrics calculator for countercase-finding evaluation.

Metrics (per submission) — all computed from agent trajectory (dual-run verdicts):
  T_Touched:      any agent-generated input covers at least one original uncovered target
  V_Valid:        proportion of well-formed inputs where student output matches reference (AC)
  B_Broken:       proportion of well-formed inputs where student fails against reference (WA/RE/TLE/OOM)
  A_Asserted:     agent declared target lines unreachable (R-family only)
  F_Fully_Covered:all original uncovered lines covered by at least one agent input
  TCC_exist:      at least one countercase found (WA/RE/TLE/OOM)
  TCC_exist_strict:
                  at least one countercase found that also touched a target line
  TCC_exist_loose:
                  at least one countercase found without touching any target line
  TCC:            proportion of all generated inputs that became countercases
  TCC_Strict:     proportion of all generated inputs that became target-touching countercases
  TCC_Loose:      proportion of all generated inputs that became loose countercases
  ATER:           F_Fully_Covered OR A_Asserted
  invalid_rate:   proportion of agent inputs rejected by reference gate (quality signal)

Usage:
    from ACA.stat.metrics import compute_all_metrics

    metrics = compute_all_metrics(results, submissions)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ACA.agent.shared.trajectory import normalize_input_tokens


@dataclass
class SubmissionMetrics:
    """Submission-level metrics derived from generated cases."""
    submission_id: str
    pid: str
    strategy: str
    source: str
    T_Touched: int               # 0/1
    V_Valid: float               # proportion
    B_Broken: float              # proportion
    A_Asserted: int              # 0/1
    F_Fully_Covered: int         # 0/1
    TCC_exist: int               # 0/1
    TCC_exist_strict: int        # 0/1
    TCC_exist_loose: int         # 0/1
    TCC: float                   # proportion over all generated inputs
    TCC_Strict: float            # proportion over all generated inputs
    TCC_Loose: float             # proportion over all generated inputs
    ATER: int                    # 0/1
    invalid_rate: float          # proportion of agent inputs rejected by ref gate
    spec_invalid_count: int
    spec_invalid_rate: float
    terminated_reason: str
    total_newly_covered: int
    iterations: int
    elapsed_sec: float


def compute_submission_metrics(
    result: dict,
    ac_count: int,
    gt_count: int,
    total_cases: int,
    original_uncovered: List[int],
    final_uncovered: List[int],
) -> SubmissionMetrics:
    """Compute 9 metrics for a single submission result.

    Args:
        result: SubmissionResult.to_dict() output.
        ac_count, gt_count, total_cases: STATIC pre-known case stats
            (from step6 ac_indices/gt_indices).  Kept for reference but
            V_Valid/B_Broken are NOW computed from the agent's actual
            trajectory — these reflect the agent's own generated inputs,
            not the pre-known test suite.
        original_uncovered: initial uncovered_lines.
        final_uncovered: remaining uncovered_lines after agent run.
    """
    # Aggregate from agent's own generated inputs (trajectory), NOT step6 pre-known cases
    covered_union = set()
    traj_ac_count = 0
    traj_wa_count = 0
    traj_re_count = 0
    traj_tle_count = 0
    traj_oom_count = 0
    traj_other_count = 0  # INVALID, UNKNOWN, TRACE_TLE
    spec_invalid_count = 0
    traj_total = 0
    cc_count = 0
    cc_strict_count = 0
    cc_loose_count = 0
    original_target_set = set(original_uncovered)

    seen_inputs: set[str] = set()
    for it in result.get("trajectory", []):
        for cr in it.get("per_case_results", []):
            raw_input = cr.get("test_input")
            input_key = normalize_input_tokens(raw_input) if raw_input else ""
            if input_key:
                if input_key in seen_inputs:
                    continue
                seen_inputs.add(input_key)
            status = cr.get("status", "")
            covered_lines = set(cr.get("covered_lines", []))
            touches_target = bool(covered_lines & original_target_set)
            traj_total += 1
            if status == "AC":
                traj_ac_count += 1
            elif status == "WA":
                traj_wa_count += 1
                cc_count += 1
                cc_strict_count += int(touches_target)
                cc_loose_count += int(not touches_target)
            elif status == "RE":
                traj_re_count += 1
                cc_count += 1
                cc_strict_count += int(touches_target)
                cc_loose_count += int(not touches_target)
            elif status == "TLE":
                traj_tle_count += 1
                cc_count += 1
                cc_strict_count += int(touches_target)
                cc_loose_count += int(not touches_target)
            elif status == "OOM":
                traj_oom_count += 1
                cc_count += 1
                cc_strict_count += int(touches_target)
                cc_loose_count += int(not touches_target)
            elif status == "SPEC_INVALID":
                spec_invalid_count += 1
            else:
                traj_other_count += 1

            for ln in covered_lines:
                covered_union.add(ln)

    # T_Touched: set intersection — any agent-generated input covered at least
    # one line from the original target set (not necessarily all)
    t_touched = 1 if (covered_union & set(original_uncovered)) else 0

    # V_Valid / B_Broken: computed from agent's own trajectory, NOT step6 pre-known stats
    #
    # Denominator = AC + WA + RE + TLE + OOM (inputs that passed the reference gate).
    # INVALID/UNKNOWN/TRACE_TLE are excluded: malformed input, ambiguous
    # reference output, or tracing overhead rather than a real student failure.
    #
    # V_Valid (precision): AC / denominator — how often the student is correct.
    # B_Broken (recall): (WA+RE+TLE+OOM) / denominator — how often the agent found a bug.
    traj_broken_count = traj_wa_count + traj_re_count + traj_tle_count + traj_oom_count
    traj_valid_total = traj_ac_count + traj_broken_count
    if traj_valid_total > 0:
        v_valid = round(traj_ac_count / traj_valid_total, 4)
        b_broken = round(traj_broken_count / traj_valid_total, 4)
    else:
        v_valid = 0.0
        b_broken = 0.0

    # INVALID rate: agent inputs rejected by reference gate / total agent inputs.
    # High rate = agent consistently generates malformed inputs.
    if traj_total > 0:
        invalid_rate = round(traj_other_count / traj_total, 4)
        spec_invalid_rate = round(spec_invalid_count / traj_total, 4)
    else:
        invalid_rate = 0.0
        spec_invalid_rate = 0.0

    # A_Asserted (R-family only): agent explicitly declared targets unreachable
    a_asserted = 1 if result.get("terminated_reason") == "declared_unreachable" else 0

    # F_Fully_Covered: set(original) ⊆ covered_union — all targets hit at least once.
    # Also True if there were no original targets (nothing to cover = trivially covered).
    f_fully_covered = 1 if (not original_uncovered or
                             set(original_uncovered) <= covered_union) else 0

    tcc_exist = 1 if cc_count > 0 else 0
    tcc_exist_strict = 1 if cc_strict_count > 0 else 0
    tcc_exist_loose = 1 if cc_loose_count > 0 else 0

    if traj_total > 0:
        tcc = round(cc_count / traj_total, 4)
        tcc_strict = round(cc_strict_count / traj_total, 4)
        tcc_loose = round(cc_loose_count / traj_total, 4)
    else:
        tcc = 0.0
        tcc_strict = 0.0
        tcc_loose = 0.0

    # ATER: agent terminated effectively — either fully covered OR asserted unreachable
    ater = 1 if (f_fully_covered or a_asserted) else 0

    return SubmissionMetrics(
        submission_id=result["submission_id"],
        pid=result["pid"],
        strategy=result["strategy"],
        source=result["source"],
        T_Touched=t_touched,
        V_Valid=v_valid,
        B_Broken=b_broken,
        A_Asserted=a_asserted,
        F_Fully_Covered=f_fully_covered,
        TCC_exist=tcc_exist,
        TCC_exist_strict=tcc_exist_strict,
        TCC_exist_loose=tcc_exist_loose,
        TCC=tcc,
        TCC_Strict=tcc_strict,
        TCC_Loose=tcc_loose,
        ATER=ater,
        invalid_rate=invalid_rate,
        spec_invalid_count=spec_invalid_count,
        spec_invalid_rate=spec_invalid_rate,
        terminated_reason=result["terminated_reason"],
        total_newly_covered=result["total_newly_covered"],
        iterations=result["iterations"],
        elapsed_sec=result["elapsed_sec"],
    )


def compute_all_metrics(
    results_path: str,
    step6_path: str,
) -> List[SubmissionMetrics]:
    """Load results and step6 data, compute metrics for all submissions."""
    import json

    with open(results_path) as f:
        results = json.load(f)

    # Build lookup from step6
    sid_to_record = {}
    with open(step6_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            sid_to_record[r["submission_id"]] = r

    metrics_list = []
    for result in results:
        sid = result["submission_id"]
        rec = sid_to_record.get(sid, {})
        m = compute_submission_metrics(
            result,
            ac_count=rec.get("ac_count", 0),
            gt_count=rec.get("gt_count", 0),
            total_cases=rec.get("total_cases", 0),
            original_uncovered=rec.get("uncovered_effective_lines", []),
            final_uncovered=result.get("final_uncovered_lines", []),
        )
        metrics_list.append(m)

    return metrics_list


def summarize_metrics(metrics_list: List[SubmissionMetrics]) -> dict:
    """Compute aggregate statistics across all submissions."""
    if not metrics_list:
        return {}

    def _mean(vals):
        return round(sum(vals) / len(vals), 4)

    def _median(vals):
        s = sorted(vals)
        return s[len(s) // 2] if s else 0

    return {
        "count": len(metrics_list),
        "T_Touched": _mean([m.T_Touched for m in metrics_list]),
        "V_Valid_mean": _mean([m.V_Valid for m in metrics_list]),
        "V_Valid_median": _median([m.V_Valid for m in metrics_list]),
        "B_Broken_mean": _mean([m.B_Broken for m in metrics_list]),
        "B_Broken_median": _median([m.B_Broken for m in metrics_list]),
        "A_Asserted": _mean([m.A_Asserted for m in metrics_list]),
        "F_Fully_Covered": _mean([m.F_Fully_Covered for m in metrics_list]),
        "TCC_exist": _mean([m.TCC_exist for m in metrics_list]),
        "TCC_exist_strict": _mean([m.TCC_exist_strict for m in metrics_list]),
        "TCC_exist_loose": _mean([m.TCC_exist_loose for m in metrics_list]),
        "TCC": _mean([m.TCC for m in metrics_list]),
        "TCC_Strict": _mean([m.TCC_Strict for m in metrics_list]),
        "TCC_Loose": _mean([m.TCC_Loose for m in metrics_list]),
        "ATER": _mean([m.ATER for m in metrics_list]),
        "invalid_rate_mean": _mean([m.invalid_rate for m in metrics_list]),
        "spec_invalid_count_mean": _mean([m.spec_invalid_count for m in metrics_list]),
        "spec_invalid_rate_mean": _mean([m.spec_invalid_rate for m in metrics_list]),
        "avg_iterations": _mean([m.iterations for m in metrics_list]),
        "avg_elapsed_sec": _mean([m.elapsed_sec for m in metrics_list]),
    }
