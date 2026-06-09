from __future__ import annotations

import csv
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MANAGED_ROOT = ROOT / "managed_runs"
LOCAL_ACA_ROOT = ROOT / "ACA"
EXTERNAL_ACA_ROOT = Path("/data/whn/ACA")
ACA_ROOT = LOCAL_ACA_ROOT if LOCAL_ACA_ROOT.exists() else EXTERNAL_ACA_ROOT
DEFAULT_DATA_BASE = ACA_ROOT / "data" / "waFocusedData_submit_0526_final"
ACA_PYTHON_BIN = Path(os.environ.get("ACA_PYTHON_BIN", sys.executable))
RUN_STATE_ORDER = [
    "CREATED",
    "SERVICE_STARTING",
    "SERVICE_READY",
    "CHAT_VERIFIED",
    "ACA_RUNNING",
    "ACA_DONE",
    "ARTIFACT_VERIFIED",
    "REWARD_ANALYZED",
    "REPORT_DONE",
    "SERVICE_STOPPED",
    "COMPLETE",
]
ERROR_STATES = {
    "SERVICE_START_FAILED",
    "CHAT_CHECK_FAILED",
    "SERVICE_CONTAMINATED",
    "ACA_FAILED",
    "ARTIFACT_INVALID",
    "ANALYZER_FAILED",
    "TASKSET_MISMATCH",
}
REQUIRED_RUN_FILES_PRE_ANALYZER = [
    "config.json",
    "summary.json",
    "run_matrix.json",
    "failure_modes.json",
]
REQUIRED_RUN_FILES_POST_ANALYZER = [
    "reward_v1_summary.json",
    "reward_v1_table.csv",
    "reward_v1_by_round.jsonl",
    "reward_v1_summary.md",
]
API_ERROR_BURST_THRESHOLD = 3


@dataclass
class HealthResult:
    ok: bool
    service_ok: bool
    models_ok: bool
    model_id_match: bool
    chat_ok: bool
    content_len: int
    model_ids: list[str]
    model_id: str | None
    content_preview: str
    error: str | None = None


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_markdown(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_model_spec(model_key: str) -> dict[str, Any]:
    shared_conda_env = os.environ.get("VLLM_CONDA_ENV")
    mapping = {
        "qwen25-coder-7b": {
            "model_path": "/data/LLMs/Qwen2.5-Coder-7B-Instruct",
            "served_model_name": "qwen25-coder-7b",
            "conda_env": shared_conda_env or "ACAvllms124",
            "fallback_env": "vllm_test_017",
            "is_qwen35": False,
        },
        "qwen35-9b": {
            "model_path": "/data/LLMs/Qwen3.5-9B",
            "served_model_name": "qwen35-9b",
            "conda_env": shared_conda_env or "vllm017_full",
            "fallback_env": "vllm_test_017",
            "is_qwen35": True,
        },
        "qwen35-4b": {
            "model_path": "/data/LLMs/Qwen3.5-4B",
            "served_model_name": "qwen35-4b",
            "conda_env": shared_conda_env or "vllm017_full",
            "fallback_env": "vllm_test_017",
            "is_qwen35": True,
        },
    }
    if model_key not in mapping:
        raise ValueError(f"Unsupported model_key: {model_key}")
    spec = mapping[model_key].copy()
    spec["model_key"] = model_key
    return spec


def port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def detect_port_owner_pid(port: int) -> int | None:
    proc = subprocess.run(
        ["bash", "-lc", f"ss -ltnp '( sport = :{port} )'"],
        capture_output=True,
        text=True,
        check=False,
    )
    text = proc.stdout + proc.stderr
    for token in text.split():
        if "pid=" in token:
            try:
                return int(token.split("pid=", 1)[1].split(",", 1)[0].strip("()"))
            except ValueError:
                continue
    return None


def ensure_port_free_or_fail(port: int) -> None:
    if port_listening(port):
        pid = detect_port_owner_pid(port)
        raise RuntimeError(f"port {port} already occupied by pid={pid or 'unknown'}")


def pid_alive(pid: int | None) -> bool:
    return bool(pid and Path(f"/proc/{pid}").exists())


def post_chat(api_base: str, api_key: str, model: str, message: str, max_tokens: int = 16) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        api_base.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def get_models(api_base: str, api_key: str) -> dict[str, Any]:
    req = urllib.request.Request(
        api_base.rstrip("/") + "/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def health_check(
    *,
    api_base: str,
    api_key: str,
    expected_model_id: str,
    models_json_path: Path | None = None,
    chat_json_path: Path | None = None,
) -> HealthResult:
    try:
        if models_json_path is not None:
            models = read_json(models_json_path)
        else:
            models = get_models(api_base, api_key)
    except Exception as exc:
        return HealthResult(
            ok=False,
            service_ok=False,
            models_ok=False,
            model_id_match=False,
            chat_ok=False,
            content_len=0,
            model_ids=[],
            model_id=None,
            content_preview="",
            error=f"models_error: {exc}",
        )

    model_ids = [str(item.get("id", "")) for item in (models.get("data") or []) if isinstance(item, dict)]
    models_ok = bool(model_ids)
    model_id = model_ids[0] if model_ids else None
    model_id_match = expected_model_id in model_ids

    try:
        if chat_json_path is not None:
            chat = read_json(chat_json_path)
        else:
            if model_id is None:
                raise RuntimeError("no model ids returned from /v1/models")
            chat = post_chat(api_base, api_key, model_id, "Reply with OK only.")
    except Exception as exc:
        return HealthResult(
            ok=False,
            service_ok=True,
            models_ok=models_ok,
            model_id_match=model_id_match,
            chat_ok=False,
            content_len=0,
            model_ids=model_ids,
            model_id=model_id,
            content_preview="",
            error=f"chat_error: {exc}",
        )

    content = ((((chat.get("choices") or [{}])[0]).get("message") or {}).get("content") or "").strip()
    chat_ok = bool(content)
    content_preview = content[:200]
    ok = models_ok and model_id_match and chat_ok
    return HealthResult(
        ok=ok,
        service_ok=True,
        models_ok=models_ok,
        model_id_match=model_id_match,
        chat_ok=chat_ok,
        content_len=len(content),
        model_ids=model_ids,
        model_id=model_id,
        content_preview=content_preview,
        error=None if ok else "health_check_failed",
    )


def count_task_statuses(run_dir: Path) -> dict[str, Any]:
    statuses = list(run_dir.glob("tasks/*/*/task_status.json"))
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in statuses:
        try:
            payload = read_json(path)
        except Exception:
            payload = {"status": "unknown"}
        counts[path.parent.parent.name][str(payload.get("status", "unknown"))] += 1
    return {
        "count": len(statuses),
        "by_method": {k: dict(v) for k, v in sorted(counts.items())},
    }


def detect_run_contamination(run_dir: Path, api_error_burst_threshold: int = API_ERROR_BURST_THRESHOLD) -> dict[str, Any]:
    api_error_count = 0
    task_hits = Counter()
    timestamps: list[str] = []
    for path in run_dir.glob("tasks/*/*/trajectory.jsonl"):
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            blob = json.dumps(obj, ensure_ascii=False)
            if "APIConnectionError" in blob or "Connection error." in blob:
                api_error_count += 1
                task_hits[path.parent.name] += 1
                if obj.get("timestamp"):
                    timestamps.append(str(obj["timestamp"]))
    if api_error_count >= api_error_burst_threshold:
        return {
            "contaminated": True,
            "reason": "api_connection_error_burst",
            "api_connection_error_count": api_error_count,
            "affected_task_count": len(task_hits),
            "timestamps": timestamps[:20],
        }
    return {
        "contaminated": False,
        "reason": None,
        "api_connection_error_count": api_error_count,
        "affected_task_count": len(task_hits),
        "timestamps": timestamps[:20],
    }


def verify_run_artifacts(run_dir: Path, require_analyzer_outputs: bool = False) -> dict[str, Any]:
    required_run = list(REQUIRED_RUN_FILES_PRE_ANALYZER)
    if require_analyzer_outputs:
        required_run += REQUIRED_RUN_FILES_POST_ANALYZER
    missing_run = [name for name in required_run if not (run_dir / name).exists()]
    status_files = sorted(run_dir.glob("tasks/*/*/task_status.json"))
    task_count = len(status_files)
    missing_task_files = []
    broken_status = []
    for status_path in status_files:
        task_dir = status_path.parent
        payload = read_json(status_path)
        if payload.get("status") not in {"success", "failed"}:
            broken_status.append(str(task_dir))
        for name in ["result.json", "trajectory.jsonl", "trace.json", "config.json"]:
            if not (task_dir / name).exists():
                missing_task_files.append(f"{task_dir}:{name}")
    contamination = detect_run_contamination(run_dir)
    ok = not missing_run and not missing_task_files and not broken_status
    usable_for_model_quality = ok and not contamination["contaminated"]
    return {
        "ok": ok,
        "run_dir": str(run_dir),
        "task_count": task_count,
        "require_analyzer_outputs": require_analyzer_outputs,
        "missing_run_files": missing_run,
        "missing_task_files": missing_task_files[:200],
        "non_terminal_task_dirs": broken_status[:200],
        "usable_for_model_quality": usable_for_model_quality,
        "usable_for_prompt_comparison": usable_for_model_quality,
        "contamination_reason": contamination["reason"],
        "api_connection_error_count": contamination["api_connection_error_count"],
        "contaminated": contamination["contaminated"],
    }


def build_final_report(managed_dir: Path) -> dict[str, Any]:
    manifest = read_json(managed_dir / "run_manifest.json")
    status = read_json(managed_dir / "run_status.json")
    service = read_json(managed_dir / "service_status.json") if (managed_dir / "service_status.json").exists() else {}
    artifacts = read_json(managed_dir / "artifact_verification.json") if (managed_dir / "artifact_verification.json").exists() else {}
    final = {
        "managed_run_id": manifest.get("managed_run_id"),
        "state": status.get("state"),
        "usable_for_model_quality": bool(artifacts.get("usable_for_model_quality", False)),
        "usable_for_prompt_comparison": bool(artifacts.get("usable_for_prompt_comparison", False)),
        "contamination_reason": artifacts.get("contamination_reason"),
        "expected_model_id": manifest.get("expected_model_id"),
        "service_ok": service.get("service_ok"),
        "chat_ok": service.get("chat_ok"),
        "run_dir": manifest.get("run_dir"),
    }
    lines = [
        f"# Managed Run Final Report: {manifest.get('managed_run_id')}",
        "",
        f"- state: `{final['state']}`",
        f"- usable_for_model_quality: `{final['usable_for_model_quality']}`",
        f"- usable_for_prompt_comparison: `{final['usable_for_prompt_comparison']}`",
        f"- contamination_reason: `{final['contamination_reason']}`",
        f"- expected_model_id: `{final['expected_model_id']}`",
        f"- service_ok: `{final['service_ok']}`",
        f"- chat_ok: `{final['chat_ok']}`",
        f"- run_dir: `{final['run_dir']}`",
    ]
    append_markdown(managed_dir / "final_report.md", "\n".join(lines) + "\n")
    if final["contamination_reason"]:
        append_markdown(
            managed_dir / "contamination_report.md",
            "\n".join(
                [
                    f"# Managed Run Contamination: {manifest.get('managed_run_id')}",
                    "",
                    f"- contamination_reason: `{final['contamination_reason']}`",
                    f"- usable_for_model_quality: `{final['usable_for_model_quality']}`",
                    f"- usable_for_prompt_comparison: `{final['usable_for_prompt_comparison']}`",
                ]
            )
            + "\n",
        )
    return final


def write_state(managed_dir: Path, state: str, extra: dict[str, Any] | None = None) -> None:
    payload = {
        "state": state,
        "updated_at": now_iso(),
    }
    if extra:
        payload.update(extra)
    write_json(managed_dir / "run_status.json", payload)


def launch_vllm(manifest: dict[str, Any], service_status_path: Path) -> dict[str, Any]:
    spec = get_model_spec(str(manifest["model_key"]))
    ensure_port_free_or_fail(int(manifest["port"]))
    log_dir = Path(manifest["managed_dir"]) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "vllm_stdout.log"
    stderr_path = log_dir / "vllm_stderr.log"
    env = os.environ.copy()
    env["PYTHONNOUSERSITE"] = "1"
    env["CUDA_HOME"] = "/data/package/cuda-12.4"
    env["PATH"] = f"/data/package/cuda-12.4/bin:{env.get('PATH', '')}"
    env["LD_LIBRARY_PATH"] = f"/data/package/cuda-12.4/lib64{':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else ''}"
    env["CUDA_VISIBLE_DEVICES"] = str(manifest["gpu_id"])
    env["TMPDIR"] = "/data/whn/tmp"
    env["HF_HOME"] = "/data/whn/tmp/acavllms-hf"
    env["XDG_CACHE_HOME"] = "/data/whn/tmp/acavllms-xdg"
    env["PIP_CACHE_DIR"] = "/data/whn/tmp/acavllms-pip-cache"
    if manifest.get("vllm_use_v1") is not None:
        env["VLLM_USE_V1"] = str(manifest["vllm_use_v1"])
    for key in ["ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"]:
        env.pop(key, None)
    vllm_bin = f"/data/miniconda3/envs/{spec['conda_env']}/bin/vllm"
    cmd = [
        vllm_bin,
        "serve",
        spec["model_path"],
        "--host",
        "127.0.0.1",
        "--port",
        str(manifest["port"]),
        "--dtype",
        "auto",
        "--api-key",
        str(manifest["api_key"]),
        "--served-model-name",
        spec["served_model_name"],
        "--tensor-parallel-size",
        "1",
        "--gpu-memory-utilization",
        str(manifest.get("gpu_memory_utilization", 0.35)),
        "--max-model-len",
        str(manifest["max_model_len"]),
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "hermes",
        "--enforce-eager",
    ]
    qwen35_reasoning_parser = os.environ.get("QWEN35_REASONING_PARSER", "").strip()
    if spec["is_qwen35"] and qwen35_reasoning_parser:
        cmd += [
            "--reasoning-parser",
            qwen35_reasoning_parser,
            "--default-chat-template-kwargs",
            '{"enable_thinking": false}',
        ]
    with stdout_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(
            cmd,
            stdout=out,
            stderr=err,
            env=env,
            start_new_session=True,
        )
    service = {
        "service_ok": False,
        "chat_ok": False,
        "port": int(manifest["port"]),
        "api_base": f"http://127.0.0.1:{manifest['port']}/v1",
        "api_key": manifest["api_key"],
        "expected_model_id": spec["served_model_name"],
        "service_pid": proc.pid,
        "service_pgid": proc.pid,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "started_at": now_iso(),
        "command": cmd,
    }
    write_json(service_status_path, service)
    return service


def stop_service(service_status: dict[str, Any]) -> None:
    pid = int(service_status.get("service_pid") or 0)
    pgid = int(service_status.get("service_pgid") or 0)
    if pgid:
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for _ in range(30):
            if not pid_alive(pid):
                return
            time.sleep(1)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def wait_for_service_ready(service_status_path: Path, startup_timeout_sec: int = 240) -> HealthResult:
    service = read_json(service_status_path)
    deadline = time.time() + startup_timeout_sec
    last = HealthResult(False, False, False, False, False, 0, [], None, "", "not_started")
    while time.time() < deadline:
        if not pid_alive(int(service.get("service_pid") or 0)):
            return HealthResult(False, False, False, False, False, 0, [], None, "", "service_pid_exited")
        last = health_check(
            api_base=str(service["api_base"]),
            api_key=str(service["api_key"]),
            expected_model_id=str(service["expected_model_id"]),
        )
        if last.ok:
            service["service_ok"] = True
            service["chat_ok"] = True
            service["verified_at"] = now_iso()
            write_json(service_status_path, service)
            return last
        time.sleep(2)
    return last


def build_run_manifest(
    *,
    managed_run_id: str,
    model_key: str,
    methods: list[str],
    submission_ids: list[str],
    port: int,
    gpu_id: int,
    llm_max_tokens: int,
    max_rounds: int,
    debug: bool,
    qwen_output_constraint: str,
    gtor_prompt_profile: str,
    managed_dir: Path,
    run_id: str,
    parallel: bool = False,
    max_workers: int = 1,
    data_base: str | None = None,
    gpu_memory_utilization: float = 0.35,
    max_model_len: int = 8192,
    vllm_use_v1: str | None = None,
) -> dict[str, Any]:
    spec = get_model_spec(model_key)
    run_output_root = managed_dir / "aca_output"
    run_dir = run_output_root / "runs" / run_id
    manifest = {
        "managed_run_id": managed_run_id,
        "managed_dir": str(managed_dir),
        "model_key": model_key,
        "model_path": spec["model_path"],
        "expected_model_id": spec["served_model_name"],
        "methods": methods,
        "submission_ids": submission_ids,
        "port": port,
        "gpu_id": gpu_id,
        "api_key": "local-vllm",
        "llm_max_tokens": llm_max_tokens,
        "max_rounds": max_rounds,
        "max_model_len": max_model_len,
        "debug": debug,
        "generator_seeds_per_round": 16,
        "qwen_output_constraint": qwen_output_constraint,
        "gtor_prompt_profile": gtor_prompt_profile,
        "run_id": run_id,
        "run_output_root": str(run_output_root),
        "run_dir": str(run_dir),
        "parallel": parallel,
        "max_workers": max_workers,
        "startup_timeout_sec": 240,
        "gpu_memory_utilization": gpu_memory_utilization,
        "created_at": now_iso(),
    }
    if vllm_use_v1 is not None:
        manifest["vllm_use_v1"] = vllm_use_v1
    if data_base:
        manifest["data_base"] = data_base
    return manifest


def preflight_verify_taskset(manifest: dict[str, Any]) -> dict[str, Any]:
    """Verify that every submission_id in the taskset is present in the ACA adapter cache.

    Returns a dict with keys: ok, total, found, missing_ids.
    If ok is False, the run must not proceed.
    """
    data_base = Path(manifest.get("data_base", str(DEFAULT_DATA_BASE)))
    submission_ids: list[str] = list(manifest.get("submission_ids") or [])

    adapter_cache = None
    managed_runs_root = MANAGED_ROOT
    if managed_runs_root.exists():
        for run_dir in sorted(managed_runs_root.iterdir(), reverse=True):
            candidate = run_dir / "aca_output" / "_wa_focused_adapter_cache" / "waFocused_clean_main_runner_ready.ndjson"
            if candidate.exists():
                adapter_cache = candidate
                break
    if adapter_cache is None:
        for root in [data_base, data_base / "_wa_focused_adapter_cache"]:
            if not root.exists():
                continue
            for candidate in sorted(root.glob("waFocused_clean_main_runner_ready*.ndjson")):
                adapter_cache = candidate
                break

    if adapter_cache is None:
        return {
            "ok": False,
            "error": "no_adapter_cache_found",
            "total": len(submission_ids),
            "found": 0,
            "missing_ids": submission_ids,
        }

    adapter_ids: set[str] = set()
    with adapter_cache.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            adapter_ids.add(obj.get("submission_id", obj.get("candidate_id", "")))

    taskset_set = set(submission_ids)
    found = taskset_set & adapter_ids
    missing = sorted(taskset_set - adapter_ids)

    return {
        "ok": len(missing) == 0,
        "adapter_cache": str(adapter_cache),
        "total": len(submission_ids),
        "found": len(found),
        "missing_ids": missing,
    }


def build_run_command(manifest: dict[str, Any], resume: bool = False) -> list[str]:
    cmd = [
        str(ACA_PYTHON_BIN),
        "-m",
        "ACA.run_experiment",
        "--methods",
        *manifest["methods"],
        "--data-base",
        manifest.get("data_base", str(DEFAULT_DATA_BASE)),
        "--submission-ids",
        ",".join(manifest["submission_ids"]),
        "--output",
        manifest["run_output_root"],
        "--run-id",
        manifest["run_id"],
        "--generator-seeds-per-round",
        str(manifest["generator_seeds_per_round"]),
        "--max-rounds",
        str(manifest["max_rounds"]),
        "--llm-model",
        manifest["model_key"],
        "--llm-temperature",
        "0.2",
        "--llm-max-tokens",
        str(manifest["llm_max_tokens"]),
        "--qwen-output-constraint",
        manifest["qwen_output_constraint"],
        "--gtor-prompt-profile",
        manifest.get("gtor_prompt_profile", "legacy"),
    ]
    if manifest.get("parallel"):
        cmd.append("--parallel")
        cmd.extend(["--max-workers", str(manifest.get("max_workers", 1))])
    if manifest["debug"]:
        cmd.append("--debug")
    if resume:
        cmd.append("--resume")
    return cmd


def run_analyzer(run_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(ACA_PYTHON_BIN), str(ACA_ROOT / "scripts" / "analyze_generator_reward_v1.py"), str(run_dir)],
        text=True,
        capture_output=True,
        check=False,
    )


def collect_watchdog_snapshot(manifest: dict[str, Any], service_status: dict[str, Any]) -> dict[str, Any]:
    run_dir = Path(manifest["run_dir"])
    health = health_check(
        api_base=str(service_status["api_base"]),
        api_key=str(service_status["api_key"]),
        expected_model_id=str(service_status["expected_model_id"]),
    )
    task_stats = count_task_statuses(run_dir) if run_dir.exists() else {"count": 0, "by_method": {}}
    contamination = detect_run_contamination(run_dir) if run_dir.exists() else {"contaminated": False, "api_connection_error_count": 0}
    return {
        "timestamp": now_iso(),
        "service_pid_alive": pid_alive(int(service_status.get("service_pid") or 0)),
        "port_listening": port_listening(int(manifest["port"])),
        "models_ok": health.models_ok,
        "chat_ok": health.chat_ok,
        "model_id_match": health.model_id_match,
        "task_status_count": task_stats["count"],
        "task_status_by_method": task_stats["by_method"],
        "api_connection_error_count": contamination.get("api_connection_error_count", 0),
        "contaminated": contamination.get("contaminated", False),
        "contamination_reason": contamination.get("reason"),
    }
