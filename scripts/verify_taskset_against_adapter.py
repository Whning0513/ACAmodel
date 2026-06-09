#!/usr/bin/env python3
"""Verify a taskset against the ACA adapter cache.

Loads the adapter runner-ready ndjson for a wa-focused base dir and checks
that every submission_id in the taskset is findable.  Exits 0 only when all
ids are found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL_ACA_ROOT = ROOT / "ACA"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _find_adapter_cache(base_dir: Path) -> Path | None:
    """Look for a pre-existing adapter cache in known locations."""
    candidates: list[Path] = []
    # 1. Base dir itself and its _wa_focused_adapter_cache subdirectory
    for root in [base_dir, base_dir / "_wa_focused_adapter_cache"]:
        if not root.exists():
            continue
        for pattern in ["waFocused_clean_main_runner_ready*.ndjson"]:
            candidates.extend(sorted(root.glob(pattern)))
    # 2. Managed runs from ACA_model
    managed_runs_root = ROOT / "managed_runs"
    if managed_runs_root.exists():
        for run_dir in sorted(managed_runs_root.iterdir(), reverse=True):
            cache = run_dir / "aca_output" / "_wa_focused_adapter_cache" / "waFocused_clean_main_runner_ready.ndjson"
            if cache.exists():
                candidates.append(cache)
                break  # use most recent run's cache
    if not candidates:
        return None
    return candidates[-1]


def _build_adapter_cache(base_dir: Path) -> Path:
    from ACA.tool.wa_focused_adapter import load_wa_focused_submit_problem, iter_clean_main_records

    output_dir = base_dir / "_wa_focused_adapter_cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / "waFocused_clean_main_runner_ready.ndjson"

    submits, problem_map = load_wa_focused_submit_problem(base_dir)
    with cache_path.open("w", encoding="utf-8") as fh:
        for rec in iter_clean_main_records(submits, problem_map):
            out = {k: v for k, v in rec.items() if k not in {"raw_submit", "raw_problem"}}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")
    return cache_path


def verify(taskset_path: Path, base_dir: Path) -> dict:
    taskset_ids: list[str] = [
        line.strip() for line in taskset_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    total = len(taskset_ids)
    duplicates = sorted({sid for sid in taskset_ids if taskset_ids.count(sid) > 1})

    cache = _find_adapter_cache(base_dir)
    if cache is None:
        cache = _build_adapter_cache(base_dir)

    adapter_ids: set[str] = set()
    with cache.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            adapter_ids.add(obj.get("submission_id", obj.get("candidate_id", "")))

    taskset_set = set(taskset_ids)
    found = taskset_set & adapter_ids
    missing = sorted(taskset_set - adapter_ids)
    runnable = sorted(found)  # all found ids can be run

    return {
        "taskset_path": str(taskset_path),
        "base_dir": str(base_dir),
        "adapter_cache": str(cache),
        "total_ids": total,
        "unique_ids": len(taskset_set),
        "duplicate_ids": duplicates,
        "found_ids": len(found),
        "missing_ids": len(missing),
        "missing_list": missing,
        "runnable_ids": len(runnable),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a taskset against the ACA adapter cache.")
    parser.add_argument("taskset", type=Path, help="Path to taskset file (one submission_id per line).")
    parser.add_argument(
        "--wa-focused-base",
        type=Path,
        default=LOCAL_ACA_ROOT / "data" / "waFocusedData_submit_0526_final",
        help="wa-focused data base directory.",
    )
    parser.add_argument("--output", type=Path, default=None, help="Write verification JSON to this path.")
    args = parser.parse_args()

    result = verify(args.taskset, args.wa_focused_base)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result["missing_ids"] > 0:
        print(f"\nFAIL: {result['missing_ids']} ids not found in adapter cache.", file=sys.stderr)
        if result["missing_list"]:
            print(f"First 10 missing: {result['missing_list'][:10]}", file=sys.stderr)
    if result["duplicate_ids"]:
        print(f"FAIL: {len(result['duplicate_ids'])} duplicate ids detected.", file=sys.stderr)

    ok = result["missing_ids"] == 0 and len(result["duplicate_ids"]) == 0
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
