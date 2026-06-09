#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MODEL_7B = "qwen25-coder-7b"
MODEL_9B = "qwen35-9b"
MODEL_DEFAULT_CONDA_ENV = {
    MODEL_7B: "ACAvllms124",
    MODEL_9B: "vllm017_full",
}
MODEL_DEFAULT_MAX_MODEL_LEN = {
    MODEL_7B: 8192,
    MODEL_9B: 8192,
}
MODEL_DEFAULT_LLM_MAX_TOKENS = {
    MODEL_7B: 2048,
    MODEL_9B: 2048,
}
MODEL_MIN_GPU_MEMORY_UTILIZATION = {
    MODEL_7B: 0.40,
    MODEL_9B: 0.30,
}


def parse_nvidia_smi_memory(text: str) -> list[dict[str, int]]:
    gpus: list[dict[str, int]] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) != 3:
            continue
        try:
            index, used_mib, total_mib = map(int, parts)
        except ValueError:
            continue
        gpus.append(
            {
                "index": index,
                "used_mib": used_mib,
                "total_mib": total_mib,
                "free_mib": max(0, total_mib - used_mib),
            }
        )
    return gpus


def parse_gpustat_json(text: str) -> list[dict[str, int]]:
    payload = json.loads(text)
    gpus: list[dict[str, int]] = []
    for item in payload.get("gpus", []):
        try:
            index = int(item["index"])
            used_mib = int(item["memory.used"])
            total_mib = int(item["memory.total"])
        except (KeyError, TypeError, ValueError):
            continue
        gpus.append(
            {
                "index": index,
                "used_mib": used_mib,
                "total_mib": total_mib,
                "free_mib": max(0, total_mib - used_mib),
            }
        )
    return gpus


def read_gpu_memory_gpustat() -> list[dict[str, int]]:
    raw = subprocess.check_output(["gpustat", "--json"], text=True, stderr=subprocess.DEVNULL)
    return parse_gpustat_json(raw)


def read_gpu_memory() -> list[dict[str, int]]:
    try:
        return read_gpu_memory_gpustat()
    except Exception:
        raw = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return parse_nvidia_smi_memory(raw)


def _gpu_by_id(gpus: list[dict[str, int]], gpu_id: int) -> dict[str, int] | None:
    for gpu in gpus:
        if gpu["index"] == gpu_id:
            return gpu
    return None


def _safe_gpu_memory_utilization(
    gpu: dict[str, int] | None,
    *,
    default_util: float,
    margin_mib: int,
    min_util: float,
) -> float:
    if gpu is None:
        return round(max(min_util, default_util), 2)
    usable_free = max(0, gpu["free_mib"] - margin_mib)
    safe = usable_free / gpu["total_mib"] if gpu["total_mib"] else default_util
    return round(max(min_util, min(default_util, safe)), 2)


def plan_dual_probe20(
    gpus: list[dict[str, int]],
    *,
    requested_7b: str = "auto",
    requested_9b: str = "auto",
    default_util: float = 0.35,
    margin_mib: int = 3072,
    run_mode: str = "sequential",
) -> dict[str, dict[str, Any]]:
    ranked = sorted(gpus, key=lambda item: item["free_mib"], reverse=True)
    if run_mode not in {"sequential", "parallel"}:
        raise ValueError(f"Unsupported run_mode: {run_mode}")
    if run_mode == "sequential":
        fallback = ranked[0]["index"] if ranked else 1
        gpu_9b = int(requested_9b) if requested_9b != "auto" else fallback
        gpu_7b = int(requested_7b) if requested_7b != "auto" else fallback
    else:
        fixed = {int(value) for value in [requested_7b, requested_9b] if value != "auto"}
        available = [gpu["index"] for gpu in ranked if gpu["index"] not in fixed]
        gpu_9b = int(requested_9b) if requested_9b != "auto" else (available.pop(0) if available else 2)
        gpu_7b = int(requested_7b) if requested_7b != "auto" else (available.pop(0) if available else 1)

    gpu_7b_info = _gpu_by_id(gpus, gpu_7b)
    gpu_9b_info = _gpu_by_id(gpus, gpu_9b)
    return {
        MODEL_7B: {
            "gpu_id": gpu_7b,
            "port": 8017,
            "gpu_memory_utilization": _safe_gpu_memory_utilization(
                gpu_7b_info,
                default_util=default_util,
                margin_mib=margin_mib,
                min_util=MODEL_MIN_GPU_MEMORY_UTILIZATION[MODEL_7B],
            ),
            "free_mib": gpu_7b_info.get("free_mib") if gpu_7b_info else None,
            "total_mib": gpu_7b_info.get("total_mib") if gpu_7b_info else None,
        },
        MODEL_9B: {
            "gpu_id": gpu_9b,
            "port": 8029,
            "gpu_memory_utilization": _safe_gpu_memory_utilization(
                gpu_9b_info,
                default_util=default_util,
                margin_mib=margin_mib,
                min_util=MODEL_MIN_GPU_MEMORY_UTILIZATION[MODEL_9B],
            ),
            "free_mib": gpu_9b_info.get("free_mib") if gpu_9b_info else None,
            "total_mib": gpu_9b_info.get("total_mib") if gpu_9b_info else None,
        },
    }


def classify_vllm_failure(text: str) -> dict[str, str | None]:
    if "layers.0.linear_attn.A_log" in text:
        evidence_line = next(
            (
                line
                for line in text.splitlines()
                if "layers.0.linear_attn.A_log" in line
            ),
            text,
        )
        evidence = " ".join(evidence_line.split())
        return {"reason": "MODEL_ENV_INCOMPATIBLE", "evidence": evidence}
    if "No available memory for the cache blocks" in text:
        evidence_line = next(
            (
                line
                for line in text.splitlines()
                if "No available memory for the cache blocks" in line
            ),
            text,
        )
        evidence = " ".join(evidence_line.split())
        return {"reason": "KV_CACHE_INSUFFICIENT", "evidence": evidence}
    if "KV cache is needed" in text and "available KV cache memory" in text:
        evidence_line = next(
            (
                line
                for line in text.splitlines()
                if "KV cache is needed" in line and "available KV cache memory" in line
            ),
            text,
        )
        evidence = " ".join(evidence_line.split())
        return {"reason": "KV_CACHE_INSUFFICIENT", "evidence": evidence}
    if "Free memory on device" in text and "desired GPU memory utilization" in text:
        evidence_line = next(
            (
                line
                for line in text.splitlines()
                if "Free memory on device" in line and "desired GPU memory utilization" in line
            ),
            text,
        )
        evidence = " ".join(evidence_line.split())
        return {"reason": "GPU_MEMORY_INSUFFICIENT", "evidence": evidence}
    if "torch.OutOfMemoryError" in text or "CUDA out of memory" in text or "Tried to allocate" in text:
        evidence_line = next(
            (
                line
                for line in text.splitlines()
                if "OutOfMemoryError" in line or "out of memory" in line or "Tried to allocate" in line
            ),
            text,
        )
        evidence = " ".join(evidence_line.split())
        return {"reason": "GPU_MEMORY_INSUFFICIENT", "evidence": evidence}
    if "Address already in use" in text or "port is already allocated" in text:
        return {"reason": "PORT_OCCUPIED", "evidence": "port already in use"}
    if "No such file or directory" in text and "model" in text.lower():
        return {"reason": "MODEL_PATH_MISSING", "evidence": "model path missing"}
    return {"reason": None, "evidence": None}


def classify_managed_run(managed_dir: Path) -> dict[str, Any]:
    service_path = managed_dir / "service_status.json"
    stderr_path = None
    if service_path.exists():
        try:
            service = json.loads(service_path.read_text(encoding="utf-8"))
            if service.get("stderr_log"):
                stderr_path = Path(str(service["stderr_log"]).replace("/data/whn/ACA_model", str(DEFAULT_ROOT)))
        except Exception:
            pass
    text = stderr_path.read_text(encoding="utf-8", errors="ignore") if stderr_path and stderr_path.exists() else ""
    diagnosis = classify_vllm_failure(text)
    return {
        "managed_dir": str(managed_dir),
        "stderr_log": str(stderr_path) if stderr_path else None,
        **diagnosis,
    }


def build_probe20_launch_command(
    plan: dict[str, dict[str, Any]],
    *,
    max_workers: int,
    monitor_interval_sec: int,
    run_mode: str = "sequential",
    vllm_conda_env: str | None = None,
    vllm_conda_env_7b: str | None = None,
    vllm_conda_env_9b: str | None = None,
    root: Path = DEFAULT_ROOT,
) -> str:
    model_7b = plan[MODEL_7B]
    model_9b = plan[MODEL_9B]
    env_7b = vllm_conda_env or vllm_conda_env_7b or MODEL_DEFAULT_CONDA_ENV[MODEL_7B]
    env_9b = vllm_conda_env or vllm_conda_env_9b or MODEL_DEFAULT_CONDA_ENV[MODEL_9B]
    assignments = {
        "GPU_7B": model_7b["gpu_id"],
        "GPU_9B": model_9b["gpu_id"],
        "GPU_MEMORY_UTILIZATION_7B": model_7b["gpu_memory_utilization"],
        "GPU_MEMORY_UTILIZATION_9B": model_9b["gpu_memory_utilization"],
        "MAX_WORKERS": max_workers,
        "MONITOR_INTERVAL_SEC": monitor_interval_sec,
        "MODEL_RUN_MODE": run_mode,
        "CONTINUE_ON_MODEL_FAILURE": 1,
        "LLM_MAX_TOKENS_7B": MODEL_DEFAULT_LLM_MAX_TOKENS[MODEL_7B],
        "LLM_MAX_TOKENS_9B": MODEL_DEFAULT_LLM_MAX_TOKENS[MODEL_9B],
        "MAX_MODEL_LEN_7B": MODEL_DEFAULT_MAX_MODEL_LEN[MODEL_7B],
        "MAX_MODEL_LEN_9B": MODEL_DEFAULT_MAX_MODEL_LEN[MODEL_9B],
        "VLLM_CONDA_ENV_7B": env_7b,
        "VLLM_CONDA_ENV_9B": env_9b,
    }
    env = " ".join(f"{key}={shlex.quote(str(value))}" for key, value in assignments.items())
    return f"cd {shlex.quote(str(root))} && {env} bash scripts/run_gtor4_probe20_dual_progress.sh"


def _cmd_plan(args: argparse.Namespace) -> int:
    try:
        gpus = read_gpu_memory()
    except Exception as exc:
        payload = {
            "ok": False,
            "error": f"nvidia_smi_failed: {exc}",
            "plan": plan_dual_probe20([], requested_7b=args.gpu_7b, requested_9b=args.gpu_9b),
        }
    else:
        payload = {
            "ok": True,
            "gpus": gpus,
            "plan": plan_dual_probe20(
                gpus,
                requested_7b=args.gpu_7b,
                requested_9b=args.gpu_9b,
                default_util=args.default_gpu_memory_utilization,
                margin_mib=args.gpu_memory_margin_mib,
                run_mode=args.run_mode,
            ),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    try:
        gpus = read_gpu_memory()
    except Exception as exc:
        print(f"ERROR: cannot read GPU status via gpustat/nvidia-smi: {exc}")
        return 1
    plan = plan_dual_probe20(
        gpus,
        requested_7b=args.gpu_7b,
        requested_9b=args.gpu_9b,
        default_util=args.default_gpu_memory_utilization,
        margin_mib=args.gpu_memory_margin_mib,
        run_mode=args.run_mode,
    )
    command = build_probe20_launch_command(
        plan,
        max_workers=args.max_workers,
        monitor_interval_sec=args.monitor_interval_sec,
        run_mode=args.run_mode,
        vllm_conda_env=args.vllm_conda_env,
        vllm_conda_env_7b=args.vllm_conda_env_7b,
        vllm_conda_env_9b=args.vllm_conda_env_9b,
        root=Path(args.root),
    )
    payload = {
        "gpus": gpus,
        "plan": plan,
        "recommended_command": command,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("GPU snapshot:")
        for gpu in sorted(gpus, key=lambda item: item["index"]):
            print(
                f"  GPU {gpu['index']}: used={gpu['used_mib']} MiB "
                f"free={gpu['free_mib']} MiB total={gpu['total_mib']} MiB"
            )
        print()
        print("Recommended plan:")
        for model in [MODEL_9B, MODEL_7B]:
            item = plan[model]
            env_name = (
                args.vllm_conda_env
                or (args.vllm_conda_env_9b if model == MODEL_9B else args.vllm_conda_env_7b)
                or MODEL_DEFAULT_CONDA_ENV[model]
            )
            print(
                f"  {model}: GPU={item['gpu_id']} "
                f"gpu_memory_utilization={item['gpu_memory_utilization']} "
                f"free_mib={item['free_mib']} "
                f"env={env_name}"
            )
        print()
        print("Run this command:")
        print(command)
    return 0


def _cmd_classify(args: argparse.Namespace) -> int:
    print(json.dumps(classify_managed_run(Path(args.managed_dir)), ensure_ascii=False, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ACA_model experiment supervisor helpers.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan-probe20-dual", help="Plan GPUs and memory utilization for dual probe20.")
    plan.add_argument("--gpu-7b", default="auto")
    plan.add_argument("--gpu-9b", default="auto")
    plan.add_argument("--default-gpu-memory-utilization", type=float, default=0.35)
    plan.add_argument("--gpu-memory-margin-mib", type=int, default=3072)
    plan.add_argument("--run-mode", choices=["sequential", "parallel"], default="sequential")
    plan.set_defaults(func=_cmd_plan)

    recommend = sub.add_parser("recommend-probe20-dual", help="Print a copy-paste launch command from GPU status.")
    recommend.add_argument("--gpu-7b", default="auto")
    recommend.add_argument("--gpu-9b", default="auto")
    recommend.add_argument("--default-gpu-memory-utilization", type=float, default=0.35)
    recommend.add_argument("--gpu-memory-margin-mib", type=int, default=3072)
    recommend.add_argument("--max-workers", type=int, default=2)
    recommend.add_argument("--monitor-interval-sec", type=int, default=10)
    recommend.add_argument("--run-mode", choices=["sequential", "parallel"], default="sequential")
    recommend.add_argument("--vllm-conda-env")
    recommend.add_argument("--vllm-conda-env-7b", default=MODEL_DEFAULT_CONDA_ENV[MODEL_7B])
    recommend.add_argument("--vllm-conda-env-9b", default=MODEL_DEFAULT_CONDA_ENV[MODEL_9B])
    recommend.add_argument("--root", default=str(DEFAULT_ROOT))
    recommend.add_argument("--json", action="store_true")
    recommend.set_defaults(func=_cmd_recommend)

    classify = sub.add_parser("classify-run", help="Classify a managed run failure from logs.")
    classify.add_argument("managed_dir")
    classify.set_defaults(func=_cmd_classify)

    args = parser.parse_args()
    raise SystemExit(args.func(args))


if __name__ == "__main__":
    main()
