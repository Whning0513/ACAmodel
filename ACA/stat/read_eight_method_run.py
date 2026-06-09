#!/usr/bin/env python3
"""Read ACA eight-method run directories and emit compact summaries."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


METHODS = ["Base", "BaseC", "ITER", "Agent", "BaseG", "BaseCG", "ITERG", "AgentG"]
COMMON_RESULT_FIELDS = [
    "requested_sample_count",
    "sample_count",
    "valid_sample_count",
    "invalid_sample_count",
    "valid_rate",
    "TCC_exist",
    "TCC",
    "coverage_progress",
    "coverage_hit_but_ac",
    "iterations",
    "stop_reason",
    "first_countercase_round",
]
GENERATOR_FIELDS = [
    "generator_compile_status",
    "seed_count",
]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _safe_load_json(path: Path) -> dict[str, Any]:
    try:
        return _load_json(path)
    except Exception:
        return {}


def _artifact_flags(
    task_dir: Path,
    method: str,
    task_status: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, bool]:
    task_status = task_status or {}
    result = result or {}
    flags = {
        "has_task_status": (task_dir / "task_status.json").exists(),
        "has_result": (task_dir / "result.json").exists(),
        "has_trajectory": (task_dir / "trajectory.jsonl").exists(),
        "has_trace_json": (task_dir / "trace.json").exists(),
        "has_trace_md": (task_dir / "trace.md").exists(),
        "has_prompt": (task_dir / "prompt.txt").exists(),
        "has_raw_response": (task_dir / "raw_response.txt").exists(),
        "has_generator_prompt": (task_dir / "generator_prompt.txt").exists(),
        "has_generator_raw_response": (task_dir / "generator_raw_response.txt").exists(),
        "has_generator_code": (task_dir / "generator_code.py").exists(),
        "has_seed_records": (task_dir / "seed_records.jsonl").exists(),
        "has_generated_cases": (task_dir / "generated_cases.jsonl").exists(),
    }
    if method in {"BaseG", "BaseCG", "ITERG", "AgentG"}:
        flags["artifact_complete"] = all(
            flags[key]
            for key in [
                "has_task_status",
                "has_result",
                "has_trajectory",
                "has_trace_json",
                "has_generator_prompt",
                "has_generator_raw_response",
                "has_generator_code",
                "has_seed_records",
                "has_generated_cases",
            ]
        )
    else:
        direct_parse_failed = (
            str(task_status.get("status")) in {"success", "failed"}
            and str(result.get("terminated_reason") or result.get("stop_reason") or "") == "llm_parse_failed"
        )
        flags["artifact_complete"] = all(
            flags[key]
            for key in [
                "has_task_status",
                "has_result",
                "has_trajectory",
                "has_trace_json",
                "has_prompt",
            ]
        ) and (flags["has_raw_response"] or direct_parse_failed)
    return flags


def _status_bucket(task_status: dict[str, Any], result: dict[str, Any], method: str) -> str:
    terminated_reason = str(result.get("terminated_reason") or "")
    error = str(result.get("error") or "")
    if task_status.get("status") != "success":
        if terminated_reason in {"llm_error", "api_error"}:
            return "llm_error"
        if "validator" in error.lower() or terminated_reason == "SPEC_INVALID":
            return "validator_error"
        if method in {"BaseG", "BaseCG", "ITERG", "AgentG"} and (
            terminated_reason.startswith("generator_")
            or terminated_reason in {"no_inputs_generated"}
        ):
            return "generator_error"
        return "failed"
    if terminated_reason in {"llm_error", "api_error"}:
        return "llm_error"
    if method in {"BaseG", "BaseCG", "ITERG", "AgentG"} and (
        terminated_reason.startswith("generator_")
        or terminated_reason in {"no_inputs_generated"}
    ):
        return "generator_error"
    if terminated_reason == "SPEC_INVALID" or "validator" in error.lower():
        return "validator_error"
    return "success"


def _extract_no_tool_call_count(trace_json: dict[str, Any]) -> Any:
    conversation = trace_json.get("conversation")
    if not isinstance(conversation, list):
        return "NA"
    max_streak = 0
    current = 0
    for item in conversation:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        tool_calls = item.get("tool_calls") or []
        if role == "AIMessage":
            if tool_calls:
                current = 0
            else:
                current += 1
                max_streak = max(max_streak, current)
    return max_streak


def _read_task(method: str, task_dir: Path) -> tuple[dict[str, Any], List[str]]:
    missing: List[str] = []
    task_status = _safe_load_json(task_dir / "task_status.json")
    result = _safe_load_json(task_dir / "result.json")
    trace = _safe_load_json(task_dir / "trace.json")
    flags = _artifact_flags(task_dir, method, task_status, result)

    row: dict[str, Any] = {
        "method": method,
        "candidate_id": task_dir.name,
        "candidate_id_or_submission_id": task_dir.name,
        "task_status": task_status.get("status", "NA"),
        "status_bucket": _status_bucket(task_status, result, method),
        "success": 1 if task_status.get("status") == "success" else 0,
        "failed": 0 if task_status.get("status") == "success" else 1,
        "pid": result.get("pid", task_status.get("pid", "NA")),
        "stop_reason": result.get("stop_reason", "NA"),
        "terminated_reason": result.get("terminated_reason", "NA"),
        "rounds": result.get("iterations", "NA"),
        "first_countercase_round": result.get("first_countercase_round", "NA"),
        "generator_compile_status": result.get("generator_compile_status", "NA"),
        "generator_seed_count": result.get("seed_count", "NA"),
        "no_tool_call_count": _extract_no_tool_call_count(trace),
        "prompt_path": "generator_prompt.txt" if flags["has_generator_prompt"] else ("prompt.txt" if flags["has_prompt"] else "NA"),
        "raw_response_path": "generator_raw_response.txt" if flags["has_generator_raw_response"] else ("raw_response.txt" if flags["has_raw_response"] else "NA"),
        "trajectory_path": "trajectory.jsonl" if flags["has_trajectory"] else "NA",
    }
    for field in COMMON_RESULT_FIELDS:
        value = result.get(field, "NA")
        row[field] = value
        if value == "NA":
            missing.append(field)
    for field in GENERATOR_FIELDS:
        if field == "seed_count":
            value = result.get("seed_count", "NA")
        else:
            value = result.get(field, "NA")
        row[field] = value
        if method in {"BaseG", "BaseCG", "ITERG", "AgentG"} and value == "NA":
            missing.append(field)
    row["artifact_complete"] = flags["artifact_complete"]
    for key, value in flags.items():
        row[key] = value
    row["missing_fields"] = ";".join(sorted(set(missing))) if missing else ""
    return row, missing


def load_run(run_dir: Path) -> tuple[List[dict[str, Any]], Counter]:
    rows: List[dict[str, Any]] = []
    missing_counter: Counter = Counter()
    tasks_root = run_dir / "tasks"
    for method in METHODS:
        method_dir = tasks_root / method
        if not method_dir.exists():
            continue
        for task_dir in sorted(p for p in method_dir.iterdir() if p.is_dir()):
            row, missing = _read_task(method, task_dir)
            rows.append(row)
            missing_counter.update(missing)
    rows.sort(key=lambda item: (item["method"], item["candidate_id"]))
    return rows, missing_counter


def _write_csv(path: Path, rows: List[dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "NA") for key in fieldnames})


def _aggregate_by_method(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    buckets: Dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = buckets.setdefault(
            row["method"],
            {
                "method": row["method"],
                "tasks": 0,
                "success": 0,
                "failed": 0,
                "llm_error": 0,
                "generator_error": 0,
                "validator_error": 0,
                "countercase_tasks": 0,
                "avg_valid_rate": 0.0,
                "avg_TCC": 0.0,
                "avg_coverage_progress": 0.0,
                "artifact_complete_tasks": 0,
            },
        )
        bucket["tasks"] += 1
        bucket["success"] += int(row["status_bucket"] == "success")
        bucket["failed"] += int(row["status_bucket"] == "failed")
        bucket["llm_error"] += int(row["status_bucket"] == "llm_error")
        bucket["generator_error"] += int(row["status_bucket"] == "generator_error")
        bucket["validator_error"] += int(row["status_bucket"] == "validator_error")
        bucket["countercase_tasks"] += int(row.get("TCC_exist") == 1 or row.get("TCC_exist") == 1.0)
        bucket["avg_valid_rate"] += float(row.get("valid_rate") if row.get("valid_rate") != "NA" else 0.0)
        bucket["avg_TCC"] += float(row.get("TCC") if row.get("TCC") != "NA" else 0.0)
        bucket["avg_coverage_progress"] += float(row.get("coverage_progress") if row.get("coverage_progress") != "NA" else 0.0)
        bucket["artifact_complete_tasks"] += int(bool(row.get("artifact_complete")))
    out = []
    for method, bucket in sorted(buckets.items()):
        if bucket["tasks"]:
            bucket["avg_valid_rate"] = round(bucket["avg_valid_rate"] / bucket["tasks"], 4)
            bucket["avg_TCC"] = round(bucket["avg_TCC"] / bucket["tasks"], 4)
            bucket["avg_coverage_progress"] = round(bucket["avg_coverage_progress"] / bucket["tasks"], 4)
        out.append(bucket)
    return out


def _aggregate_failure_modes(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    counter: Dict[Tuple[str, str], int] = defaultdict(int)
    for row in rows:
        counter[(row["method"], str(row.get("terminated_reason", "NA")))] += 1
    return [
        {"method": method, "terminated_reason": reason, "count": count}
        for (method, reason), count in sorted(counter.items())
    ]


def _write_metric_matrix(path: Path, summary_rows: List[dict[str, Any]]) -> None:
    lines = [
        "# Metric Matrix",
        "",
        "| Method | Tasks | Success | LLM Error | Generator Error | Validator Error | Countercase Tasks | Avg Valid Rate | Avg TCC | Avg Coverage Progress | Artifact Complete |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['method']} | {row['tasks']} | {row['success']} | {row['llm_error']} | {row['generator_error']} | {row['validator_error']} | {row['countercase_tasks']} | {row['avg_valid_rate']} | {row['avg_TCC']} | {row['avg_coverage_progress']} | {row['artifact_complete_tasks']}/{row['tasks']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_report(path: Path, run_dir: Path, summary_rows: List[dict[str, Any]], rows: List[dict[str, Any]], missing_counter: Counter) -> None:
    lines = [
        "# Eight-Method Run Reading Report",
        "",
        f"- Run dir: `{run_dir}`",
        f"- Tasks read: `{len(rows)}`",
        "- AgentG should be interpreted as an `implemented_minimal` baseline.",
        "",
        "## Missing Fields",
        "",
    ]
    if missing_counter:
        for field, count in missing_counter.most_common():
            lines.append(f"- `{field}` missing in `{count}` task rows")
    else:
        lines.append("- none")
    lines.extend(["", "## By Method", ""])
    for row in summary_rows:
        lines.append(
            f"- `{row['method']}`: tasks={row['tasks']}, success={row['success']}, countercase_tasks={row['countercase_tasks']}, avg_valid_rate={row['avg_valid_rate']}, avg_TCC={row['avg_TCC']}, artifact_complete={row['artifact_complete_tasks']}/{row['tasks']}"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Direct methods use `prompt.txt` / `raw_response.txt` when available.")
    lines.append("- Generator methods use `generator_prompt.txt` / `generator_raw_response.txt` and generator-specific artifacts instead of direct prompt files.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_run(run_dir: Path, out_dir: Path) -> dict[str, Path]:
    rows, missing_counter = load_run(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = _aggregate_by_method(rows)
    failure_rows = _aggregate_failure_modes(rows)

    task_fields = [
        "method",
        "candidate_id",
        "pid",
        "task_status",
        "status_bucket",
        "requested_sample_count",
        "sample_count",
        "valid_sample_count",
        "invalid_sample_count",
        "valid_rate",
        "TCC_exist",
        "TCC",
        "coverage_progress",
        "coverage_hit_but_ac",
        "rounds",
        "stop_reason",
        "first_countercase_round",
        "generator_compile_status",
        "generator_seed_count",
        "no_tool_call_count",
        "artifact_complete",
        "has_prompt",
        "has_raw_response",
        "has_generator_code",
        "has_seed_records",
        "has_generated_cases",
        "missing_fields",
    ]
    _write_csv(out_dir / "summary_by_task.csv", rows, task_fields)
    _write_csv(out_dir / "summary_by_method.csv", summary_rows, list(summary_rows[0].keys()) if summary_rows else ["method"])
    _write_csv(out_dir / "failure_modes_by_method.csv", failure_rows, ["method", "terminated_reason", "count"])
    _write_metric_matrix(out_dir / "metric_matrix.md", summary_rows)
    _write_report(out_dir / "run_reading_report.md", run_dir, summary_rows, rows, missing_counter)
    return {
        "summary_by_task": out_dir / "summary_by_task.csv",
        "summary_by_method": out_dir / "summary_by_method.csv",
        "failure_modes_by_method": out_dir / "failure_modes_by_method.csv",
        "metric_matrix": out_dir / "metric_matrix.md",
        "run_reading_report": out_dir / "run_reading_report.md",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read ACA eight-method run directory.")
    parser.add_argument("--run-dir", required=True, help="Run directory")
    parser.add_argument("--out-dir", default=None, help="Output directory, defaults to <run-dir>/reading")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir / "reading"
    outputs = read_run(run_dir, out_dir)
    for name, path in outputs.items():
        print(f"{name}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
