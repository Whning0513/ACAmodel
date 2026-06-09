#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _managed_pipeline import build_final_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize a managed ACA_model run into final_report.md.")
    parser.add_argument("managed_dir", type=Path)
    args = parser.parse_args()

    report = build_final_report(args.managed_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
