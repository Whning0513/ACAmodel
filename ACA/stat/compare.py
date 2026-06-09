"""Cross-strategy comparison.

Usage:
    python3 -m ACA.stat.compare outputs/R1_20250101 outputs/R1.1_20250101 --step6 data/normal_eval.ndjson
    # or from Python:
    from ACA.stat.compare import compare_strategies
    table = compare_strategies(["outputs/R1", "outputs/R1.1", "outputs/L0"], step6_path="data/normal_eval.ndjson")
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from ACA.stat.metrics import compute_all_metrics, summarize_metrics


def compare_strategies(run_dirs: List[str],
                       step6_path: Optional[str] = None) -> Dict[str, dict]:
    """Compare metrics across strategy run directories.

    Args:
        run_dirs: List of paths to run directories (each containing results.json).
        step6_path: Path to step6_final.ndjson for per-record context.
                    Defaults to ACA/data/step6_final.ndjson if omitted.

    Returns:
        Dict[str, dict] mapping strategy label → aggregate metrics.
    """
    if step6_path is None:
        step6_path = "/data/whn/ACA/data/step6_final.ndjson"

    summaries = {}
    for run_dir in run_dirs:
        results_file = Path(run_dir) / "results.json"
        if not results_file.exists():
            print(f"Warning: {results_file} not found — skipping")
            continue

        metrics_list = compute_all_metrics(str(results_file), step6_path)
        label = Path(run_dir).name
        summaries[label] = summarize_metrics(metrics_list)

    return summaries


def print_comparison_table(summaries: Dict[str, dict]):
    """Print a formatted comparison table."""
    if not summaries:
        print("No data to compare.")
        return

    # Code-to-display abbreviation mapping for the comparison table header
    metrics = [
        "count", "T_Touched", "V_Valid_mean", "B_Broken_mean",
        "F_Fully_Covered", "TCC_exist", "TCC", "TCC_Strict", "ATER",
        "avg_iterations", "avg_elapsed_sec",
    ]
    headers = [
        "Strategy", "N", "T", "V_Valid", "B_Broken",
        "F", "TCC_ex", "TCC", "TCC_S", "ATER", "AvgIter", "AvgTime",
    ]

    print("\n" + "=" * 100)
    print("STRATEGY COMPARISON")
    print("=" * 100)
    header_line = "".join(f"{h:>12}" for h in headers)
    print(header_line)
    print("-" * 100)

    for label, s in summaries.items():
        vals = [
            label[:11],
            s.get("count", 0),
            f"{s.get('T_Touched', 0):.3f}",
            f"{s.get('V_Valid_mean', 0):.3f}",
            f"{s.get('B_Broken_mean', 0):.3f}",
            f"{s.get('F_Fully_Covered', 0):.3f}",
            f"{s.get('TCC_exist', 0):.3f}",
            f"{s.get('TCC', 0):.3f}",
            f"{s.get('TCC_Strict', 0):.3f}",
            f"{s.get('ATER', 0):.3f}",
            f"{s.get('avg_iterations', 0):.1f}",
            f"{s.get('avg_elapsed_sec', 0):.0f}s",
        ]
        print("".join(f"{str(v):>12}" for v in vals))

    print("-" * 100)
    print("T=Touched, V=Valid, B=Broken, F=FullyCovered, ex=exist, S=Strict")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compare ACA strategy run directories.")
    parser.add_argument("run_dirs", nargs="+", help="Run directories containing results.json")
    parser.add_argument(
        "--step6",
        default=None,
        help="Step6/eval ndjson used for per-submission context. Defaults to /data/whn/ACA/data/step6_final.ndjson.",
    )
    args = parser.parse_args()

    summaries = compare_strategies(args.run_dirs, step6_path=args.step6)
    print_comparison_table(summaries)
