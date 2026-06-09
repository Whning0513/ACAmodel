from __future__ import annotations

import importlib.util
import csv
import json
from pathlib import Path


def _load_module():
    script_path = Path("/data/whn/ACA_model/scripts/report_gtor4_probe20_small_model_minimal.py")
    spec = importlib.util.spec_from_file_location("report_gtor4_probe20_small_model_minimal", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_best_row_prefers_highest_tier_then_reward() -> None:
    module = _load_module()
    rows = [
        {"tier": "T2 valid no-hit", "reward_v1_score": "200", "hit_count": "0", "round_id": "1"},
        {"tier": "T4 pure point", "reward_v1_score": "410", "hit_count": "16", "round_id": "1"},
        {"tier": "T4 pure point", "reward_v1_score": "415", "hit_count": "15", "round_id": "2"},
    ]

    best = module.best_row(rows)

    assert best["reward_v1_score"] == "415"
    assert best["round_id"] == "2"


def test_scan_task_flags_detects_seed_loop_commentary_and_gen_too_large(tmp_path: Path) -> None:
    module = _load_module()
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "generator_code.py").write_text(
        "for seed in range(16):\n    print(seed)\n",
        encoding="utf-8",
    )
    (task_dir / "generator_raw_response.txt").write_text(
        "We need to analyze the bug carefully before writing code.\n"
        "The student code likely fails on a boundary case.\n"
        "```python\nprint(1)\n```\n",
        encoding="utf-8",
    )
    _write_json(
        task_dir / "generator_failure_modes.json",
        {"failure_modes": {"GEN_TOO_LARGE": 2}},
    )
    _write_json(
        task_dir / "task_status.json",
        {"status": "failed", "stop_reason": "llm_parse_failed", "elapsed_sec": 9.5},
    )

    flags = module.scan_task_flags(task_dir)

    assert flags["seed_loop"] is True
    assert flags["commentary_heavy"] is True
    assert flags["gen_too_large"] is True
    assert flags["parse_fail"] is True


def test_collect_method_summary_counts_best_rows_and_failures(tmp_path: Path) -> None:
    module = _load_module()
    run_dir = tmp_path / "run"
    task_a = run_dir / "tasks" / "BaseG" / "cand_a"
    task_b = run_dir / "tasks" / "BaseG" / "cand_b"
    task_a.mkdir(parents=True)
    task_b.mkdir(parents=True)
    _write_csv(
        run_dir / "reward_v1_table.csv",
        [
            {
                "method": "BaseG",
                "candidate_id": "cand_a",
                "tier": "T0 broken",
                "reward_v1_score": "0",
                "hit_count": "0",
                "round_id": "1",
                "seed_count": "0",
                "valid_count": "0",
                "empty_count": "1",
                "compile_error": "true",
                "task_dir": str(task_a),
                "hit_rate": "0",
            },
            {
                "method": "BaseG",
                "candidate_id": "cand_a",
                "tier": "T6 pure broad family",
                "reward_v1_score": "616.5",
                "hit_count": "16",
                "round_id": "2",
                "seed_count": "16",
                "valid_count": "16",
                "empty_count": "0",
                "compile_error": "false",
                "task_dir": str(task_a),
                "hit_rate": "1.0",
            },
            {
                "method": "BaseG",
                "candidate_id": "cand_b",
                "tier": "T0 broken",
                "reward_v1_score": "0",
                "hit_count": "0",
                "round_id": "1",
                "seed_count": "0",
                "valid_count": "0",
                "empty_count": "1",
                "compile_error": "true",
                "task_dir": str(task_b),
                "hit_rate": "0",
            },
        ],
    )
    _write_json(task_a / "task_status.json", {"status": "success", "stop_reason": "countercase_found", "elapsed_sec": 5.0})
    _write_json(task_b / "task_status.json", {"status": "failed", "stop_reason": "llm_parse_failed", "elapsed_sec": 7.0})
    _write_json(task_a / "generator_failure_modes.json", {"failure_modes": {}})
    _write_json(task_b / "generator_failure_modes.json", {"failure_modes": {"GEN_TOO_LARGE": 1}})
    (task_a / "generator_code.py").write_text("print(1)\n", encoding="utf-8")
    (task_b / "generator_code.py").write_text("for seed in range(16):\n    pass\n", encoding="utf-8")
    (task_b / "generator_raw_response.txt").write_text(
        "This code attempts to explain the bug in detail before printing code.\n",
        encoding="utf-8",
    )

    summary = module.collect_method_summary(run_dir, "BaseG")

    assert summary["task_count"] == 2
    assert summary["tier_distribution"]["T6 pure broad family"] == 1
    assert summary["tier_distribution"]["T0 broken"] == 1
    assert summary["positive"] == 1
    assert summary["invalid"] == 1
    assert summary["compile_error"] == 1
    assert summary["no_inputs"] == 1
    assert summary["empty_output"] == 1
    assert summary["gen_too_large"] == 1
    assert summary["seed_loop"] == 1
    assert summary["commentary_heavy"] == 1
    assert summary["parse_fail"] == 1
    assert summary["t6"] == 1


def test_render_report_answers_core_questions() -> None:
    module = _load_module()
    comparison = {
        "qwen25-coder-7b": {
            "old": {"BaseG": {"positive": 1, "t6": 1, "seed_loop": 4, "commentary_heavy": 0, "no_inputs": 5, "gen_too_large": 4, "parse_fail": 0, "avg_latency_sec": 10.0, "tier_distribution": {label: 0 for label in module.TIER_LABELS}}},
            "new": {"BaseG": {"positive": 2, "t6": 2, "seed_loop": 1, "commentary_heavy": 0, "no_inputs": 2, "gen_too_large": 1, "parse_fail": 0, "avg_latency_sec": 4.0, "tier_distribution": {label: 0 for label in module.TIER_LABELS}}},
        },
        "qwen35-9b": {
            "old": {"AgentG": {"positive": 3, "t6": 0, "seed_loop": 0, "commentary_heavy": 7, "no_inputs": 6, "gen_too_large": 0, "parse_fail": 8, "avg_latency_sec": 40.0, "tier_distribution": {label: 0 for label in module.TIER_LABELS}}},
            "new": {"AgentG": {"positive": 5, "t6": 1, "seed_loop": 0, "commentary_heavy": 2, "no_inputs": 3, "gen_too_large": 0, "parse_fail": 2, "avg_latency_sec": 20.0, "tier_distribution": {label: 0 for label in module.TIER_LABELS}}},
        },
    }
    for model_payload in comparison.values():
        for probe_payload in model_payload.values():
            for method in module.METHODS:
                probe_payload.setdefault(
                    method,
                    {
                        "positive": 0,
                        "t6": 0,
                        "seed_loop": 0,
                        "commentary_heavy": 0,
                        "no_inputs": 0,
                        "gen_too_large": 0,
                        "parse_fail": 0,
                        "avg_latency_sec": 0.0,
                        "tier_distribution": {label: 0 for label in module.TIER_LABELS},
                    },
                )

    report = module.render_report(comparison)

    assert "Did `small_model_minimal` reduce `for seed in range(16)`?" in report
    assert "Did removing AgentG `seeds` tool parameter help?" in report
    assert "Which of 7B vs 9B is better for next rollout?" in report

