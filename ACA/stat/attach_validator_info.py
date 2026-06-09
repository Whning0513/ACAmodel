"""Attach validator_info metadata to each dataset record."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ACA.tool.input_validation import get_validator_info_for_pid  # noqa: E402


def attach_validator_info(data_path: Path, out_path: Path) -> dict:
    total = 0
    with out_path.open("w", encoding="utf-8") as out:
        with data_path.open(encoding="utf-8") as f:
            for line in f:
                raw = line.strip()
                if not raw:
                    continue
                record = json.loads(raw)
                patched = dict(record)
                patched["validator_info"] = get_validator_info_for_pid(record.get("pid"))
                out.write(json.dumps(patched, ensure_ascii=False) + "\n")
                total += 1
    return {
        "input": str(data_path),
        "output": str(out_path),
        "records": total,
        "validator_root": os.environ.get("ACA_VALIDATOR_ROOT", ""),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Attach validator_info to ACA dataset ndjson.")
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--validator-root", type=Path, default=None)
    args = parser.parse_args()

    if args.validator_root is not None:
        os.environ["ACA_VALIDATOR_ROOT"] = str(args.validator_root)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = attach_validator_info(args.data, args.out)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
