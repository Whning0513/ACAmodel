#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _resolve_task_dirs(path: Path) -> list[Path]:
    if (path / "trajectory.jsonl").exists() and (path / "result.json").exists():
        return [path]
    task_dirs = sorted(
        task_dir
        for task_dir in path.glob("tasks/*/*")
        if (task_dir / "trajectory.jsonl").exists() and (task_dir / "result.json").exists()
    )
    if task_dirs:
        return task_dirs
    raise FileNotFoundError(f"Could not find a task directory or run directory under {path}")


def _group_by_iteration(events: Iterable[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if "iteration" in event:
            grouped[int(event["iteration"])].append(event)
    return dict(sorted(grouped.items()))


def _deduplicate_by_hash(items: Iterable[dict[str, Any]], *, hit_only: bool = False) -> tuple[int, int]:
    seen: set[str] = set()
    unique = 0
    duplicate = 0
    for item in items:
        if hit_only and not (item.get("valid") and item.get("breakthrough")):
            continue
        key = (
            item.get("input_hash")
            or item.get("input_id")
            or item.get("input_text")
            or item.get("test_input")
            or ""
        )
        if key and key in seen:
            duplicate += 1
            continue
        if key:
            seen.add(key)
        unique += 1
    return unique, duplicate


def _round_generator_path(task_dir: Path, round_id: int) -> str | None:
    round_path = task_dir / f"generator_code_round_{round_id}.py"
    if round_path.exists():
        return str(round_path)
    if round_id == 1:
        fallback = task_dir / "generator_code.py"
        if fallback.exists():
            return str(fallback)
    return None


def _tier_name(
    *,
    compile_error: bool,
    extraction_failed: bool,
    runtime_error_count: int,
    empty_count: int,
    timeout_count: int,
    invalid_count: int,
    hit_count: int,
    seed_count: int,
    unique_hit_count: int,
    coverage_progress: int,
) -> tuple[str, int]:
    pure = seed_count > 0 and hit_count == seed_count
    broken = (
        extraction_failed
        or compile_error
        or runtime_error_count > 0
        or empty_count > 0
        or timeout_count > 0
    )
    if broken:
        return "T0 broken", 0
    if invalid_count > 0:
        return "T1 invalid", 1
    if hit_count == 0:
        return "T2 valid no-hit", 2
    if not pure:
        return "T3 mixed-hit", 3
    if unique_hit_count >= 8 or coverage_progress >= 8:
        return "T6 pure broad family", 6
    if unique_hit_count >= 4:
        return "T5 pure family", 5
    return "T4 pure point", 4


def _reward_score(tier_level: int, hit_count: int, unique_hit_count: int, coverage_progress: int) -> float:
    score = (
        tier_level * 100
        + hit_count
        + min(unique_hit_count, 16) * 0.1
        + coverage_progress * 0.01
    )
    return round(score, 4)


def _analyze_task_dir(task_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result = _load_json(task_dir / "result.json")
    trajectory_events = _load_jsonl(task_dir / "trajectory.jsonl")
    seed_records = _load_jsonl(task_dir / "seed_records.jsonl")
    generated_cases = _load_jsonl(task_dir / "generated_cases.jsonl")

    event_rounds = _group_by_iteration(trajectory_events)
    seed_rounds = _group_by_iteration(seed_records)
    generated_rounds = _group_by_iteration(generated_cases)

    rows: list[dict[str, Any]] = []
    for round_id in sorted(set(event_rounds) | set(seed_rounds) | set(generated_rounds)):
        round_events = event_rounds.get(round_id, [])
        round_seed_records = seed_rounds.get(round_id, [])
        round_generated_cases = generated_rounds.get(round_id, [])

        extraction_event = next((e for e in round_events if e.get("event_type") == "generator_code_extracted"), None)
        compile_event = next((e for e in round_events if e.get("event_type") == "generator_compile"), None)
        generator_runs = [e for e in round_events if e.get("event_type") == "generator_run"]
        sandbox_results = [e for e in round_events if e.get("event_type") == "sandbox_result"]

        compile_error = not bool(compile_event and compile_event.get("compile_ok"))
        extraction_failed = bool(extraction_event and extraction_event.get("extraction_status") != "GENERATOR_OK")
        if extraction_event is None and any(e.get("event_type") == "llm_response" for e in round_events):
            extraction_failed = True

        runtime_error_count = sum(
            1
            for item in generator_runs
            if item.get("generator_status") in {"GEN_RUNTIME_ERROR", "GEN_TOO_LARGE"}
        )
        empty_count = sum(1 for item in generator_runs if item.get("generator_status") == "GEN_EMPTY_OUTPUT")
        timeout_count = sum(
            1
            for item in generator_runs
            if item.get("generator_status") == "GEN_TIMEOUT"
        ) + sum(
            1
            for item in sandbox_results
            if item.get("status") in {"TLE", "TIMEOUT", "TRACE_TLE"}
        )

        seed_count = len(round_seed_records) or len(generator_runs)
        valid_count = sum(1 for item in sandbox_results if item.get("valid") is True)
        invalid_count = sum(1 for item in sandbox_results if item.get("valid") is False)
        hit_count = sum(
            1
            for item in sandbox_results
            if item.get("valid") is True and item.get("breakthrough") is True
        )
        hit_rate = round(hit_count / seed_count, 4) if seed_count else 0.0
        pure_at_16 = seed_count == 16 and hit_count == 16
        unique_input_count, duplicate_count = _deduplicate_by_hash(round_generated_cases)
        unique_hit_count, _ = _deduplicate_by_hash(sandbox_results, hit_only=True)
        coverage_progress = len(
            {
                line
                for item in sandbox_results
                for line in (item.get("newly_covered_targets") or [])
            }
        )

        tier, tier_level = _tier_name(
            compile_error=compile_error,
            extraction_failed=extraction_failed,
            runtime_error_count=runtime_error_count,
            empty_count=empty_count,
            timeout_count=timeout_count,
            invalid_count=invalid_count,
            hit_count=hit_count,
            seed_count=seed_count,
            unique_hit_count=unique_hit_count,
            coverage_progress=coverage_progress,
        )

        row = {
            "method": result.get("method"),
            "candidate_id": result.get("submission_id"),
            "global_pid": result.get("pid"),
            "round_id": round_id,
            "generator_path": _round_generator_path(task_dir, round_id),
            "seed_count": seed_count,
            "compile_error": compile_error,
            "runtime_error_count": runtime_error_count,
            "empty_count": empty_count,
            "timeout_count": timeout_count,
            "invalid_count": invalid_count,
            "valid_count": valid_count,
            "hit_count": hit_count,
            "hit_rate": hit_rate,
            "Pure@16": pure_at_16,
            "unique_input_count": unique_input_count,
            "unique_hit_count": unique_hit_count,
            "duplicate_count": duplicate_count,
            "coverage_progress": coverage_progress,
            "tier": tier,
            "reward_v1_score": _reward_score(tier_level, hit_count, unique_hit_count, coverage_progress),
            "task_dir": str(task_dir),
            "elapsed_sec_task": result.get("elapsed_sec"),
            "extraction_failed": extraction_failed,
        }
        rows.append(row)

    task_summary = {
        "method": result.get("method"),
        "candidate_id": result.get("submission_id"),
        "global_pid": result.get("pid"),
        "task_dir": str(task_dir),
        "elapsed_sec": result.get("elapsed_sec"),
        "round_count": len(rows),
    }
    return rows, task_summary


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown_summary(md_path: Path, payload: dict[str, Any]) -> None:
    rows = []
    with (Path(payload["analyzed_path"]) / "reward_v1_by_round.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    methods_info = payload.get("methods", {})
    lines: list[str] = []
    lines.append("# Reward v1 Summary")
    lines.append("")
    lines.append(f"**Run path:** `{payload['analyzed_path']}`")
    lines.append(f"**Task count:** {payload['task_count']}")
    lines.append(f"**Row count:** {payload['row_count']}")
    lines.append("")

    for method, info in sorted(methods_info.items()):
        lines.append(f"## Method: {method}")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---|")
        lines.append(f"| Round count | {info['round_count']} |")
        lines.append(f"| Task count | {info['task_count']} |")
        lines.append(f"| Invalid rate | {info['invalid_rate']:.4f} |")
        lines.append("")
        lines.append("### Tier Distribution")
        lines.append("")
        lines.append("| Tier | Count | Ratio |")
        lines.append("|---|---|---|")
        tier_dist = info.get("tier_distribution", {})
        for tier_name in ["T0 broken", "T1 invalid", "T2 valid no-hit", "T3 mixed-hit", "T4 pure point", "T5 pure family", "T6 pure broad family"]:
            count = tier_dist.get(tier_name, 0)
            ratio = count / info["task_count"] if info["task_count"] else 0
            lines.append(f"| {tier_name} | {count} | {ratio:.2%} |")
        lines.append("")
        lines.append("### Key Metrics")
        lines.append("")
        lines.append(f"- **Pure@16 task ratio:** {info['Pure@16_task_ratio']:.4f} ({int(info['Pure@16_task_ratio'] * info['task_count'])} tasks)")
        lines.append(f"- **Average hit rate:** {info['average_hit_rate']:.4f}")
        lines.append(f"- **Average unique hit count:** {info['average_unique_hit_count']:.2f}")
        lines.append(f"- **Invalid rate:** {info['invalid_rate']:.4f}")
        lines.append(f"- **Average task latency:** {info['average_task_latency_sec']:.2f}s")
        lines.append(f"- **Total task latency:** {info['total_task_latency_sec']:.1f}s")
        lines.append(f"- **Max task latency:** {info['max_task_latency_sec']:.1f}s")
        lines.append("")

        # T6 tasks
        t6_rows = [r for r in rows if r["tier"] == "T6 pure broad family"]
        if t6_rows:
            lines.append("### T6 Pure Broad Family")
            lines.append("")
            for r in t6_rows:
                lines.append(f"- `{r['candidate_id']}`")
                lines.append(f"  - PID: {r['global_pid']}")
                lines.append(f"  - Hit count: {r['hit_count']}/16, Unique: {r['unique_hit_count']}")
                lines.append(f"  - Score: {r['reward_v1_score']}")
                lines.append(f"  - Generator: `{r.get('generator_path', 'N/A')}`")
            lines.append("")

        # T4/T5 if any
        for tier_label, tier_name in [("T5 pure family", "T5 Pure Family"), ("T4 pure point", "T4 Pure Point")]:
            tier_rows = [r for r in rows if r["tier"] == tier_label]
            if tier_rows:
                lines.append(f"### {tier_name}")
                lines.append("")
                for r in tier_rows:
                    lines.append(f"- `{r['candidate_id']}` | {r['global_pid']} | hit={r['hit_count']}/16 | unique={r['unique_hit_count']} | score={r['reward_v1_score']}")
                lines.append("")

        # T3 high-hit samples
        t3_rows = sorted([r for r in rows if r["tier"] == "T3 mixed-hit"], key=lambda x: x["hit_count"], reverse=True)
        if t3_rows:
            lines.append("### T3 Mixed-Hit (top samples)")
            lines.append("")
            for r in t3_rows[:10]:
                lines.append(f"- `{r['candidate_id']}` | {r['global_pid']} | hit={r['hit_count']}/16 | unique={r['unique_hit_count']} | score={r['reward_v1_score']}")
            lines.append("")

        # Artifact warnings
        no_inputs = sum(1 for r in rows if r.get("seed_count", 0) == 0)
        missing_gen = sum(1 for r in rows if not r.get("generator_path"))
        if no_inputs > 0:
            lines.append(f"**Warning:** {no_inputs} rows have seed_count=0 (no_inputs_generated).")
            lines.append("")
        if missing_gen > 0:
            lines.append(f"**Warning:** {missing_gen} rows have no generator_path.")
            lines.append("")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _method_summary(rows: list[dict[str, Any]], task_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    rows_by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_method[row["method"]].append(row)

    tasks_by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in task_summaries:
        tasks_by_method[item["method"]].append(item)

    summary: dict[str, Any] = {}
    for method, method_rows in sorted(rows_by_method.items()):
        tier_counts = Counter(row["tier"] for row in method_rows)
        task_latest_rows: dict[str, dict[str, Any]] = {}
        for row in method_rows:
            task_latest_rows[row["task_dir"]] = row
        latest_rows = list(task_latest_rows.values())
        summary[method] = {
            "round_count": len(method_rows),
            "task_count": len(tasks_by_method.get(method, [])),
            "invalid_rate": round(mean(row["invalid_count"] > 0 for row in latest_rows), 4) if latest_rows else 0.0,
            "tier_distribution": dict(sorted(tier_counts.items())),
            "Pure@16_task_ratio": round(mean(bool(row["Pure@16"]) for row in latest_rows), 4) if latest_rows else 0.0,
            "average_hit_rate": round(mean(row["hit_rate"] for row in latest_rows), 4) if latest_rows else 0.0,
            "average_unique_hit_count": round(mean(row["unique_hit_count"] for row in latest_rows), 4) if latest_rows else 0.0,
            "average_task_latency_sec": round(mean(item.get("elapsed_sec") or 0.0 for item in tasks_by_method.get(method, [])), 4) if tasks_by_method.get(method) else 0.0,
            "total_task_latency_sec": round(sum(item.get("elapsed_sec") or 0.0 for item in tasks_by_method.get(method, [])), 4) if tasks_by_method.get(method) else 0.0,
            "max_task_latency_sec": round(max((item.get("elapsed_sec") or 0.0 for item in tasks_by_method.get(method, [])), default=0.0), 4),
        }
    return summary


def analyze_path(path: Path) -> dict[str, Any]:
    task_dirs = _resolve_task_dirs(path)
    all_rows: list[dict[str, Any]] = []
    task_summaries: list[dict[str, Any]] = []
    for task_dir in task_dirs:
        rows, task_summary = _analyze_task_dir(task_dir)
        all_rows.extend(rows)
        task_summaries.append(task_summary)

    output_dir = path if task_dirs != [path] else path
    by_round_path = output_dir / "reward_v1_by_round.jsonl"
    summary_path = output_dir / "reward_v1_summary.json"
    table_path = output_dir / "reward_v1_table.csv"
    md_path = output_dir / "reward_v1_summary.md"

    _write_jsonl(by_round_path, all_rows)
    _write_csv(table_path, all_rows)

    payload = {
        "analyzed_path": str(path),
        "task_count": len(task_dirs),
        "row_count": len(all_rows),
        "methods": _method_summary(all_rows, task_summaries),
        "task_summaries": task_summaries,
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown_summary(md_path, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze BaseG/AgentG generator trajectories into reward_v1 summaries.")
    parser.add_argument("path", help="Task directory or run directory to analyze.")
    args = parser.parse_args()

    path = Path(args.path).resolve()
    summary = analyze_path(path)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
