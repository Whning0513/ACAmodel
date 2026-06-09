#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from tqdm import tqdm
except Exception:  # pragma: no cover - fallback for minimal environments
    tqdm = None

METHOD_WEIGHTS = {
    "BaseG": 1,
    "BaseCG": 1,
    "ITERG": 5,
    "AgentG": 5,
}
ROOT = Path(__file__).resolve().parents[1]


def _run_command(cmd: list[str], timeout_sec: float = 2.0) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return ""
    return proc.stdout.strip()


def _service_status_for_run(run_dir: Path) -> dict[str, Any] | None:
    for parent in [run_dir.parent, run_dir.parent.parent, run_dir.parent.parent.parent]:
        candidate = parent / "service_status.json"
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return None


def _port_alive(port: int | None) -> bool:
    if port is None:
        return False
    try:
        proc = subprocess.run(
            ["bash", "-lc", f"ss -ltn '( sport = :{int(port)} )' | tail -n +2 | grep -q ."],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0


def _find_pidfile(model_alias: str | None, port: int | None) -> Path | None:
    if not model_alias or port is None:
        return None
    pidfile = ROOT / "run" / "vllm" / f"{model_alias}_{int(port)}.pid"
    return pidfile if pidfile.exists() else None


def _pid_alive(pid: int | None) -> bool:
    return bool(pid and Path(f"/proc/{pid}").exists())


def _find_runner_pids(run_name: str) -> list[int]:
    out = _run_command(["pgrep", "-f", f"ACA.run_experiment.*{run_name}"])
    pids: list[int] = []
    for line in out.splitlines():
        line = line.strip()
        if line.isdigit():
            pids.append(int(line))
    return pids


def _load_run_config(run_dir: Path) -> dict[str, Any]:
    config_path = run_dir / "config.json"
    if not config_path.exists():
        return {}
    return json.loads(config_path.read_text(encoding="utf-8"))


def _expected_task_count(config: dict[str, Any], task_root: Path) -> int:
    submission_ids = config.get("submission_ids") or []
    methods = config.get("methods") or []
    if submission_ids and methods:
        return len(submission_ids) * len(methods)
    task_dirs = list(task_root.glob("*/*"))
    return len(task_dirs)


def _method_weights_for(config: dict[str, Any]) -> dict[str, int]:
    methods = config.get("methods") or []
    return {str(method): METHOD_WEIGHTS.get(str(method), 1) for method in methods}


def _weighted_total(config: dict[str, Any], task_root: Path) -> int:
    submission_ids = config.get("submission_ids") or []
    methods = config.get("methods") or []
    if submission_ids and methods:
        return sum(METHOD_WEIGHTS.get(str(method), 1) for method in methods) * len(submission_ids)
    task_dirs = list(task_root.glob("*/*"))
    return sum(METHOD_WEIGHTS.get(path.parent.name, 1) for path in task_dirs)


def _terminal_count(method_status_counts: dict[str, dict[str, int]]) -> int:
    return sum(counts.get("success", 0) + counts.get("failed", 0) for counts in method_status_counts.values())


def _running_count(method_status_counts: dict[str, dict[str, int]]) -> int:
    return sum(counts.get("running", 0) for counts in method_status_counts.values())


def _weighted_done(method_status_counts: dict[str, dict[str, int]]) -> int:
    total = 0
    for method, counts in method_status_counts.items():
        terminal_count = counts.get("success", 0) + counts.get("failed", 0)
        total += terminal_count * METHOD_WEIGHTS.get(method, 1)
    return total


def format_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _estimate_eta_sec(done: int, total: int, elapsed_sec: float) -> float | None:
    if done <= 0 or total <= 0 or done >= total:
        return 0.0 if total > 0 and done >= total else None
    return elapsed_sec * (total - done) / done


def _format_progress_bar(done: int, total: int, elapsed_sec: float, width: int = 30) -> str:
    eta_sec = _estimate_eta_sec(done, total, elapsed_sec)
    if tqdm is not None:
        return tqdm.format_meter(
            n=done,
            total=total if total > 0 else None,
            elapsed=elapsed_sec,
            ncols=80,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
        )
    if total <= 0:
        return f"[{'-' * width}] {done}/? ETA unknown"
    ratio = min(1.0, max(0.0, done / total))
    filled = int(round(width * ratio))
    bar = "#" * filled + "-" * (width - filled)
    return f"[{bar}] {ratio * 100:.1f}% {done}/{total} ETA {format_duration(eta_sec)}"


def collect_progress(run_dir: Path) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    config = _load_run_config(run_dir)
    task_root = run_dir / "tasks"
    status_files = sorted(task_root.glob("*/*/task_status.json"))
    method_status_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    latest_file: Path | None = None
    latest_mtime = -1.0
    for path in status_files:
        try:
            status = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {"status": "unknown"}
        method = path.parent.parent.name
        method_status_counts[method][str(status.get("status", "unknown"))] += 1
        mtime = path.stat().st_mtime
        if mtime > latest_mtime:
            latest_mtime = mtime
            latest_file = path

    service = _service_status_for_run(run_dir)
    actual_port = (service.get("actual_port") or service.get("port")) if service else None
    model_alias = service.get("model_alias") if service else None
    pidfile = _find_pidfile(model_alias, actual_port)
    vllm_pid = None
    if pidfile is not None:
        try:
            raw = pidfile.read_text(encoding="utf-8").strip()
            vllm_pid = int(raw)
        except (OSError, ValueError):
            vllm_pid = None

    runner_pids = _find_runner_pids(run_dir.name)
    start_time = None
    if (run_dir / "config.json").exists():
        start_time = (run_dir / "config.json").stat().st_mtime
    elif run_dir.exists():
        start_time = run_dir.stat().st_mtime
    elapsed_sec = max(0.0, time.time() - start_time) if start_time else 0.0

    expected_task_count = _expected_task_count(config, task_root)
    status_file_count = len(status_files)
    terminal_status_file_count = _terminal_count(method_status_counts)
    running_status_file_count = _running_count(method_status_counts)
    progress_percent = round((terminal_status_file_count / expected_task_count) * 100, 1) if expected_task_count else 0.0
    weighted_done = _weighted_done(method_status_counts)
    weighted_total = _weighted_total(config, task_root)
    weighted_progress_percent = round((weighted_done / weighted_total) * 100, 1) if weighted_total else 0.0
    eta_sec = _estimate_eta_sec(weighted_done, weighted_total, elapsed_sec)

    return {
        "run_dir": str(run_dir),
        "run_name": run_dir.name,
        "expected_task_count": expected_task_count,
        "status_file_count": status_file_count,
        "terminal_status_file_count": terminal_status_file_count,
        "running_status_file_count": running_status_file_count,
        "progress_percent": progress_percent,
        "weighted_done": weighted_done,
        "weighted_total": weighted_total,
        "weighted_progress_percent": weighted_progress_percent,
        "method_weights": _method_weights_for(config),
        "eta_sec": round(eta_sec, 2) if eta_sec is not None else None,
        "eta": format_duration(eta_sec),
        "progress_bar": _format_progress_bar(weighted_done, weighted_total, elapsed_sec),
        "method_status_counts": {k: dict(v) for k, v in sorted(method_status_counts.items())},
        "latest_modified_task": str(latest_file.relative_to(run_dir)) if latest_file else None,
        "elapsed_sec": round(elapsed_sec, 2),
        "elapsed": format_duration(elapsed_sec),
        "service_status_path": str((run_dir.parent.parent / "service_status.json")) if service else None,
        "actual_port": actual_port,
        "vllm_alive": _port_alive(actual_port) or _pid_alive(vllm_pid),
        "vllm_pid": vllm_pid,
        "run_experiment_alive": bool(runner_pids),
        "run_experiment_pids": runner_pids,
    }


def _print_human(progress: dict[str, Any]) -> None:
    print(f"run_dir: {progress['run_dir']}")
    print(f"progress: {progress['progress_bar']}")
    print(f"status files: {progress['status_file_count']} / {progress['expected_task_count']}")
    print(
        "terminal/running: "
        f"{progress['terminal_status_file_count']} terminal, "
        f"{progress['running_status_file_count']} running"
    )
    if progress["weighted_total"]:
        print(
            "weighted progress: "
            f"{progress['weighted_done']} / {progress['weighted_total']} "
            f"({progress['weighted_progress_percent']:.1f}%)"
        )
    print(f"elapsed: {progress['elapsed']}  eta: {progress['eta']}")
    for method, counts in progress["method_status_counts"].items():
        parts = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"{method}: {parts}")
    print(f"latest modified task: {progress['latest_modified_task'] or 'N/A'}")
    print(f"elapsed sec: {progress['elapsed_sec']:.2f}")
    print(f"vLLM alive: {progress['vllm_alive']}")
    print(f"run_experiment alive: {progress['run_experiment_alive']}")
    if progress["actual_port"] is not None:
        print(f"port: {progress['actual_port']}")
    if progress["vllm_pid"] is not None:
        print(f"vllm pid: {progress['vllm_pid']}")
    if progress["run_experiment_pids"]:
        print("run_experiment pids: " + ",".join(str(pid) for pid in progress["run_experiment_pids"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor ACA_model run progress using artifacts and live process checks.")
    parser.add_argument("run_dir", help="Run directory under ACA_model/outputs/.../runs/<run_id>")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of human-readable text.")
    args = parser.parse_args()

    progress = collect_progress(Path(args.run_dir))
    if args.json:
        print(json.dumps(progress, ensure_ascii=False, indent=2))
    else:
        _print_human(progress)


if __name__ == "__main__":
    main()
