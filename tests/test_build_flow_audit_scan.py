import csv
import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "_build_flow_audit_scan.py"
    spec = importlib.util.spec_from_file_location("build_flow_audit_scan", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_reward_table(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "method",
        "candidate_id",
        "global_pid",
        "round_id",
        "generator_path",
        "seed_count",
        "compile_error",
        "runtime_error_count",
        "empty_count",
        "timeout_count",
        "invalid_count",
        "valid_count",
        "hit_count",
        "hit_rate",
        "Pure@16",
        "unique_input_count",
        "unique_hit_count",
        "duplicate_count",
        "coverage_progress",
        "tier",
        "reward_v1_score",
        "task_dir",
        "elapsed_sec_task",
        "extraction_failed",
    ]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def test_generate_audit_from_explicit_run_dirs(tmp_path: Path) -> None:
    module = _load_module()
    run_7b = tmp_path / "run_7b"
    run_9b = tmp_path / "run_9b"

    _write_reward_table(
        run_7b / "reward_v1_table.csv",
        [
            {
                "method": "BaseG",
                "candidate_id": "cand_a",
                "global_pid": "pid_a",
                "round_id": 1,
                "generator_path": str(run_7b / "tasks" / "BaseG" / "cand_a" / "generator_code_round_1.py"),
                "seed_count": 16,
                "compile_error": "False",
                "runtime_error_count": 0,
                "empty_count": 0,
                "timeout_count": 0,
                "invalid_count": 0,
                "valid_count": 16,
                "hit_count": 16,
                "hit_rate": 1.0,
                "Pure@16": "True",
                "unique_input_count": 16,
                "unique_hit_count": 16,
                "duplicate_count": 0,
                "coverage_progress": 1.0,
                "tier": "T6 positive",
                "reward_v1_score": 600.0,
                "task_dir": str(run_7b / "tasks" / "BaseG" / "cand_a"),
                "elapsed_sec_task": 3.0,
                "extraction_failed": "False",
            },
            {
                "method": "AgentG",
                "candidate_id": "cand_b",
                "global_pid": "pid_b",
                "round_id": 1,
                "generator_path": str(run_7b / "tasks" / "AgentG" / "cand_b" / "generator_code_round_1.py"),
                "seed_count": 16,
                "compile_error": "True",
                "runtime_error_count": 0,
                "empty_count": 0,
                "timeout_count": 0,
                "invalid_count": 0,
                "valid_count": 0,
                "hit_count": 0,
                "hit_rate": 0.0,
                "Pure@16": "False",
                "unique_input_count": 0,
                "unique_hit_count": 0,
                "duplicate_count": 0,
                "coverage_progress": 0.0,
                "tier": "T0 broken",
                "reward_v1_score": 0.0,
                "task_dir": str(run_7b / "tasks" / "AgentG" / "cand_b"),
                "elapsed_sec_task": 9.0,
                "extraction_failed": "True",
            },
        ],
    )

    _write_reward_table(
        run_9b / "reward_v1_table.csv",
        [
            {
                "method": "BaseG",
                "candidate_id": "cand_a",
                "global_pid": "pid_a",
                "round_id": 1,
                "generator_path": str(run_9b / "tasks" / "BaseG" / "cand_a" / "generator_code_round_1.py"),
                "seed_count": 16,
                "compile_error": "False",
                "runtime_error_count": 0,
                "empty_count": 0,
                "timeout_count": 0,
                "invalid_count": 0,
                "valid_count": 16,
                "hit_count": 0,
                "hit_rate": 0.0,
                "Pure@16": "False",
                "unique_input_count": 16,
                "unique_hit_count": 0,
                "duplicate_count": 0,
                "coverage_progress": 0.2,
                "tier": "T2 valid no-hit",
                "reward_v1_score": 200.0,
                "task_dir": str(run_9b / "tasks" / "BaseG" / "cand_a"),
                "elapsed_sec_task": 4.0,
                "extraction_failed": "False",
            },
        ],
    )

    output_path = tmp_path / "fresh_audit.json"
    payload = module.generate_audit(
        sources=[
            {"model": "qwen25-coder-7b", "run_dir": str(run_7b), "managed_run_id": "run_7b"},
            {"model": "qwen35-9b", "run_dir": str(run_9b), "managed_run_id": "run_9b"},
        ],
        output_path=output_path,
        scan_date="2026-06-09",
    )

    assert output_path.exists()
    assert payload["scan_date"] == "2026-06-09"
    assert payload["sources"]["qwen25-coder-7b"]["run_dir"] == str(run_7b)
    assert payload["summary"]["qwen25-coder-7b__BaseG"]["positive"] == 1
    assert payload["summary"]["qwen25-coder-7b__AgentG"]["invalid"] == 1
    assert payload["summary"]["qwen35-9b__BaseG"]["negative"] == 1

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(saved["tasks"]) == 3
