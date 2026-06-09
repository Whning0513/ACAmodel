import importlib.util
import json
import time
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "monitor_run_progress.py"
    spec = importlib.util.spec_from_file_location("monitor_run_progress", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_collect_progress_counts_statuses_and_latest_file(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    task_a = run_dir / "tasks" / "BaseG" / "task_a"
    task_b = run_dir / "tasks" / "BaseG" / "task_b"
    task_c = run_dir / "tasks" / "AgentG" / "task_c"
    for task_dir in [task_a, task_b, task_c]:
        task_dir.mkdir(parents=True)

    (run_dir / "config.json").write_text(json.dumps({"methods": ["BaseG", "AgentG"], "submission_ids": ["a", "b"]}), encoding="utf-8")
    (task_a / "task_status.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")
    (task_b / "task_status.json").write_text(json.dumps({"status": "running"}), encoding="utf-8")
    latest_path = task_c / "task_status.json"
    latest_path.write_text(json.dumps({"status": "failed"}), encoding="utf-8")

    progress = module.collect_progress(run_dir)

    assert progress["status_file_count"] == 3
    assert progress["expected_task_count"] == 4
    assert progress["method_status_counts"]["BaseG"]["success"] == 1
    assert progress["method_status_counts"]["BaseG"]["running"] == 1
    assert progress["method_status_counts"]["AgentG"]["failed"] == 1
    assert progress["latest_modified_task"].endswith("AgentG/task_c/task_status.json")
    assert progress["terminal_status_file_count"] == 2
    assert progress["running_status_file_count"] == 1
    assert progress["progress_percent"] == 50.0
    assert progress["weighted_done"] == 6
    assert progress["weighted_total"] == 12
    assert "6/12" in progress["progress_bar"]
    assert progress["eta_sec"] >= 0


def test_collect_progress_detects_dead_service_and_runner_when_missing(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({"methods": ["BaseG"], "submission_ids": ["a"]}), encoding="utf-8")

    progress = module.collect_progress(run_dir)

    assert progress["vllm_alive"] is False
    assert progress["run_experiment_alive"] is False


def test_collect_progress_accepts_managed_service_status_port_key(tmp_path, monkeypatch):
    module = _load_module()
    run_dir = tmp_path / "managed" / "aca_output" / "runs" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps({"methods": ["BaseG"], "submission_ids": ["a"]}), encoding="utf-8")
    service_status = run_dir.parent.parent / "service_status.json"
    service_status.write_text(json.dumps({"port": 8029, "model_alias": "qwen35-9b"}), encoding="utf-8")
    monkeypatch.setattr(module, "_port_alive", lambda port: port == 8029)

    progress = module.collect_progress(run_dir)

    assert progress["actual_port"] == 8029
    assert progress["vllm_alive"] is True


def test_format_duration_uses_compact_human_units():
    module = _load_module()

    assert module.format_duration(None) == "unknown"
    assert module.format_duration(59) == "59s"
    assert module.format_duration(61) == "1m01s"
    assert module.format_duration(3661) == "1h01m"


def test_run_command_times_out_slow_process():
    module = _load_module()

    started = time.time()
    output = module._run_command(["/bin/sh", "-c", "sleep 2; echo done"], timeout_sec=0.1)

    assert output == ""
    assert time.time() - started < 1.0


def test_collect_progress_weights_iter_and_agent_as_slower_methods(tmp_path):
    module = _load_module()
    run_dir = tmp_path / "run"
    methods = ["BaseG", "BaseCG", "ITERG", "AgentG"]
    (run_dir / "config.json").parent.mkdir(parents=True)
    (run_dir / "config.json").write_text(
        json.dumps({"methods": methods, "submission_ids": ["a", "b"]}),
        encoding="utf-8",
    )

    for method in ["BaseG", "ITERG"]:
        task_dir = run_dir / "tasks" / method / "a"
        task_dir.mkdir(parents=True)
        (task_dir / "task_status.json").write_text(json.dumps({"status": "success"}), encoding="utf-8")

    progress = module.collect_progress(run_dir)

    assert progress["weighted_done"] == 6
    assert progress["weighted_total"] == 24
    assert progress["weighted_progress_percent"] == 25.0
    assert progress["method_weights"]["BaseG"] == 1
    assert progress["method_weights"]["ITERG"] == 5
