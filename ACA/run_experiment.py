#!/usr/bin/env python3
"""Unified ACA experiment runner with task-level scheduling.

Each task is exactly one `(method, submission)` pair. Serial mode is simply
`max_workers=1`; parallel mode reuses the same scheduler with a larger pool.
"""

import argparse
import dataclasses
import json
import os
import shutil
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_THIS_FILE = Path(__file__).resolve()
_ACA_ROOT = _THIS_FILE.parent
_WORKSPACE_ROOT = _ACA_ROOT.parent
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

from ACA.agent.shared.prompt_templates import (
    QWEN_OUTPUT_CONSTRAINT_TEXT,
    SEED_CONTRACT_CLARIFICATION_TEXT,
    should_apply_qwen_output_constraint,
)

@dataclasses.dataclass(frozen=True)
class MethodRuntimeConfig:
    cases_per_round: int = 5
    generator_seeds_per_round: int = 5
    max_rounds: int = 1
    max_total_cases: int = 5
    stop_on_first_hack: bool = True
    validator_timeout_s: float = 30.0
    ref_timeout_s: float = 30.0
    student_timeout_s: float = 30.0
    generator_compile_timeout_s: float = 2.0
    generator_run_timeout_s: float = 2.0
    llm_model: Optional[str] = None
    llm_temperature: float = 0.2
    llm_max_tokens: int = 16383
    llm_retry_count: int = 0
    coverage_union_scope: str = "per_round"
    seed_base: int = 0
    seed_list: Optional[List[int]] = None
    output_truncation_limit: int = 500
    max_case_bytes: int = 262144
    max_generator_code_bytes: int = 262144
    no_tool_call_limit: int = 10
    qwen_output_constraint_mode: str = "auto"
    qwen_output_constraint_text: str = QWEN_OUTPUT_CONSTRAINT_TEXT
    seed_contract_clarification_text: str = SEED_CONTRACT_CLARIFICATION_TEXT
    gtor_prompt_profile: str = "legacy"


@dataclasses.dataclass(frozen=True)
class MethodSpec:
    canonical_method: str
    legacy_method: str
    method_family: str
    method_contract_version: str = "v1"
    input_method: Optional[str] = None
    generator_mode: bool = False
    direct_base_method: Optional[str] = None
    runtime_config: MethodRuntimeConfig = dataclasses.field(default_factory=MethodRuntimeConfig)


CANONICAL_METHOD_REGISTRY: dict[str, MethodSpec] = {
    "Base": MethodSpec(
        canonical_method="Base",
        legacy_method="L0",
        method_family="direct_case_generation",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=1,
            max_total_cases=5,
        ),
    ),
    "BaseC": MethodSpec(
        canonical_method="BaseC",
        legacy_method="L1",
        method_family="coverage_guided_generation",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=1,
            max_total_cases=5,
        ),
    ),
    "ITER": MethodSpec(
        canonical_method="ITER",
        legacy_method="V0",
        method_family="iterative_coverage_generation",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=5,
            max_total_cases=25,
        ),
    ),
    "Agent": MethodSpec(
        canonical_method="Agent",
        legacy_method="R1",
        method_family="feedback_agent_generation",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=5,
            max_total_cases=25,
        ),
    ),
    "BaseG": MethodSpec(
        canonical_method="BaseG",
        legacy_method="G0",
        method_family="generator_case_generation",
        method_contract_version="gtor_v1",
        generator_mode=True,
        direct_base_method="Base",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=1,
            max_total_cases=5,
            seed_list=[0, 1, 2, 3, 4],
        ),
    ),
    "BaseCG": MethodSpec(
        canonical_method="BaseCG",
        legacy_method="G1",
        method_family="coverage_guided_generator_generation",
        method_contract_version="gtor_v1",
        generator_mode=True,
        direct_base_method="BaseC",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=1,
            max_total_cases=5,
            seed_list=[0, 1, 2, 3, 4],
        ),
    ),
    "ITERG": MethodSpec(
        canonical_method="ITERG",
        legacy_method="ITERG",
        method_family="iterative_coverage_generator_generation",
        method_contract_version="gtor_v1",
        generator_mode=True,
        direct_base_method="ITER",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=5,
            max_total_cases=25,
            seed_list=[0, 1, 2, 3, 4],
        ),
    ),
    "AgentG": MethodSpec(
        canonical_method="AgentG",
        legacy_method="AgentG",
        method_family="feedback_generator_generation",
        method_contract_version="gtor_v1",
        generator_mode=True,
        direct_base_method="Agent",
        runtime_config=MethodRuntimeConfig(
            cases_per_round=5,
            generator_seeds_per_round=5,
            max_rounds=5,
            max_total_cases=25,
            seed_list=[0, 1, 2, 3, 4],
        ),
    ),
}

METHOD_ALIASES = {
    "Base": "Base",
    "BaseC": "BaseC",
    "ITER": "ITER",
    "Agent": "Agent",
    "BaseG": "BaseG",
    "Base-G": "BaseG",
    "BaseCG": "BaseCG",
    "BaseC-G": "BaseCG",
    "ITERG": "ITERG",
    "ITER-G": "ITERG",
    "AgentG": "AgentG",
    "Agent-G": "AgentG",
    "L0": "Base",
    "L1": "BaseC",
    "V0": "ITER",
    "R1": "Agent",
    "G0": "BaseG",
    "G1": "BaseCG",
}


def add_sys_paths():
    whn = Path("/data/whn")
    if str(whn) not in sys.path:
        sys.path.insert(0, str(whn))


def resolve_strategy_runner(strategy: str):
    """Return `(config, process_one_submission)` for a strategy."""
    if strategy == "R1":
        from ACA.agent.r_family.config import R1Config
        from ACA.agent.r_family.runner import process_one_submission

        return R1Config(), process_one_submission
    if strategy == "R1.1":
        from ACA.agent.r_family.config import R1_1Config
        from ACA.agent.r_family.runner import process_one_submission

        return R1_1Config(), process_one_submission
    if strategy == "L0":
        from ACA.agent.l_family.config import L0Config
        from ACA.agent.l_family.runner import process_one_submission

        return L0Config(), process_one_submission
    if strategy == "L1":
        from ACA.agent.l_family.config import L1Config
        from ACA.agent.l_family.runner import process_one_submission

        return L1Config(), process_one_submission
    if strategy == "V0":
        from ACA.agent.v_family.config import V0Config
        from ACA.agent.v_family.runner import process_one_submission

        return V0Config(), process_one_submission
    if strategy == "G0":
        from ACA.agent.g_family.config import G0Config
        from ACA.agent.g_family.runner import process_one_submission

        return G0Config(), process_one_submission
    if strategy == "G1":
        from ACA.agent.g_family.config import G1Config
        from ACA.agent.g_family.runner import process_one_submission

        return G1Config(), process_one_submission
    if strategy == "ITERG":
        from ACA.agent.g_family.config import ITERGConfig
        from ACA.agent.g_family.runner import process_one_submission

        return ITERGConfig(), process_one_submission
    if strategy == "AgentG":
        from ACA.agent.r_family.config import AgentGConfig
        from ACA.agent.r_family.runner import process_one_submission

        return AgentGConfig(), process_one_submission
    raise ValueError(f"Unknown strategy: {strategy}")


def resolve_requested_methods(
    methods_arg,
    strategy_arg,
) -> List[MethodSpec]:
    if methods_arg and strategy_arg:
        raise ValueError("--methods and --strategy cannot be used together.")

    raw_arg = methods_arg if methods_arg else strategy_arg
    if not raw_arg:
        raise ValueError("One of --methods or --strategy is required.")

    if strategy_arg and not methods_arg:
        print("--strategy is deprecated; use --methods instead.", file=sys.stderr)

    resolved_methods: list[MethodSpec] = []
    if isinstance(raw_arg, list):
        raw_tokens = []
        for item in raw_arg:
            raw_tokens.extend(part.strip() for part in str(item).split(",") if part.strip())
    else:
        raw_tokens = [part.strip() for part in str(raw_arg).split(",") if part.strip()]
    for token in raw_tokens:
        canonical_name = METHOD_ALIASES.get(token)
        if canonical_name is None:
            allowed = ", ".join(CANONICAL_METHOD_REGISTRY)
            raise ValueError(f"Unknown method '{token}'. Allowed canonical methods: {allowed}; aliases: L0,L1,V0,R1,G0,G1,Base-G,BaseC-G,ITER-G,Agent-G.")
        resolved_methods.append(
            dataclasses.replace(
                CANONICAL_METHOD_REGISTRY[canonical_name],
                input_method=token,
            )
        )
    return resolved_methods


def method_metadata(method: MethodSpec) -> dict:
    payload = {
        "input_method": method.input_method or method.canonical_method,
        "method": method.canonical_method,
        "legacy_method": method.legacy_method,
        "method_family": method.method_family,
        "method_contract_version": method.method_contract_version,
        "runtime_config": dataclasses.asdict(method.runtime_config),
    }
    if method.generator_mode:
        payload["generator_mode"] = True
    if method.direct_base_method:
        payload["direct_base_method"] = method.direct_base_method
    return payload


def apply_runtime_config(config, method: MethodSpec) -> None:
    runtime = method.runtime_config
    setattr(config, "stop_on_first_hack", runtime.stop_on_first_hack)
    if runtime.llm_model and hasattr(config, "model"):
        config.model = runtime.llm_model
    if hasattr(config, "test_input_count"):
        config.test_input_count = runtime.cases_per_round
    if hasattr(config, "num_seeds"):
        config.num_seeds = runtime.generator_seeds_per_round
    if hasattr(config, "max_iterations"):
        config.max_iterations = runtime.max_rounds
    if hasattr(config, "patience") and runtime.max_rounds > 1:
        config.patience = min(getattr(config, "patience", runtime.max_rounds), runtime.max_rounds)
    if hasattr(config, "run_timeout"):
        config.run_timeout = runtime.student_timeout_s
    if hasattr(config, "generator_timeout"):
        config.generator_timeout = runtime.generator_run_timeout_s
    if hasattr(config, "generator_max_output_bytes"):
        config.generator_max_output_bytes = runtime.max_case_bytes
    if hasattr(config, "generator_max_code_bytes"):
        config.generator_max_code_bytes = runtime.max_generator_code_bytes
    if hasattr(config, "seed_base"):
        config.seed_base = runtime.seed_base
    if hasattr(config, "seed_list"):
        config.seed_list = list(runtime.seed_list) if runtime.seed_list is not None else None
    if hasattr(config, "no_tool_call_limit"):
        config.no_tool_call_limit = runtime.no_tool_call_limit
    if hasattr(config, "temperature"):
        config.temperature = runtime.llm_temperature
    if hasattr(config, "max_tokens"):
        config.max_tokens = runtime.llm_max_tokens
    gtor_generator = bool(method.generator_mode and method.method_contract_version == "gtor_v1")
    if hasattr(config, "qwen_output_constraint_mode"):
        config.qwen_output_constraint_mode = runtime.qwen_output_constraint_mode
    if hasattr(config, "qwen_output_constraint_text"):
        config.qwen_output_constraint_text = runtime.qwen_output_constraint_text
    if hasattr(config, "seed_contract_clarification_text"):
        config.seed_contract_clarification_text = runtime.seed_contract_clarification_text
    prompt_profile_allows_qwen_suffix = runtime.gtor_prompt_profile != "small_model_minimal"
    if hasattr(config, "qwen_output_constraint_applied"):
        config.qwen_output_constraint_applied = gtor_generator and prompt_profile_allows_qwen_suffix and should_apply_qwen_output_constraint(
            runtime.qwen_output_constraint_mode,
            getattr(config, "model", None),
        )
    if hasattr(config, "seed_contract_clarification_applied"):
        config.seed_contract_clarification_applied = gtor_generator and prompt_profile_allows_qwen_suffix and should_apply_qwen_output_constraint(
            runtime.qwen_output_constraint_mode,
            getattr(config, "model", None),
        )
    if hasattr(config, "gtor_prompt_profile"):
        config.gtor_prompt_profile = runtime.gtor_prompt_profile


def override_method_runtime(
    methods: List[MethodSpec],
    *,
    generator_seeds_per_round: Optional[int] = None,
    max_rounds: Optional[int] = None,
    llm_model: Optional[str] = None,
    llm_temperature: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
    qwen_output_constraint_mode: Optional[str] = None,
    gtor_prompt_profile: Optional[str] = None,
) -> List[MethodSpec]:
    overridden: list[MethodSpec] = []
    for method in methods:
        runtime = method.runtime_config
        updates: dict = {}

        if generator_seeds_per_round is not None and method.generator_mode:
            seed_count = int(generator_seeds_per_round)
            updates["generator_seeds_per_round"] = seed_count
            updates["cases_per_round"] = seed_count
            updates["seed_list"] = list(range(seed_count))
            updates["max_total_cases"] = seed_count * runtime.max_rounds
        if max_rounds is not None and method.generator_mode:
            round_count = int(max_rounds)
            updates["max_rounds"] = round_count
            current_seed_count = int(updates.get("generator_seeds_per_round", runtime.generator_seeds_per_round))
            updates["max_total_cases"] = current_seed_count * round_count
        if llm_model is not None:
            updates["llm_model"] = llm_model
        if llm_temperature is not None:
            updates["llm_temperature"] = llm_temperature
        if llm_max_tokens is not None:
            updates["llm_max_tokens"] = llm_max_tokens
        if qwen_output_constraint_mode is not None and method.generator_mode:
            updates["qwen_output_constraint_mode"] = qwen_output_constraint_mode
        if gtor_prompt_profile is not None and method.generator_mode:
            updates["gtor_prompt_profile"] = gtor_prompt_profile

        if updates:
            runtime = dataclasses.replace(runtime, **updates)
            method = dataclasses.replace(method, runtime_config=runtime)
        overridden.append(method)
    return overridden


def json_dump(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    tmp_path.replace(path)


def load_json(path: Path) -> dict | list:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _with_method_metadata(payload: dict, method: MethodSpec) -> dict:
    enriched = dict(payload)
    enriched.update(method_metadata(method))
    if "strategy" in enriched:
        enriched["strategy"] = method.canonical_method
    return enriched


def _augment_trace_json(path: Path, method: MethodSpec) -> None:
    try:
        payload = load_json(path)
    except (OSError, json.JSONDecodeError):
        return

    trajectory_path = path.with_name("trajectory.jsonl")
    seed_policy_fields = _collect_generator_seed_policy_fields(trajectory_path) if method.generator_mode else {}

    if isinstance(payload, dict):
        enriched = _with_method_metadata(payload, method)
        if seed_policy_fields:
            enriched.update(seed_policy_fields)
        json_dump(path, enriched)
        return

    if isinstance(payload, list):
        metadata_entry = {
            "index": -1,
            "role": "metadata",
            **method_metadata(method),
            **seed_policy_fields,
            "strategy": method.canonical_method,
        }
        json_dump(path, payload + [metadata_entry])


def _augment_trajectory_jsonl(path: Path, method: MethodSpec) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    rewritten: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            rewritten.append(line)
            continue
        if isinstance(payload, dict):
            payload = _with_method_metadata(payload, method)
        rewritten.append(json.dumps(payload, ensure_ascii=False))

    if rewritten:
        path.write_text("\n".join(rewritten) + "\n", encoding="utf-8")


def _collect_generator_result_fields(trajectory_path: Path) -> dict:
    try:
        lines = trajectory_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    generator_runs = []
    generated_inputs = []
    sandbox_results = []
    extraction_status = None
    compile_status = None
    seed_list = None
    configured_seed_list = None
    actual_seed_list = None
    model_requested_seed_list = None
    seed_policy = None
    seed_override_applied = False

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("event_type")
        if event_type == "generator_code_extracted":
            extraction_status = payload.get("extraction_status")
        elif event_type == "generator_compile":
            compile_status = payload.get("compile_status")
        elif event_type == "generator_code_built":
            seed_list = payload.get("seed_list")
            configured_seed_list = payload.get("configured_seed_list", configured_seed_list)
            actual_seed_list = payload.get("actual_seed_list", actual_seed_list)
            if payload.get("model_requested_seed_list") is not None:
                model_requested_seed_list = payload.get("model_requested_seed_list")
            seed_policy = payload.get("seed_policy", seed_policy)
            seed_override_applied = bool(payload.get("seed_override_applied")) or seed_override_applied
        elif event_type == "generator_run":
            generator_runs.append(payload)
        elif event_type == "generated_input":
            generated_inputs.append(payload)
        elif event_type == "sandbox_result":
            sandbox_results.append(payload)

    seed_count = len(seed_list or [])
    runtime_success_count = sum(1 for item in generator_runs if item.get("generator_status") == "GEN_OK")
    runtime_error_count = sum(1 for item in generator_runs if item.get("generator_status") == "GEN_RUNTIME_ERROR")
    timeout_count = sum(1 for item in generator_runs if item.get("generator_status") == "GEN_TIMEOUT")
    no_inputs_generated_count = 1 if not generated_inputs else 0
    duplicate_input_count = sum(1 for item in generated_inputs if item.get("duplicate_exact"))
    unique_input_count = len(generated_inputs) - duplicate_input_count
    duplicate_rate = round(duplicate_input_count / len(generated_inputs), 4) if generated_inputs else 0.0
    raw_generated_sample_count = len(sandbox_results)
    unique_sandbox_results, duplicate_generated_sample_count = _deduplicate_sandbox_results(sandbox_results)
    valid_generated_count = sum(1 for item in unique_sandbox_results if item.get("valid") is True)
    invalid_generated_count = len(unique_sandbox_results) - valid_generated_count
    valid_rate = round(valid_generated_count / len(unique_sandbox_results), 4) if unique_sandbox_results else 0.0
    breakthrough_count = sum(1 for item in unique_sandbox_results if item.get("breakthrough") is True)
    tcc_exist = 1 if breakthrough_count > 0 else 0
    tcc = round(breakthrough_count / len(unique_sandbox_results), 4) if unique_sandbox_results else 0.0
    coverage_hit_but_ac = sum(
        1
        for item in unique_sandbox_results
        if item.get("status") == "AC" and bool(item.get("newly_covered_targets"))
    )

    return {
        "generator_extract_success": extraction_status == "GENERATOR_OK",
        "generator_extract_status": extraction_status,
        "generator_compile_success": compile_status == "GENERATOR_COMPILE_OK",
        "generator_compile_status": compile_status,
        "seed_count": seed_count,
        "generator_runtime_success_count": runtime_success_count,
        "generator_runtime_error_count": runtime_error_count,
        "generator_timeout_count": timeout_count,
        "no_inputs_generated_count": no_inputs_generated_count,
        "raw_generated_input_count": len(generated_inputs),
        "raw_generated_sample_count": raw_generated_sample_count,
        "duplicate_generated_sample_count": duplicate_generated_sample_count,
        "unique_input_count": unique_input_count,
        "duplicate_input_count": duplicate_input_count,
        "duplicate_rate": duplicate_rate,
        "valid_generated_count": valid_generated_count,
        "invalid_generated_count": invalid_generated_count,
        "valid_rate": valid_rate,
        "TCC_exist": tcc_exist,
        "TCC": tcc,
        "coverage_progress": len({
            ln
            for item in unique_sandbox_results
            for ln in (item.get("newly_covered_targets") or [])
        }),
        "coverage_hit_but_ac": coverage_hit_but_ac,
        "configured_seed_list": configured_seed_list,
        "actual_seed_list": actual_seed_list or seed_list,
        "model_requested_seed_list": model_requested_seed_list,
        "seed_policy": seed_policy or "system_fixed",
        "seed_override_applied": seed_override_applied,
    }


def _collect_generator_seed_policy_fields(trajectory_path: Path) -> dict:
    generator_fields = _collect_generator_result_fields(trajectory_path)
    keys = [
        "configured_seed_list",
        "actual_seed_list",
        "model_requested_seed_list",
        "seed_policy",
        "seed_override_applied",
    ]
    return {key: generator_fields.get(key) for key in keys if key in generator_fields}


def _deduplicate_sandbox_results(sandbox_results: list[dict]) -> tuple[list[dict], int]:
    unique_results: list[dict] = []
    seen_keys: set[str] = set()
    duplicate_count = 0

    for item in sandbox_results:
        if item.get("input_hash"):
            key = f"hash::{item['input_hash']}"
        elif item.get("test_input") or item.get("input_text"):
            key = f"text::{item.get('test_input') or item.get('input_text')}"
        elif item.get("input_id"):
            key = f"id::{item['input_id']}"
        else:
            key = ""
        if key and key in seen_keys:
            duplicate_count += 1
            continue
        if key:
            seen_keys.add(key)
        unique_results.append(item)

    return unique_results, duplicate_count


def _collect_common_result_fields(trajectory_path: Path) -> dict:
    try:
        lines = trajectory_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    requested_sample_count = 0
    sandbox_results = []

    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event_type = payload.get("event_type")
        if event_type == "inputs_extracted":
            requested_sample_count += len(payload.get("inputs") or [])
        elif event_type == "sandbox_result":
            sandbox_results.append(payload)

    raw_sample_count = len(sandbox_results)
    unique_sandbox_results, duplicate_sample_count = _deduplicate_sandbox_results(sandbox_results)
    sample_count = len(unique_sandbox_results)
    valid_sample_count = sum(1 for item in unique_sandbox_results if item.get("valid") is True)
    invalid_sample_count = sample_count - valid_sample_count
    valid_rate = round(valid_sample_count / sample_count, 4) if sample_count else 0.0
    breakthrough_count = sum(1 for item in unique_sandbox_results if item.get("breakthrough") is True)
    tcc_exist = 1 if breakthrough_count > 0 else 0
    tcc = round(breakthrough_count / sample_count, 4) if sample_count else 0.0
    coverage_progress = len({
        ln
        for item in unique_sandbox_results
        for ln in (item.get("newly_covered_targets") or [])
    })
    coverage_hit_but_ac = sum(
        1
        for item in unique_sandbox_results
        if item.get("status") == "AC" and bool(item.get("newly_covered_targets"))
    )

    return {
        "requested_sample_count": requested_sample_count,
        "raw_sample_count": raw_sample_count,
        "duplicate_sample_count": duplicate_sample_count,
        "sample_count": sample_count,
        "valid_sample_count": valid_sample_count,
        "invalid_sample_count": invalid_sample_count,
        "valid_rate": valid_rate,
        "TCC_exist": tcc_exist,
        "TCC": tcc,
        "coverage_progress": coverage_progress,
        "coverage_hit_but_ac": coverage_hit_but_ac,
    }


def _materialize_generator_artifacts(task_dir: Path, method: MethodSpec) -> None:
    trajectory_path = task_dir / "trajectory.jsonl"
    if not trajectory_path.exists():
        return

    prompt_blocks: list[str] = []
    raw_response_blocks: list[str] = []
    code_rounds: list[dict] = []
    compile_rounds: list[dict] = []
    seed_records: list[dict] = []
    generated_cases: list[dict] = []
    failure_counts: dict[str, int] = {}

    for line in trajectory_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type == "prompt_built":
            prompt_blocks.append(
                f"=== iteration {event.get('iteration')} ===\n{event.get('prompt_text', '')}\n"
            )
        elif event_type == "llm_response":
            raw_response_blocks.append(
                f"=== iteration {event.get('iteration')} ===\n{event.get('raw_response', '')}\n"
            )
        elif event_type == "generator_code_extracted":
            code_rounds.append({
                "iteration": event.get("iteration"),
                "extraction_status": event.get("extraction_status"),
                "code_hash": event.get("code_hash"),
                "code_preview": event.get("code_preview"),
                "code_text": event.get("code_text"),
            })
        elif event_type == "generator_compile":
            compile_rounds.append(dict(event))
            status = event.get("compile_status")
            if status:
                failure_counts[status] = failure_counts.get(status, 0) + int(not event.get("compile_ok", False))
        elif event_type == "generator_run":
            seed_records.append(dict(event))
            status = event.get("generator_status")
            if status and status != "GEN_OK":
                failure_counts[status] = failure_counts.get(status, 0) + 1
        elif event_type == "generated_input":
            generated_cases.append(dict(event))
            if event.get("duplicate_exact"):
                failure_counts["DUPLICATE_INPUT"] = failure_counts.get("DUPLICATE_INPUT", 0) + 1
        elif event_type == "sandbox_result":
            if event.get("valid") is False:
                failure_counts["INVALID_GENERATED_CASE"] = failure_counts.get("INVALID_GENERATED_CASE", 0) + 1

    if prompt_blocks:
        (task_dir / "generator_prompt.txt").write_text("\n".join(prompt_blocks), encoding="utf-8")
    if raw_response_blocks:
        (task_dir / "generator_raw_response.txt").write_text("\n".join(raw_response_blocks), encoding="utf-8")
    if code_rounds:
        latest_code = code_rounds[-1].get("code_text") or ""
        (task_dir / "generator_code.py").write_text(latest_code, encoding="utf-8")
        for round_info in code_rounds:
            iteration = round_info.get("iteration")
            code_text = round_info.get("code_text")
            if iteration is None or code_text is None:
                continue
            (task_dir / f"generator_code_round_{iteration}.py").write_text(code_text, encoding="utf-8")
    else:
        placeholder = (
            "# No generator code was extracted for this task.\n"
            "# This placeholder preserves the expected artifact layout for parse-failed generator runs.\n"
        )
        (task_dir / "generator_code.py").write_text(placeholder, encoding="utf-8")
        (task_dir / "generator_code_round_0.py").write_text(placeholder, encoding="utf-8")
    json_dump(
        task_dir / "generator_compile_status.json",
        {"rounds": compile_rounds, **({"latest": compile_rounds[-1]} if compile_rounds else {})},
    )
    with (task_dir / "seed_records.jsonl").open("w", encoding="utf-8") as fh:
        for record in seed_records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    with (task_dir / "generated_cases.jsonl").open("w", encoding="utf-8") as fh:
        for record in generated_cases:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    json_dump(
        task_dir / "generator_failure_modes.json",
        {
            "method": method.canonical_method,
            "legacy_method": method.legacy_method,
            "failure_modes": failure_counts,
        },
    )


def _materialize_direct_artifacts(task_dir: Path, method: MethodSpec) -> None:
    trajectory_path = task_dir / "trajectory.jsonl"
    if not trajectory_path.exists():
        return

    prompt_blocks: list[str] = []
    raw_response_blocks: list[str] = []

    for line in trajectory_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type == "prompt_built":
            prompt_blocks.append(
                f"=== iteration {event.get('iteration')} ===\n{event.get('prompt_text', '')}\n"
            )
        elif event_type == "llm_response":
            raw_response_blocks.append(
                f"=== iteration {event.get('iteration')} ===\n{event.get('raw_response', '')}\n"
            )

    if prompt_blocks:
        (task_dir / "prompt.txt").write_text("\n".join(prompt_blocks), encoding="utf-8")
    if raw_response_blocks:
        (task_dir / "raw_response.txt").write_text("\n".join(raw_response_blocks), encoding="utf-8")


def _ensure_placeholder_trace(task_dir: Path, method: MethodSpec, submission_id: str) -> None:
    trace_json_path = task_dir / "trace.json"
    if not trace_json_path.exists():
        json_dump(
            trace_json_path,
            {
                **method_metadata(method),
                "strategy": method.canonical_method,
                "submission_id": submission_id,
                "trace_status": "missing_runner_trace",
                "conversation": [],
            },
        )

    trace_md_path = task_dir / "trace.md"
    if not trace_md_path.exists():
        trace_md_path.write_text(
            "\n".join(
                [
                    f"# Trace: {submission_id}",
                    "",
                    f"- Method: {method.canonical_method}",
                    f"- Legacy method: {method.legacy_method}",
                    "- Trace status: missing_runner_trace",
                    "",
                ]
            ),
            encoding="utf-8",
        )


def make_run_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_tasks(methods: List[MethodSpec], submissions: list) -> list[Tuple[MethodSpec, object]]:
    return [(method, rec) for method in methods for rec in submissions]


def filter_submissions(submissions: list, submission_ids: Optional[List[str]] = None) -> list:
    if not submission_ids:
        return list(submissions)
    wanted = {sid.strip() for sid in submission_ids if sid and sid.strip()}
    ordered = [rec for rec in submissions if getattr(rec, "submission_id", None) in wanted]
    return ordered


def task_dir_for(run_root: Path, method: MethodSpec, submission_id: str) -> Path:
    return run_root / "tasks" / method.canonical_method / submission_id


def write_run_config(
    run_root: Path,
    *,
    methods: List[MethodSpec],
    max_workers: int,
    parallel: bool,
    resume: bool,
    run_metadata: Optional[dict],
) -> None:
    payload = {
        "methods": [method.canonical_method for method in methods],
        "input_methods": [method.input_method or method.canonical_method for method in methods],
        "legacy_methods": [method.legacy_method for method in methods],
        "strategies": [method.canonical_method for method in methods],
        "max_workers": max_workers,
        "parallel": parallel,
        "resume": resume,
        "run_id": run_root.name,
    }
    if run_metadata:
        payload.update(run_metadata)
    json_dump(run_root / "config.json", payload)
    json_dump(
        run_root / "method_config_snapshot.json",
        {
            method.canonical_method: dataclasses.asdict(method.runtime_config)
            for method in methods
        },
    )
    json_dump(
        run_root / "method_registry_snapshot.json",
        {
            method.canonical_method: method_metadata(method)
            for method in methods
        },
    )


def _promote_task_artifacts(task_dir: Path, method: MethodSpec, submission_id: str) -> None:
    """Copy runner-private outputs into stable task-local filenames."""
    trajectory_src = task_dir / method.legacy_method / f"{submission_id}.jsonl"
    if trajectory_src.exists():
        shutil.copyfile(trajectory_src, task_dir / "trajectory.jsonl")
        _augment_trajectory_jsonl(task_dir / "trajectory.jsonl", method)

    trace_json_src = task_dir / f"{submission_id}_trace.json"
    if trace_json_src.exists():
        shutil.copyfile(trace_json_src, task_dir / "trace.json")
        _augment_trace_json(task_dir / "trace.json", method)

    trace_md_src = task_dir / f"{submission_id}_trace.md"
    if trace_md_src.exists():
        shutil.copyfile(trace_md_src, task_dir / "trace.md")

    _ensure_placeholder_trace(task_dir, method, submission_id)
    if method.generator_mode:
        _materialize_generator_artifacts(task_dir, method)
    else:
        _materialize_direct_artifacts(task_dir, method)


def _result_payload_from_submission_result(result, method: MethodSpec, task_dir: Optional[Path] = None) -> dict:
    payload = _with_method_metadata(result.to_dict(), method)
    payload["status"] = "success" if not result.error else "failed"
    if task_dir is not None:
        payload.update(_collect_common_result_fields(task_dir / "trajectory.jsonl"))
    if method.generator_mode and task_dir is not None:
        payload.update(_collect_generator_result_fields(task_dir / "trajectory.jsonl"))
    return payload


def _config_payload(config, method: MethodSpec) -> dict:
    if dataclasses.is_dataclass(config):
        payload = dataclasses.asdict(config)
    else:
        payload = {
        key: value
        for key, value in vars(config).items()
        if not key.startswith("_")
        }
    api_key = payload.get("api_key")
    if isinstance(api_key, str) and api_key:
        if len(api_key) <= 8:
            payload["api_key"] = "*" * len(api_key)
        else:
            payload["api_key"] = f"{api_key[:4]}{'*' * max(4, len(api_key) - 8)}{api_key[-4:]}"
    if method.generator_mode:
        configured_seed_list = None
        if payload.get("seed_list"):
            configured_seed_list = [int(seed) for seed in payload.get("seed_list", [])[: payload.get("num_seeds", 5)]]
        elif "seed_base" in payload and "num_seeds" in payload:
            base = int(payload.get("seed_base", 0))
            count = int(payload.get("num_seeds", 5))
            configured_seed_list = list(range(base, base + count))
        payload["configured_seed_list"] = configured_seed_list
        payload["actual_seed_list"] = configured_seed_list
        payload["model_requested_seed_list"] = None
        payload["seed_policy"] = "system_fixed"
        payload["seed_override_applied"] = False
    return _with_method_metadata(payload, method)


def _failed_result_payload(method: MethodSpec, rec, error: str, elapsed_sec: float) -> dict:
    payload = {
        "submission_id": rec.submission_id,
        "pid": rec.pid,
        "source": rec.source,
        "strategy": method.canonical_method,
        "trajectory": [],
        "final_uncovered_lines": list(getattr(rec, "uncovered_effective_lines", [])),
        "terminated_reason": "worker_error",
        "countercases": [],
        "total_newly_covered": 0,
        "total_stagnation": 0,
        "iterations": 0,
        "elapsed_sec": round(elapsed_sec, 3),
        "error": error,
        "status": "failed",
        "stop_reason": "worker_error",
        "first_countercase_round": None,
        "first_countercase_input": None,
    }
    payload.update(method_metadata(method))
    return payload


def _task_status_payload(
    *,
    method: MethodSpec,
    rec,
    status: str,
    task_dir: Path,
    elapsed_sec: float,
    skipped: bool,
    terminated_reason: Optional[str] = None,
    stop_reason: Optional[str] = None,
    error: Optional[str] = None,
) -> dict:
    payload = {
        "status": status,
        "strategy": method.canonical_method,
        "submission_id": rec.submission_id,
        "pid": rec.pid,
        "task_dir": str(task_dir),
        "elapsed_sec": round(elapsed_sec, 3),
        "skipped": skipped,
        "terminated_reason": terminated_reason,
        "stop_reason": stop_reason,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(method_metadata(method))
    return payload


def _load_existing_success(task_dir: Path) -> Optional[dict]:
    status_path = task_dir / "task_status.json"
    result_path = task_dir / "result.json"
    if not status_path.exists() or not result_path.exists():
        return None
    try:
        status_payload = load_json(status_path)
        if isinstance(status_payload, dict) and status_payload.get("status") == "success":
            result_payload = load_json(result_path)
            return {
                "task_status": status_payload,
                "result_payload": result_payload,
                "resumed": True,
            }
    except (OSError, json.JSONDecodeError):
        return None
    return None


def run_one_task(
    *,
    run_root: Path,
    method: MethodSpec,
    rec,
    test_cases: dict,
    descriptions: Optional[Dict[str, str]],
    verbose: bool,
    debug: bool,
    resume: bool,
) -> dict:
    task_dir = task_dir_for(run_root, method, rec.submission_id)
    task_dir.mkdir(parents=True, exist_ok=True)

    if resume:
        existing = _load_existing_success(task_dir)
        if existing is not None:
            return {
                "method": method.canonical_method,
                "legacy_method": method.legacy_method,
                "submission_id": rec.submission_id,
                "pid": rec.pid,
                "task_dir": str(task_dir),
                "task_status": existing["task_status"],
                "result_payload": existing["result_payload"],
                "resumed": True,
            }

    config, process_one_submission = resolve_strategy_runner(method.legacy_method)
    apply_runtime_config(config, method)
    config.verbose = bool(verbose or debug)
    json_dump(
        task_dir / "config.json",
        _config_payload(config, method),
    )
    json_dump(
        task_dir / "task_status.json",
        _task_status_payload(
            method=method,
            rec=rec,
            status="running",
            task_dir=task_dir,
            elapsed_sec=0.0,
            skipped=False,
        ),
    )

    started = time.time()
    try:
        result = process_one_submission(
            rec,
            config,
            test_cases,
            description_html=(descriptions or {}).get(rec.pid, ""),
            verbose=verbose,
            trace_dir=str(task_dir) if debug else "",
            trajectory_dir=str(task_dir),
        )
        elapsed = time.time() - started
        _promote_task_artifacts(task_dir, method, rec.submission_id)
        result_payload = _result_payload_from_submission_result(result, method, task_dir=task_dir)
        json_dump(task_dir / "result.json", result_payload)
        task_status = _task_status_payload(
            method=method,
            rec=rec,
            status="success" if not result.error else "failed",
            task_dir=task_dir,
            elapsed_sec=elapsed,
            skipped=False,
            terminated_reason=result.terminated_reason,
            stop_reason=getattr(result, "stop_reason", None),
            error=result.error,
        )
        json_dump(task_dir / "task_status.json", task_status)
        if result.error:
            json_dump(
                task_dir / "error.json",
                _with_method_metadata({
                    "strategy": method.canonical_method,
                    "submission_id": rec.submission_id,
                    "pid": rec.pid,
                    "terminated_reason": result.terminated_reason,
                    "error": result.error,
                }, method),
            )
        return {
            "method": method.canonical_method,
            "legacy_method": method.legacy_method,
            "submission_id": rec.submission_id,
            "pid": rec.pid,
            "task_dir": str(task_dir),
            "task_status": task_status,
            "result_payload": result_payload,
            "resumed": False,
        }
    except Exception as exc:
        elapsed = time.time() - started
        _promote_task_artifacts(task_dir, method, rec.submission_id)
        error_text = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        result_payload = _failed_result_payload(method, rec, error_text, elapsed)
        json_dump(task_dir / "result.json", result_payload)
        json_dump(
            task_dir / "error.json",
            _with_method_metadata({
                "strategy": method.canonical_method,
                "submission_id": rec.submission_id,
                "pid": rec.pid,
                "error": error_text,
                "traceback": traceback.format_exc(),
            }, method),
        )
        task_status = _task_status_payload(
            method=method,
            rec=rec,
            status="failed",
            task_dir=task_dir,
            elapsed_sec=elapsed,
            skipped=False,
            terminated_reason="worker_error",
            stop_reason="worker_error",
            error=error_text,
        )
        json_dump(task_dir / "task_status.json", task_status)
        return {
            "method": method.canonical_method,
            "legacy_method": method.legacy_method,
            "submission_id": rec.submission_id,
            "pid": rec.pid,
            "task_dir": str(task_dir),
            "task_status": task_status,
            "result_payload": result_payload,
            "resumed": False,
        }


def aggregate_run(run_root: Path, task_records: list[dict]) -> None:
    run_matrix = []
    failure_modes: dict[str, int] = {}
    summary = {
        "run_id": run_root.name,
        "total_tasks": len(task_records),
        "completed_tasks": 0,
        "successful_tasks": 0,
        "failed_tasks": 0,
        "skipped_tasks": 0,
        "countercase_tasks": 0,
        "elapsed_sec_total": 0.0,
        "methods": {},
    }

    for item in task_records:
        result_payload = item["result_payload"]
        task_status = item["task_status"]
        method = item["method"]
        legacy_method = item["legacy_method"]
        task_state = task_status.get("status")
        terminated_reason = result_payload.get("terminated_reason")
        elapsed = float(result_payload.get("elapsed_sec", 0.0) or 0.0)

        method_bucket = summary["methods"].setdefault(
            method,
            {
                "tasks": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "countercases": 0,
                "legacy_method": legacy_method,
            },
        )
        method_bucket["tasks"] += 1
        summary["completed_tasks"] += 1
        summary["elapsed_sec_total"] += elapsed

        if item.get("resumed"):
            summary["skipped_tasks"] += 1
            method_bucket["skipped"] += 1

        if task_state == "success":
            summary["successful_tasks"] += 1
            method_bucket["success"] += 1
        else:
            summary["failed_tasks"] += 1
            method_bucket["failed"] += 1

        if result_payload.get("countercases"):
            summary["countercase_tasks"] += 1
            method_bucket["countercases"] += 1

        failure_modes[terminated_reason or "unknown"] = failure_modes.get(terminated_reason or "unknown", 0) + 1
        run_matrix.append(
            {
                "input_method": task_status.get("input_method"),
                "method": method,
                "legacy_method": legacy_method,
                "strategy": method,
                "submission_id": item["submission_id"],
                "pid": item["pid"],
                "status": task_state,
                "resumed": bool(item.get("resumed")),
                "terminated_reason": terminated_reason,
                "stop_reason": result_payload.get("stop_reason"),
                "countercases": len(result_payload.get("countercases", [])),
                "first_countercase_round": result_payload.get("first_countercase_round"),
                "first_countercase_input": result_payload.get("first_countercase_input"),
                "iterations": result_payload.get("iterations", 0),
                "elapsed_sec": elapsed,
                "task_dir": item["task_dir"],
                "result_path": str(Path(item["task_dir"]) / "result.json"),
                "trajectory_path": str(Path(item["task_dir"]) / "trajectory.jsonl"),
                "trace_json_path": str(Path(item["task_dir"]) / "trace.json"),
                "trace_md_path": str(Path(item["task_dir"]) / "trace.md"),
                "error": result_payload.get("error"),
            }
        )

    summary["elapsed_sec_total"] = round(summary["elapsed_sec_total"], 3)
    json_dump(run_root / "run_matrix.json", run_matrix)
    json_dump(
        run_root / "failure_modes.json",
        {
            "run_id": run_root.name,
            "terminated_reasons": failure_modes,
            "failed_tasks": [
                item for item in run_matrix if item["status"] != "success"
            ],
        },
    )
    json_dump(run_root / "summary.json", summary)


def execute_run(
    *,
    methods: List[MethodSpec],
    submissions: list,
    test_cases: dict,
    descriptions: Optional[Dict[str, str]],
    output_dir: Path,
    max_workers: int,
    verbose: bool,
    debug: bool,
    run_metadata: Optional[dict],
    resume: bool,
    parallel: bool,
    run_id: Optional[str] = None,
) -> Path:
    run_root = output_dir / "runs" / (run_id or make_run_id())
    run_root.mkdir(parents=True, exist_ok=True)
    write_run_config(
        run_root,
        methods=methods,
        max_workers=max_workers,
        parallel=parallel,
        resume=resume,
        run_metadata=run_metadata,
    )

    tasks = build_tasks(methods, submissions)
    print(
        f"Running {len(tasks)} tasks across {len(methods)} methods "
        f"with max_workers={max_workers}"
    )

    task_records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(
                run_one_task,
                run_root=run_root,
                method=method,
                rec=rec,
                test_cases=test_cases,
                descriptions=descriptions,
                verbose=verbose,
                debug=debug,
                resume=resume,
            ): (method, rec)
            for method, rec in tasks
        }
        for future in as_completed(future_map):
            method, rec = future_map[future]
            record = future.result()
            task_records.append(record)
            task_status = record["task_status"]
            print(
                f"  [{method.canonical_method}] {rec.submission_id} -> "
                f"{task_status['status']} ({task_status.get('terminated_reason')})"
            )

    task_records.sort(key=lambda item: (item["method"], item["submission_id"]))
    aggregate_run(run_root, task_records)
    return run_root


def main():
    add_sys_paths()

    parser = argparse.ArgumentParser(description="ACA Experiment Runner")
    parser.add_argument(
        "--methods",
        required=False,
        nargs="+",
        help="Canonical methods (Base,BaseC,ITER,Agent,BaseG,BaseCG,ITERG,AgentG) or compatible aliases (L0,L1,V0,R1,G0,G1,Base-G,BaseC-G,ITER-G,Agent-G)",
    )
    parser.add_argument(
        "--strategy",
        required=False,
        nargs="+",
        help="Deprecated alias for --methods",
    )
    parser.add_argument(
        "--data-base",
        required=False,
        help="waFocusedData base directory (contains submit.ndjson + problem.ndjson)",
    )
    parser.add_argument(
        "--wa-focused-base",
        default=None,
        help="Compatibility alias for --data-base",
    )
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable task-level parallel execution",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Task scheduler worker count when --parallel is enabled (default: 8)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Deprecated alias for --max-workers",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip tasks whose task_status.json already reports success",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max submissions to process")
    parser.add_argument("--pids", default=None, help="Comma-separated list of pids to filter")
    parser.add_argument(
        "--submission-ids",
        default=None,
        help="Comma-separated exact submission_ids to filter after dataset load",
    )
    parser.add_argument("--output", default="outputs", help="Output directory for results")
    parser.add_argument("--verbose", action="store_true", help="Print debug output")
    parser.add_argument(
        "--generator-seeds-per-round",
        type=int,
        default=None,
        help="Override generator seed count for BaseG/BaseCG/ITERG/AgentG while preserving non-generator methods.",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Optional runtime override for generator methods max_rounds.",
    )
    parser.add_argument(
        "--llm-model",
        default=None,
        help="Optional runtime override for the served model name.",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=None,
        help="Optional runtime override for LLM temperature.",
    )
    parser.add_argument(
        "--llm-max-tokens",
        type=int,
        default=None,
        help="Optional runtime override for LLM max_tokens.",
    )
    parser.add_argument(
        "--qwen-output-constraint",
        choices=["auto", "on", "off"],
        default="auto",
        help="Append a short code-only output constraint to GTOR system prompts: auto=Qwen GTOR only, on=all GTOR, off=disabled.",
    )
    parser.add_argument(
        "--gtor-prompt-profile",
        choices=["legacy", "small_model_minimal"],
        default="legacy",
        help="Prompt profile for generator methods: legacy=full prompt, small_model_minimal=minimal prompt for small models.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Write full LLM conversation traces to each task directory",
    )
    parser.add_argument(
        "--data-backend",
        default=None,
        help="Optional label written to config.json (e.g. waFocusedData_joined)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional fixed run ID under <output>/runs/<run_id>",
    )
    args = parser.parse_args()

    try:
        methods = resolve_requested_methods(args.methods, args.strategy)
    except ValueError as exc:
        parser.error(str(exc))
    methods = override_method_runtime(
        methods,
        generator_seeds_per_round=args.generator_seeds_per_round,
        max_rounds=args.max_rounds,
        llm_model=args.llm_model,
        llm_temperature=args.llm_temperature,
        llm_max_tokens=args.llm_max_tokens,
        qwen_output_constraint_mode=args.qwen_output_constraint,
        gtor_prompt_profile=args.gtor_prompt_profile,
    )
    data_base = args.data_base or args.wa_focused_base
    if not data_base:
        parser.error("one of --data-base or --wa-focused-base is required")
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    effective_workers = args.workers if args.workers is not None else args.max_workers
    if not args.parallel:
        effective_workers = 1
    if effective_workers < 1:
        raise ValueError("max_workers must be >= 1")

    from ACA.tool.wa_focused_adapter import write_adapter_dataset

    adapter_dir = output_dir / "_wa_focused_adapter_cache"
    adapter_paths = write_adapter_dataset(data_base, adapter_dir)
    data_path = adapter_paths.runner_ready_ndjson
    ref_path = adapter_paths.references_json
    descriptions_path = adapter_paths.descriptions_json
    os.environ["ACA_VALIDATOR_ROOT"] = adapter_paths.validator_root
    os.environ["ACA_VALIDATOR_REGISTRY"] = adapter_paths.validator_registry
    data_backend = args.data_backend or "waFocusedData_joined"
    print(f"Using waFocusedData backend from {data_base}")
    print(f"  adapter dataset: {data_path}")
    print(f"  adapter refs: {ref_path}")

    from ACA.tool.problem_loader import load_dataset, load_descriptions

    pids = [p.strip() for p in args.pids.split(",")] if args.pids else None
    submission_ids = [s.strip() for s in args.submission_ids.split(",")] if args.submission_ids else None
    descriptions = load_descriptions(descriptions_path)
    print(f"Loading {data_path} ...")
    dataset = load_dataset(
        data_path,
        ref_path,
        filter_passed_only=True,
        limit=args.limit,
        pids=pids,
        descriptions=descriptions,
    )
    if submission_ids:
        dataset.submissions = filter_submissions(dataset.submissions, submission_ids=submission_ids)
    print(
        f"  {len(dataset.submissions)} submissions, {len(dataset.test_cases)} problems, "
        f"{len(descriptions)} descriptions"
    )

    run_root = execute_run(
        methods=methods,
        submissions=dataset.submissions,
        test_cases={
            pid: [
                {
                    "input": tc.input_text,
                    "output": tc.expected_output,
                    "_norm_out": tc.expected_output_norm,
                }
                for tc in cases
            ]
            for pid, cases in dataset.test_cases.items()
        },
        descriptions=descriptions,
        output_dir=output_dir,
        max_workers=effective_workers,
        verbose=args.verbose,
        debug=args.debug,
        run_metadata={
            "data_backend": data_backend,
            "data_path": data_path,
            "references_path": ref_path,
            "descriptions_path": descriptions_path,
            "validator_root": os.environ.get("ACA_VALIDATOR_ROOT"),
            "validator_registry": os.environ.get("ACA_VALIDATOR_REGISTRY"),
            "pids": pids,
            "submission_ids": submission_ids,
        },
        resume=args.resume,
        parallel=args.parallel,
        run_id=args.run_id,
    )
    print(f"Run output: {run_root}")
    print("Done.")


if __name__ == "__main__":
    main()
