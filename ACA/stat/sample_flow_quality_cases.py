#!/usr/bin/env python3
"""Sample flow-quality cases from an ACA run directory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = REPO_ROOT.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ACA.stat.read_eight_method_run import load_run


METHODS = ["Base", "BaseC", "ITER", "Agent", "BaseG", "BaseCG", "ITERG", "AgentG"]


def _safe_load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _load_first_lines(path: Path, head: int = 8, tail: int = 8) -> str:
    if not path.exists():
        return "not available"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= head + tail:
        return "\n".join(lines)
    return "\n".join(lines[:head] + ["..."] + lines[-tail:])


def _task_dir(run_dir: Path, method: str, candidate_id: str) -> Path:
    return run_dir / "tasks" / method / candidate_id


def _pick(rows: List[dict[str, Any]], predicate) -> Optional[dict[str, Any]]:
    for row in rows:
        if predicate(row):
            return row
    return None


def _category_samples(rows: List[dict[str, Any]]) -> Dict[str, Optional[dict[str, Any]]]:
    return {
        "hack_success": _pick(rows, lambda r: r.get("TCC_exist") == 1),
        "valid_but_no_hack": _pick(rows, lambda r: float(r.get("valid_rate") or 0) > 0 and r.get("TCC_exist") in {0, "0", 0.0}),
        "high_coverage_no_hack": _pick(rows, lambda r: float(r.get("coverage_progress") or 0) > 0 and r.get("TCC_exist") in {0, "0", 0.0}),
        "invalid_heavy": _pick(rows, lambda r: float(r.get("invalid_sample_count") or 0) > 0),
        "llm_or_generator_error": _pick(rows, lambda r: r.get("status_bucket") in {"llm_error", "generator_error"}),
    }


def _sample_reason(category: str) -> str:
    mapping = {
        "hack_success": "contains at least one countercase",
        "valid_but_no_hack": "produced valid samples but no countercase",
        "high_coverage_no_hack": "made coverage progress without converting it into a hack",
        "invalid_heavy": "contains invalid-heavy or validator-fail behavior",
        "llm_or_generator_error": "shows llm_error or generator_error behavior",
    }
    return mapping.get(category, category)


def generate_flow_quality_review(run_dir: Path, out_md: Path) -> Path:
    rows, _ = load_run(run_dir)
    grouped: Dict[str, List[dict[str, Any]]] = {m: [] for m in METHODS}
    for row in rows:
        grouped.setdefault(row["method"], []).append(row)

    lines = [
        "# Flow Quality Review",
        "",
        f"- Run dir: `{run_dir}`",
        "- AgentG should be interpreted as an `implemented_minimal` baseline.",
        "",
    ]

    for method in METHODS:
        lines.append(f"## {method}")
        lines.append("")
        samples = _category_samples(grouped.get(method, []))
        for category, row in samples.items():
            lines.append(f"### {category}")
            lines.append("")
            if row is None:
                lines.append("- not available")
                lines.append("")
                continue
            task_dir = _task_dir(run_dir, method, row["candidate_id"])
            result = _safe_load_json(task_dir / "result.json")
            prompt_path = task_dir / ("generator_prompt.txt" if (task_dir / "generator_prompt.txt").exists() else "prompt.txt")
            raw_path = task_dir / ("generator_raw_response.txt" if (task_dir / "generator_raw_response.txt").exists() else "raw_response.txt")
            lines.extend(
                [
                    f"- candidate_id: `{row['candidate_id']}`",
                    f"- problem_id: `{row.get('pid', 'NA')}`",
                    f"- task_status: `{row.get('task_status', 'NA')}`",
                    f"- status_bucket: `{row.get('status_bucket', 'NA')}`",
                    f"- metrics: `TCC_exist={row.get('TCC_exist', 'NA')}, TCC={row.get('TCC', 'NA')}, valid_rate={row.get('valid_rate', 'NA')}, coverage_progress={row.get('coverage_progress', 'NA')}`",
                    f"- prompt path: `{prompt_path}`",
                    f"- raw response path: `{raw_path}`",
                    f"- trajectory path: `{task_dir / 'trajectory.jsonl'}`",
                    f"- failure mode: `{result.get('terminated_reason', 'NA')}`",
                    f"- why sampled: {_sample_reason(category)}",
                    "",
                    "Prompt excerpt:",
                    "```text",
                    _load_first_lines(prompt_path),
                    "```",
                    "",
                    "Raw response excerpt:",
                    "```text",
                    _load_first_lines(raw_path),
                    "```",
                    "",
                ]
            )
        lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_md


def main() -> int:
    parser = argparse.ArgumentParser(description="Sample flow-quality cases from an ACA run.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()
    out = generate_flow_quality_review(Path(args.run_dir), Path(args.out_md))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
