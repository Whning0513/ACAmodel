#!/usr/bin/env python3
"""Build structured quantitative flow audit for probe20 runs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


DEFAULT_SOURCES = [
    {
        "model": "qwen25-coder-7b",
        "managed_run_id": "managed_qwen25_seedclar_probe20_v0",
        "run_dir": "/data/whn/ACA_model/managed_runs/managed_qwen25_seedclar_probe20_v0/aca_output/runs/gtor4_probe20_seedclar_qwen25_coder_7b_managed_v0",
    },
    {
        "model": "qwen35-9b",
        "managed_run_id": "managed_qwen35_seedclar_probe20_v0",
        "run_dir": "/data/whn/ACA_model/managed_runs/managed_qwen35_seedclar_probe20_v0/aca_output/runs/managed_qwen35_seedclar_probe20_v0_aca",
    },
]
DEFAULT_OUTPUT = Path("/data/whn/ACA_model/reports/probe20_7b9b_4method_flow_audit.json")


def build_scan(csv_path: str | Path, model_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(csv_path).open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            method = row["method"]
            candidate_id = row["candidate_id"]
            global_pid = row["global_pid"]
            round_id = int(row["round_id"])
            tier = row["tier"]

            if tier.startswith("T0") or tier.startswith("T1"):
                coarse = "invalid"
            elif tier.startswith("T2") or tier.startswith("T3"):
                coarse = "negative"
            elif tier.startswith("T4") or tier.startswith("T5") or tier.startswith("T6"):
                coarse = "positive"
            else:
                coarse = "unknown"

            rows.append(
                {
                    "model": model_name,
                    "method": method,
                    "candidate_id": candidate_id,
                    "global_pid": global_pid,
                    "round_id": round_id,
                    "tier": tier,
                    "coarse_label": coarse,
                    "seed_count": int(row.get("seed_count", 0)),
                    "compile_error": row.get("compile_error", "False") == "True",
                    "runtime_error_count": int(row.get("runtime_error_count", 0)),
                    "empty_count": int(row.get("empty_count", 0)),
                    "timeout_count": int(row.get("timeout_count", 0)),
                    "invalid_count": int(row.get("invalid_count", 0)),
                    "valid_count": int(row.get("valid_count", 0)),
                    "hit_count": int(row.get("hit_count", 0)),
                    "hit_rate": float(row.get("hit_rate", 0)),
                    "pure_at_16": row.get("Pure@16", "False") == "True",
                    "unique_input_count": int(row.get("unique_input_count", 0)),
                    "unique_hit_count": int(row.get("unique_hit_count", 0)),
                    "duplicate_count": int(row.get("duplicate_count", 0)),
                    "coverage_progress": row.get("coverage_progress", ""),
                    "reward_v1_score": float(row.get("reward_v1_score", 0)),
                    "task_dir": row.get("task_dir", ""),
                    "elapsed_sec": float(row.get("elapsed_sec_task", 0)),
                    "extraction_failed": row.get("extraction_failed", "False") == "True",
                    "generator_path": row.get("generator_path", ""),
                }
            )
    return rows


def aggregate_by_task(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        tasks[(row["model"], row["method"], row["candidate_id"])].append(row)

    result: list[dict[str, Any]] = []
    for (model, method, candidate_id), rounds in tasks.items():
        best = max(rounds, key=lambda row: row["reward_v1_score"])
        latest = max(rounds, key=lambda row: row["round_id"])

        total_valid = sum(row["valid_count"] for row in rounds)
        total_invalid = sum(row["invalid_count"] for row in rounds)
        total_hit = sum(row["hit_count"] for row in rounds)
        total_unique_hit = sum(row["unique_hit_count"] for row in rounds)
        total_seeds = sum(row["seed_count"] for row in rounds)
        total_compile_err = sum(1 for row in rounds if row["compile_error"])
        total_runtime = sum(row["runtime_error_count"] for row in rounds)
        total_empty = sum(row["empty_count"] for row in rounds)
        total_timeout = sum(row["timeout_count"] for row in rounds)
        total_extraction_failed = sum(1 for row in rounds if row["extraction_failed"])

        stop_reasons = []
        if total_compile_err > 0:
            stop_reasons.append("compile_error")
        if total_runtime > 0:
            stop_reasons.append("runtime_error")
        if total_empty > 0:
            stop_reasons.append("empty_output")
        if total_timeout > 0:
            stop_reasons.append("timeout")
        if total_extraction_failed > 0:
            stop_reasons.append("extraction_failed")
        if latest["tier"] in ("T2 valid no-hit", "T3 mixed-hit") and latest["valid_count"] == 16:
            stop_reasons.append("all_valid_no_hit_or_partial")
        if latest["pure_at_16"]:
            stop_reasons.append("pure_at_16_achieved")

        task_dir = best["task_dir"]
        task_root = task_dir.rsplit("/", 1)[0] if "/tasks/" in task_dir else task_dir
        result.append(
            {
                "model": model,
                "method": method,
                "candidate_id": candidate_id,
                "global_pid": rounds[0]["global_pid"],
                "tier": best["tier"],
                "coarse_label": best["coarse_label"],
                "round_count": len(rounds),
                "best_round_tier": best["tier"],
                "best_round_id": best["round_id"],
                "latest_round_tier": latest["tier"],
                "latest_round_id": latest["round_id"],
                "valid_count": total_valid,
                "invalid_count": total_invalid,
                "hit_count": total_hit,
                "unique_hit_count": total_unique_hit,
                "seed_count": total_seeds,
                "stop_reason": "; ".join(stop_reasons) if stop_reasons else "unknown",
                "compile_error": total_compile_err > 0,
                "runtime_error": total_runtime > 0,
                "empty_output": total_empty > 0,
                "timeout": total_timeout > 0,
                "extraction_failed": total_extraction_failed > 0,
                "no_inputs_generated": total_valid == 0 and total_invalid == 0,
                "gen_too_large": False,
                "latency": sum(row["elapsed_sec"] for row in rounds),
                "task_dir": task_root,
                "best_generator_path": best["generator_path"],
                "best_hit_rate": best["hit_rate"],
                "best_reward_score": best["reward_v1_score"],
            }
        )

    return sorted(result, key=lambda item: (item["model"], item["method"], item["candidate_id"]))


def summarize_tasks(tasks: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "invalid": 0,
            "negative": 0,
            "positive": 0,
            "T0": 0,
            "T1": 0,
            "T2": 0,
            "T3": 0,
            "T4": 0,
            "T5": 0,
            "T6": 0,
            "total": 0,
        }
    )

    for task in tasks:
        key = f"{task['model']}__{task['method']}"
        bucket = summary[key]
        bucket[task["coarse_label"]] += 1
        tier_short = str(task["tier"]).split()[0]
        if tier_short in bucket:
            bucket[tier_short] += 1
        bucket["total"] += 1

    return {key: dict(value) for key, value in summary.items()}


def generate_audit(
    *,
    sources: list[dict[str, str]],
    output_path: str | Path,
    scan_date: str | None = None,
) -> dict[str, Any]:
    all_rows: list[dict[str, Any]] = []
    normalized_sources: dict[str, dict[str, str]] = {}

    for source in sources:
        model = source["model"]
        run_dir = Path(source["run_dir"])
        csv_path = run_dir / "reward_v1_table.csv"
        if not csv_path.exists():
            raise FileNotFoundError(f"Missing reward_v1_table.csv: {csv_path}")
        all_rows.extend(build_scan(csv_path, model))
        normalized_sources[model] = {
            "managed_run_id": source.get("managed_run_id", run_dir.name),
            "run_dir": str(run_dir),
        }

    tasks = aggregate_by_task(all_rows)
    payload = {
        "scan_date": scan_date or str(date.today()),
        "sources": normalized_sources,
        "summary": summarize_tasks(tasks),
        "tasks": tasks,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build probe20 flow audit JSON from explicit run dirs.")
    parser.add_argument("--run-dir-7b", help="Run dir containing reward_v1_table.csv for qwen25-coder-7b.")
    parser.add_argument("--run-dir-9b", help="Run dir containing reward_v1_table.csv for qwen35-9b.")
    parser.add_argument("--managed-run-id-7b", help="Optional source label for 7B.")
    parser.add_argument("--managed-run-id-9b", help="Optional source label for 9B.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path.")
    parser.add_argument("--scan-date", help="Override scan date, default=today.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.run_dir_7b or args.run_dir_9b:
        if not (args.run_dir_7b and args.run_dir_9b):
            raise SystemExit("Both --run-dir-7b and --run-dir-9b are required together.")
        sources = [
            {
                "model": "qwen25-coder-7b",
                "managed_run_id": args.managed_run_id_7b or Path(args.run_dir_7b).name,
                "run_dir": args.run_dir_7b,
            },
            {
                "model": "qwen35-9b",
                "managed_run_id": args.managed_run_id_9b or Path(args.run_dir_9b).name,
                "run_dir": args.run_dir_9b,
            },
        ]
    else:
        sources = DEFAULT_SOURCES

    payload = generate_audit(sources=sources, output_path=args.output, scan_date=args.scan_date)
    print(f"Wrote {len(payload['tasks'])} task summaries to {args.output}")

    positives = [task for task in payload["tasks"] if task["coarse_label"] == "positive"]
    if positives:
        print("\n=== POSITIVE CASES ===")
        for task in positives:
            print(
                f"  {task['model']} {task['method']} {task['candidate_id']} "
                f"{task['tier']} (hits={task['hit_count']}, unique={task['unique_hit_count']})"
            )


if __name__ == "__main__":
    main()
