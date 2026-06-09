from __future__ import annotations

import importlib.util
from pathlib import Path
import json


def _load_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "aca_model_supervisor.py"
    spec = importlib.util.spec_from_file_location("aca_model_supervisor", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_plan_dual_probe20_sequential_reuses_freest_gpu_for_both_models():
    module = _load_module()
    gpus = module.parse_nvidia_smi_memory(
        "\n".join(
            [
                "0, 64750, 81920",
                "1, 48958, 81920",
                "2, 61313, 81920",
                "3, 10000, 81920",
            ]
        )
    )

    plan = module.plan_dual_probe20(gpus, requested_7b="auto", requested_9b="auto", run_mode="sequential")

    assert plan["qwen35-9b"]["gpu_id"] == 3
    assert plan["qwen25-coder-7b"]["gpu_id"] == 3


def test_plan_dual_probe20_parallel_assigns_9b_to_freest_gpu_and_7b_to_second_freest():
    module = _load_module()
    gpus = module.parse_nvidia_smi_memory(
        "\n".join(
            [
                "0, 64750, 81920",
                "1, 48958, 81920",
                "2, 61313, 81920",
                "3, 10000, 81920",
            ]
        )
    )

    plan = module.plan_dual_probe20(gpus, requested_7b="auto", requested_9b="auto", run_mode="parallel")

    assert plan["qwen35-9b"]["gpu_id"] == 3
    assert plan["qwen25-coder-7b"]["gpu_id"] == 1


def test_plan_dual_probe20_respects_9b_minimum_gpu_memory_utilization():
    module = _load_module()
    gpus = module.parse_nvidia_smi_memory("2, 61313, 81920")

    plan = module.plan_dual_probe20(gpus, requested_7b="auto", requested_9b="2", default_util=0.35, margin_mib=3072)

    assert plan["qwen35-9b"]["gpu_id"] == 2
    assert plan["qwen35-9b"]["gpu_memory_utilization"] == 0.30


def test_classify_vllm_failure_detects_gpu_memory_insufficient():
    module = _load_module()
    text = (
        "ValueError: Free memory on device cuda:0 (18.79/79.15 GiB) on startup "
        "is less than desired GPU memory utilization (0.35, 27.7 GiB)."
    )

    diagnosis = module.classify_vllm_failure(text)

    assert diagnosis["reason"] == "GPU_MEMORY_INSUFFICIENT"
    assert "desired GPU memory utilization" in diagnosis["evidence"]


def test_classify_vllm_failure_detects_kv_cache_insufficient():
    module = _load_module()
    text = (
        "ValueError: To serve at least one request with the models's max seq len (8192), "
        "(0.44 GiB KV cache is needed, which is larger than the available KV cache memory (0.17 GiB)."
    )

    diagnosis = module.classify_vllm_failure(text)

    assert diagnosis["reason"] == "KV_CACHE_INSUFFICIENT"
    assert "available KV cache memory" in diagnosis["evidence"]


def test_classify_vllm_failure_detects_no_cache_blocks():
    module = _load_module()
    text = "ValueError: No available memory for the cache blocks. Try increasing `gpu_memory_utilization`."

    diagnosis = module.classify_vllm_failure(text)

    assert diagnosis["reason"] == "KV_CACHE_INSUFFICIENT"
    assert "No available memory for the cache blocks" in diagnosis["evidence"]


def test_classify_vllm_failure_detects_model_env_incompatible():
    module = _load_module()
    text = "KeyError: 'layers.0.linear_attn.A_log'"

    diagnosis = module.classify_vllm_failure(text)

    assert diagnosis["reason"] == "MODEL_ENV_INCOMPATIBLE"
    assert "linear_attn.A_log" in diagnosis["evidence"]


def test_classify_vllm_failure_detects_torch_oom():
    module = _load_module()
    text = "torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 224.00 MiB."

    diagnosis = module.classify_vllm_failure(text)

    assert diagnosis["reason"] == "GPU_MEMORY_INSUFFICIENT"
    assert "OutOfMemoryError" in diagnosis["evidence"]


def test_plan_dual_probe20_does_not_recommend_below_model_minimum_utilization():
    module = _load_module()
    gpus = module.parse_nvidia_smi_memory("2, 61313, 81920")

    plan = module.plan_dual_probe20(gpus, requested_7b="2", requested_9b="auto", default_util=0.35, margin_mib=3072)

    assert plan["qwen25-coder-7b"]["gpu_memory_utilization"] >= 0.40


def test_parse_gpustat_json_memory():
    module = _load_module()
    payload = {
        "gpus": [
            {"index": 0, "memory.used": 60000, "memory.total": 81920},
            {"index": 1, "memory.used": 10000, "memory.total": 81920},
        ]
    }

    gpus = module.parse_gpustat_json(json.dumps(payload))

    assert gpus == [
        {"index": 0, "used_mib": 60000, "total_mib": 81920, "free_mib": 21920},
        {"index": 1, "used_mib": 10000, "total_mib": 81920, "free_mib": 71920},
    ]


def test_build_probe20_launch_command_contains_explicit_recommended_parameters():
    module = _load_module()
    plan = {
        "qwen25-coder-7b": {"gpu_id": 2, "gpu_memory_utilization": 0.25},
        "qwen35-9b": {"gpu_id": 1, "gpu_memory_utilization": 0.35},
    }

    command = module.build_probe20_launch_command(plan, max_workers=2, monitor_interval_sec=10, run_mode="sequential")

    assert "GPU_7B=2" in command
    assert "GPU_9B=1" in command
    assert "MODEL_RUN_MODE=sequential" in command
    assert "CONTINUE_ON_MODEL_FAILURE=1" in command
    assert "LLM_MAX_TOKENS_7B=2048" in command
    assert "LLM_MAX_TOKENS_9B=2048" in command
    assert "MAX_MODEL_LEN_7B=8192" in command
    assert "MAX_MODEL_LEN_9B=8192" in command
    assert "VLLM_CONDA_ENV_7B=ACAvllms124" in command
    assert "VLLM_CONDA_ENV_9B=vllm017_full" in command
    assert "GPU_MEMORY_UTILIZATION_7B=0.25" in command
    assert "GPU_MEMORY_UTILIZATION_9B=0.35" in command
    assert "MAX_WORKERS=2" in command
    assert "bash scripts/run_gtor4_probe20_dual_progress.sh" in command
