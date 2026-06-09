from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import _managed_pipeline as mp  # type: ignore


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_detect_contamination_from_api_connection_error_burst(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    task_dir = run_dir / "tasks" / "BaseG" / "cand_a"
    task_dir.mkdir(parents=True)
    (task_dir / "task_status.json").write_text(
        json.dumps({"status": "success", "stop_reason": "generator_extraction_error"}),
        encoding="utf-8",
    )
    lines = []
    for i in range(4):
        lines.append(
            json.dumps(
                {
                    "event_type": "llm_response",
                    "iteration": 1,
                    "raw_response": '{"content": "[LLM API Error] {\\"error_type\\": \\"APIConnectionError\\", \\"message\\": \\"Connection error.\\"}"}',
                    "parse_ok": False,
                    "parse_error": "generator_extraction_error",
                    "timestamp": f"2026-06-07T10:00:0{i}+00:00",
                }
            )
        )
    (task_dir / "trajectory.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")

    contamination = mp.detect_run_contamination(run_dir, api_error_burst_threshold=3)
    assert contamination["contaminated"] is True
    assert contamination["reason"] == "api_connection_error_burst"
    assert contamination["api_connection_error_count"] == 4


def test_verify_artifacts_before_analyzer_allows_missing_reward_outputs(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed"
    run_dir = managed_dir / "aca_output" / "runs" / "demo_run"
    run_dir.mkdir(parents=True)
    _write_json(run_dir / "config.json", {"run_id": "demo_run"})
    _write_json(run_dir / "summary.json", {})
    _write_json(run_dir / "run_matrix.json", {})
    _write_json(run_dir / "failure_modes.json", {})
    task_dir = run_dir / "tasks" / "BaseG" / "cand_a"
    task_dir.mkdir(parents=True)
    _write_json(task_dir / "task_status.json", {"status": "success"})
    _write_json(task_dir / "result.json", {})
    _write_json(task_dir / "trace.json", {})
    _write_json(task_dir / "config.json", {})
    (task_dir / "trajectory.jsonl").write_text("{}", encoding="utf-8")
    verification = mp.verify_run_artifacts(run_dir)
    assert verification["ok"] is True
    assert verification["missing_run_files"] == []
    assert verification["usable_for_model_quality"] is True


def test_finalize_marks_contaminated_run_unusable(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    _write_json(managed_dir / "run_manifest.json", {"managed_run_id": "demo", "model_key": "qwen25-coder-7b"})
    _write_json(managed_dir / "run_status.json", {"state": "SERVICE_CONTAMINATED"})
    _write_json(
        managed_dir / "service_status.json",
        {"service_ok": True, "chat_ok": False, "expected_model_id": "qwen25-coder-7b"},
    )
    _write_json(
        managed_dir / "artifact_verification.json",
        {
            "ok": True,
            "usable_for_model_quality": False,
            "usable_for_prompt_comparison": False,
            "contamination_reason": "api_connection_error_burst",
        },
    )

    report = mp.build_final_report(managed_dir)
    assert report["usable_for_model_quality"] is False
    assert report["usable_for_prompt_comparison"] is False
    assert report["contamination_reason"] == "api_connection_error_burst"


def test_health_check_rejects_model_id_mismatch(tmp_path: Path) -> None:
    script = SCRIPTS_DIR / "health_check_vllm.py"
    models_path = tmp_path / "models.json"
    chat_path = tmp_path / "chat.json"
    models_path.write_text(json.dumps({"data": [{"id": "wrong-model"}]}), encoding="utf-8")
    chat_path.write_text(
        json.dumps({"choices": [{"message": {"content": "OK"}}]}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--models-json",
            str(models_path),
            "--chat-json",
            str(chat_path),
            "--expected-model-id",
            "qwen25-coder-7b",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "MODEL_ID_MATCH=0" in proc.stdout


def test_build_run_command_includes_gtor_prompt_profile() -> None:
    manifest = mp.build_run_manifest(
        managed_run_id="demo",
        model_key="qwen25-coder-7b",
        methods=["BaseG", "AgentG"],
        submission_ids=["a", "b"],
        port=8017,
        gpu_id=1,
        llm_max_tokens=1024,
        max_rounds=4,
        debug=True,
        qwen_output_constraint="auto",
        gtor_prompt_profile="small_model_minimal",
        managed_dir=Path("/tmp/demo_managed"),
        run_id="demo_run",
        parallel=True,
        max_workers=8,
    )

    cmd = mp.build_run_command(manifest)

    assert "--gtor-prompt-profile" in cmd
    idx = cmd.index("--gtor-prompt-profile")
    assert cmd[idx + 1] == "small_model_minimal"


def test_build_run_manifest_allows_gpu_memory_utilization_override() -> None:
    manifest = mp.build_run_manifest(
        managed_run_id="demo",
        model_key="qwen35-9b",
        methods=["BaseG"],
        submission_ids=["a"],
        port=8029,
        gpu_id=2,
        llm_max_tokens=1024,
        max_rounds=4,
        debug=True,
        qwen_output_constraint="auto",
        gtor_prompt_profile="legacy",
        managed_dir=Path("/tmp/demo_managed"),
        run_id="demo_run",
        gpu_memory_utilization=0.22,
    )

    assert manifest["gpu_memory_utilization"] == 0.22


def test_get_model_spec_defaults_to_acavllms124_for_7b(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_CONDA_ENV", raising=False)

    spec = mp.get_model_spec("qwen25-coder-7b")

    assert spec["conda_env"] == "ACAvllms124"


def test_get_model_spec_defaults_to_vllm017_full_for_qwen35_9b(monkeypatch) -> None:
    monkeypatch.delenv("VLLM_CONDA_ENV", raising=False)

    spec = mp.get_model_spec("qwen35-9b")

    assert spec["conda_env"] == "vllm017_full"


def test_get_model_spec_allows_vllm_conda_env_override(monkeypatch) -> None:
    monkeypatch.setenv("VLLM_CONDA_ENV", "vllm017_full")

    spec = mp.get_model_spec("qwen35-9b")

    assert spec["conda_env"] == "vllm017_full"
