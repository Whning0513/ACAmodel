#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from _managed_pipeline import (
    ERROR_STATES,
    MANAGED_ROOT,
    append_jsonl,
    build_final_report,
    build_run_command,
    build_run_manifest,
    collect_watchdog_snapshot,
    detect_run_contamination,
    get_model_spec,
    launch_vllm,
    now_iso,
    preflight_verify_taskset,
    read_json,
    run_analyzer,
    stop_service,
    verify_run_artifacts,
    wait_for_service_ready,
    write_json,
    write_state,
)


def _default_managed_run_id(prefix: str) -> str:
    return f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}"


def _load_taskset(path: Path, limit: int | None = None) -> list[str]:
    items = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return items[:limit] if limit else items


def _prepare_managed_dir(managed_run_id: str) -> Path:
    managed_dir = MANAGED_ROOT / managed_run_id
    managed_dir.mkdir(parents=True, exist_ok=False)
    return managed_dir


def _run_with_env(cmd: list[str], env: dict[str, str], cwd: Path, log_path: Path) -> subprocess.Popen[str]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    fh = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=fh,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )


def _watchdog_loop(
    *,
    stop_event: threading.Event,
    manifest: dict[str, Any],
    service_status_path: Path,
    run_status_path: Path,
    watchdog_path: Path,
    interval_sec: int = 60,
) -> None:
    consecutive_health_failures = 0
    while True:
        service = read_json(service_status_path)
        snapshot = collect_watchdog_snapshot(manifest, service)
        append_jsonl(watchdog_path, snapshot)
        health_ok = (
            snapshot["service_pid_alive"]
            and snapshot["port_listening"]
            and snapshot["models_ok"]
            and snapshot["model_id_match"]
            and snapshot["chat_ok"]
        )
        if health_ok:
            consecutive_health_failures = 0
        else:
            consecutive_health_failures += 1
        if consecutive_health_failures >= 3:
            write_state(
                run_status_path.parent,
                "SERVICE_CONTAMINATED",
                {
                    "updated_at": now_iso(),
                    "contamination_reason": "consecutive_health_check_failures",
                },
            )
            return
        if snapshot["contaminated"]:
            write_state(
                run_status_path.parent,
                "SERVICE_CONTAMINATED",
                {
                    "updated_at": now_iso(),
                    "contamination_reason": snapshot["contamination_reason"],
                },
            )
            return
        if stop_event.wait(interval_sec):
            return


def _env_for_aca(api_base: str, model_key: str) -> dict[str, str]:
    env = os.environ.copy()
    env["LLM_API_BASE"] = api_base
    env["LLM_API_KEY"] = "local-vllm"
    env["LLM_MODEL"] = model_key
    env["CHATANYWHERE_API_BASE"] = api_base
    env["CHATANYWHERE_API_KEY"] = "local-vllm"
    env["CHATANYWHERE_MODEL"] = model_key
    env["PYTHONNOUSERSITE"] = "1"
    aca_root = Path(__file__).resolve().parents[1]
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{aca_root}{os.pathsep}{current_pythonpath}" if current_pythonpath else str(aca_root)
    )
    for key in ["ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"]:
        env.pop(key, None)
    return env


def do_replay(args: argparse.Namespace) -> int:
    managed_run_id = args.managed_run_id or _default_managed_run_id("replay")
    managed_dir = _prepare_managed_dir(managed_run_id)
    existing_run_dir = Path(args.existing_run_dir).resolve()
    spec = get_model_spec(args.model_key)
    manifest = {
        "managed_run_id": managed_run_id,
        "managed_dir": str(managed_dir),
        "mode": "replay",
        "model_key": args.model_key,
        "model_path": spec["model_path"],
        "expected_model_id": spec["served_model_name"],
        "run_dir": str(existing_run_dir),
        "created_at": now_iso(),
    }
    write_json(managed_dir / "run_manifest.json", manifest)
    write_state(managed_dir, "CREATED", {"mode": "replay"})
    service_status = {
        "service_ok": False,
        "chat_ok": False,
        "replay_only": True,
        "expected_model_id": spec["served_model_name"],
    }
    write_json(managed_dir / "service_status.json", service_status)
    append_jsonl(managed_dir / "watchdog_status.jsonl", {"timestamp": now_iso(), "mode": "replay"})
    contamination = detect_run_contamination(existing_run_dir)
    verification = verify_run_artifacts(existing_run_dir)
    write_json(managed_dir / "artifact_verification.json", verification)
    if contamination["contaminated"]:
        write_state(managed_dir, "SERVICE_CONTAMINATED", {"contamination_reason": contamination["reason"]})
    elif verification["ok"]:
        write_state(managed_dir, "ARTIFACT_VERIFIED")
    else:
        write_state(managed_dir, "ARTIFACT_INVALID")
    build_final_report(managed_dir)
    return 0


def do_run(args: argparse.Namespace) -> int:
    managed_run_id = args.managed_run_id or _default_managed_run_id(args.label or "managed")
    managed_dir = _prepare_managed_dir(managed_run_id)
    taskset_path = Path(args.taskset).resolve()
    submission_ids = _load_taskset(taskset_path, args.task_limit)
    run_id = args.run_id or f"{managed_run_id}_aca"
    manifest = build_run_manifest(
        managed_run_id=managed_run_id,
        model_key=args.model_key,
        methods=args.methods,
        submission_ids=submission_ids,
        port=args.port,
        gpu_id=args.gpu_id,
        llm_max_tokens=args.llm_max_tokens,
        max_rounds=args.max_rounds,
        debug=args.debug,
        qwen_output_constraint=args.qwen_output_constraint,
        gtor_prompt_profile=args.gtor_prompt_profile,
        managed_dir=managed_dir,
        run_id=run_id,
        parallel=args.parallel,
        max_workers=args.max_workers,
        data_base=args.data_base,
        gpu_memory_utilization=args.gpu_memory_utilization,
        max_model_len=args.max_model_len,
        vllm_use_v1=args.vllm_use_v1,
    )
    manifest["taskset_path"] = str(taskset_path)
    manifest["watchdog_interval_sec"] = args.watchdog_interval_sec
    write_json(managed_dir / "run_manifest.json", manifest)
    write_state(managed_dir, "CREATED", {"run_dir": manifest["run_dir"]})

    preflight = preflight_verify_taskset(manifest)
    write_json(managed_dir / "taskset_preflight.json", preflight)
    if not preflight["ok"]:
        write_state(managed_dir, "TASKSET_MISMATCH", {
            "total_ids": preflight["total"],
            "found_ids": preflight["found"],
            "missing_ids": preflight.get("missing_ids", [])[:50],
            "error": preflight.get("error", "taskset_not_aligned"),
        })
        build_final_report(managed_dir)
        return 1

    write_state(managed_dir, "SERVICE_STARTING")
    try:
        service = launch_vllm(manifest, managed_dir / "service_status.json")
    except Exception as exc:
        write_json(managed_dir / "service_status.json", {"service_ok": False, "chat_ok": False, "error": str(exc)})
        write_state(managed_dir, "SERVICE_START_FAILED", {"error": str(exc)})
        build_final_report(managed_dir)
        return 1

    try:
        health = wait_for_service_ready(managed_dir / "service_status.json", startup_timeout_sec=manifest["startup_timeout_sec"])
        if not health.ok:
            write_state(managed_dir, "CHAT_CHECK_FAILED", {"error": health.error})
            build_final_report(managed_dir)
            return 1
        write_state(managed_dir, "SERVICE_READY")
        write_state(managed_dir, "CHAT_VERIFIED")

        stop_event = threading.Event()
        initial_snapshot = collect_watchdog_snapshot(manifest, read_json(managed_dir / "service_status.json"))
        append_jsonl(managed_dir / "watchdog_status.jsonl", initial_snapshot)
        watchdog = threading.Thread(
            target=_watchdog_loop,
            kwargs={
                "stop_event": stop_event,
                "manifest": manifest,
                "service_status_path": managed_dir / "service_status.json",
                "run_status_path": managed_dir / "run_status.json",
                "watchdog_path": managed_dir / "watchdog_status.jsonl",
                "interval_sec": args.watchdog_interval_sec,
            },
            daemon=True,
        )
        watchdog.start()

        write_state(managed_dir, "ACA_RUNNING")
        aca_env = _env_for_aca(read_json(managed_dir / "service_status.json")["api_base"], args.model_key)
        aca_proc = _run_with_env(
            build_run_command(manifest, resume=False),
            aca_env,
            Path(__file__).resolve().parents[1],
            managed_dir / "logs" / "aca_run.log",
        )

        while True:
            ret = aca_proc.poll()
            state = read_json(managed_dir / "run_status.json").get("state")
            if state == "SERVICE_CONTAMINATED":
                aca_proc.terminate()
                stop_event.set()
                watchdog.join(timeout=2)
                build_final_report(managed_dir)
                return 1
            if ret is not None:
                break
            time.sleep(5)

        stop_event.set()
        watchdog.join(timeout=2)
        if ret != 0:
            write_state(managed_dir, "ACA_FAILED", {"aca_exit_code": ret})
            build_final_report(managed_dir)
            return 1

        write_state(managed_dir, "ACA_DONE")
        verification = verify_run_artifacts(Path(manifest["run_dir"]), require_analyzer_outputs=False)
        write_json(managed_dir / "artifact_verification.json", verification)
        if not verification["ok"]:
            write_state(managed_dir, "ARTIFACT_INVALID", {"contamination_reason": verification.get("contamination_reason")})
            build_final_report(managed_dir)
            return 1
        write_state(managed_dir, "ARTIFACT_VERIFIED")

        analyze = run_analyzer(Path(manifest["run_dir"]))
        (managed_dir / "logs").mkdir(parents=True, exist_ok=True)
        (managed_dir / "logs" / "analyzer.log").write_text(analyze.stdout + "\n" + analyze.stderr, encoding="utf-8")
        if analyze.returncode != 0:
            write_state(managed_dir, "ANALYZER_FAILED", {"analyzer_exit_code": analyze.returncode})
            build_final_report(managed_dir)
            return 1
        verification = verify_run_artifacts(Path(manifest["run_dir"]), require_analyzer_outputs=True)
        write_json(managed_dir / "artifact_verification.json", verification)
        if not verification["ok"]:
            write_state(managed_dir, "ARTIFACT_INVALID", {"contamination_reason": verification.get("contamination_reason")})
            build_final_report(managed_dir)
            return 1
        write_state(managed_dir, "REWARD_ANALYZED")

        build_final_report(managed_dir)
        write_state(managed_dir, "REPORT_DONE")
        return_code = 0
        return return_code
    finally:
        try:
            service_status = read_json(managed_dir / "service_status.json")
            stop_service(service_status)
            service_status["stopped_at"] = now_iso()
            service_status["service_ok"] = False
            service_status["chat_ok"] = False
            write_json(managed_dir / "service_status.json", service_status)
        except Exception:
            pass
        state = read_json(managed_dir / "run_status.json").get("state")
        if state not in ERROR_STATES:
            write_state(managed_dir, "SERVICE_STOPPED")
            write_state(managed_dir, "COMPLETE")
        final = build_final_report(managed_dir)
        if state in ERROR_STATES:
            write_state(managed_dir, state, {"contamination_reason": final.get("contamination_reason")})


def main() -> None:
    parser = argparse.ArgumentParser(description="ACA_model managed pipeline v0.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    replay = sub.add_parser("replay", help="Replay an existing run and classify contamination.")
    replay.add_argument("--managed-run-id", default=None)
    replay.add_argument("--existing-run-dir", required=True)
    replay.add_argument("--model-key", required=True)
    replay.set_defaults(func=do_replay)

    run = sub.add_parser("run", help="Run a managed ACA experiment end to end.")
    run.add_argument("--managed-run-id", default=None)
    run.add_argument("--label", default="managed")
    run.add_argument("--model-key", required=True)
    run.add_argument("--port", type=int, required=True)
    run.add_argument("--gpu-id", type=int, required=True)
    run.add_argument("--taskset", required=True)
    run.add_argument("--task-limit", type=int, default=None)
    run.add_argument("--methods", nargs="+", required=True)
    run.add_argument("--run-id", default=None)
    run.add_argument("--max-rounds", type=int, default=4)
    run.add_argument("--llm-max-tokens", type=int, default=1024)
    run.add_argument("--qwen-output-constraint", default="auto")
    run.add_argument("--gtor-prompt-profile", choices=["legacy", "small_model_minimal"], default="legacy")
    run.add_argument("--watchdog-interval-sec", type=int, default=60)
    run.add_argument("--parallel", action="store_true")
    run.add_argument("--max-workers", type=int, default=1)
    run.add_argument("--data-base", default=None)
    run.add_argument("--gpu-memory-utilization", type=float, default=0.35)
    run.add_argument("--max-model-len", type=int, default=8192)
    run.add_argument("--vllm-use-v1", choices=["0", "1"], default=None)
    run.add_argument("--debug", action="store_true")
    run.set_defaults(func=do_run)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
