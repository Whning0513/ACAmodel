"""Read-only validator coverage summary for a dataset ndjson."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def _info_from_registry(pid: str, registry: dict) -> dict:
    entry = registry.get(pid)
    if not entry:
        return {"available": False, "status": "missing", "version": None, "path": None, "source": None}
    status = entry.get("status", "draft")
    return {
        "available": status in {"draft", "reviewed"},
        "status": status,
        "version": entry.get("version"),
        "path": entry.get("path"),
        "source": entry.get("source"),
    }


def _load_registry(registry_path: Path) -> dict:
    if not registry_path.exists():
        return {}
    return json.loads(registry_path.read_text(encoding="utf-8"))


def compute_validator_coverage(data_path: Path, validator_root: Path) -> dict:
    submissions = 0
    pids = set()
    pid_to_info = {}
    records_with_info = 0
    with data_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            submissions += 1
            pid = row.get("pid")
            if pid:
                pids.add(pid)
                if isinstance(row.get("validator_info"), dict):
                    pid_to_info[pid] = row["validator_info"]
                    records_with_info += 1

    registry = _load_registry(validator_root / "registry.json")
    status_counter = Counter()
    validator_records = {}
    validator_available_pids = set()
    for pid in sorted(pids):
        info = pid_to_info.get(pid) or _info_from_registry(pid, registry)
        status = info.get("status", "missing")
        status_counter[status] += 1
        if info.get("available"):
            validator_available_pids.add(pid)
        validator_records[pid] = {
            "available": bool(info.get("available")),
            "status": status,
            "version": info.get("version"),
            "path": str((validator_root / info.get("path", "")).resolve()) if info.get("path") else None,
            "source": info.get("source"),
        }

    return {
        "dataset": str(data_path),
        "validator_root": str(validator_root),
        "total_submissions": submissions,
        "unique_pids": len(pids),
        "records_with_validator_info": records_with_info,
        "validator_coverage": {
            "total_submissions": submissions,
            "unique_pids": len(pids),
            "validator_available_pids": len(validator_available_pids),
            "reviewed_pids": status_counter.get("reviewed", 0),
            "draft_pids": status_counter.get("draft", 0),
            "disabled_pids": status_counter.get("disabled", 0),
            "missing_pids": status_counter.get("missing", 0),
        },
        "validators": validator_records,
        "missing_pids": sorted(pid for pid in pids if validator_records[pid]["status"] == "missing"),
        "status_distribution": dict(status_counter),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize validator coverage for an ACA dataset.")
    parser.add_argument("--data", required=True, type=Path, help="Dataset ndjson path")
    parser.add_argument(
        "--validator-root",
        type=Path,
        default=Path("/data/whn/ACA_data/validators"),
        help="Validator asset root containing registry.json",
    )
    args = parser.parse_args()
    report = compute_validator_coverage(args.data, args.validator_root)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
