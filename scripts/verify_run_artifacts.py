#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _managed_pipeline import verify_run_artifacts, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify ACA run artifacts before reward analysis.")
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--require-analyzer-outputs", action="store_true")
    args = parser.parse_args()

    verification = verify_run_artifacts(args.run_dir, require_analyzer_outputs=args.require_analyzer_outputs)
    output_path = args.output or (args.run_dir.parent.parent.parent / "artifact_verification.json")
    write_json(output_path, verification)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    raise SystemExit(0 if verification["ok"] else 1)


if __name__ == "__main__":
    main()
