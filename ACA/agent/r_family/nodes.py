"""R-family LangGraph nodes: agent_node and tool_executor_node."""

import time
from typing import Any, Dict, List, Optional
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from ACA.agent.g_family.prompts import build_user_message as build_generator_user_message
from ACA.agent.l_family.prompts import build_user_message
from ACA.agent.r_family.config import R1Config
from ACA.agent.r_family.prompts import PROMPT_REGISTRY, get_system_prompt
from ACA.agent.r_family.tools import get_tools
from ACA.agent.shared.generator_utils import normalize_generator_code_transport_escapes
from ACA.agent.shared.llm_client import LLMClient
from ACA.agent.shared.trajectory import (
    TrajectoryWriter,
    stable_input_hash,
    response_payload_text,
    safe_preview,
    stable_hash,
)
from ACA.agent.shared.verdicts import is_valid_dual_status
from ACA.agent.shared.state import AgentState
from ACA.tool.sandbox import (
    trace_coverage_dual,
)
from ACA.tool.generator_runner import compile_generator_code, run_generator_code


def _compact_line_list(lines: List[int]) -> str:
    """Compact line list: [1,2,3,5,6] → '1-3,5-6'."""
    if not lines:
        return "[]"
    lines = sorted(lines)
    parts = []
    start = lines[0]
    end = lines[0]
    for ln in lines[1:]:
        if ln == end + 1:
            end = ln
        else:
            parts.append(str(start) if start == end else f"{start}-{end}")
            start = end = ln
    parts.append(str(start) if start == end else f"{start}-{end}")
    return ",".join(parts)


def _format_countercase_inputs(countercases: List[str]) -> list[str]:
    if not countercases:
        return []
    lines = ["Countercase inputs:"]
    nl = chr(10)
    bs = chr(92)
    for idx, inp in enumerate(countercases, start=1):
        lines.append(f"  {idx}. {inp.replace(nl, bs + 'n')}")
    return lines


def _classify_feedback_status(dr: Any, newly_covered: set[int]) -> tuple[str, str]:
    validator_reason = getattr(dr, "validator_reason", "") or dr.error or ""
    if dr.status == "SPEC_INVALID":
        reason = validator_reason or "validator rejected input"
        return "INVALID", f"validator rejected input: {reason}"
    if dr.status in ("INVALID", "UNKNOWN", "TRACE_TLE") or not dr.reference_ok:
        if dr.status == "TRACE_TLE":
            return "INCOMPARABLE", "trace run timed out; comparable verdict unavailable"
        if dr.status == "INVALID":
            return "INCOMPARABLE", "reference failed on this input"
        if dr.status == "UNKNOWN":
            return "INCOMPARABLE", "reference produced an incomparable result"
        return "INCOMPARABLE", "reference failed or timed out on this input"
    if dr.status == "WA":
        return "COUNTERCASE_WA", "student output differs from reference"
    if dr.status in ("RE", "MLE", "OOM"):
        if dr.status == "MLE":
            return "COUNTERCASE_RE", "student exceeded memory limit"
        if dr.status == "OOM":
            return "COUNTERCASE_RE", "student ran out of memory"
        return "COUNTERCASE_RE", "student runtime error"
    if dr.status in ("TLE", "TIMEOUT"):
        return "TIMEOUT", "student exceeded timeout"
    if dr.status == "AC" and newly_covered:
        return "AC", "same output as reference; new target coverage"
    if dr.status == "AC":
        return "AC", "same output as reference; no new target coverage"
    return "EXECUTION_ERROR", "execution failed unexpectedly"


def _build_task_package(state: AgentState) -> str:
    """Build the task context for the LLM using the shared BaseC-style template."""
    if state.get("strategy") == "AgentG":
        prompt_config = SimpleNamespace(strategy="G1", test_input_count=5)
        return build_generator_user_message(
            prompt_config,
            code_text=state.get("prompt_code_text", state["code_text"]),
            target_lines=state.get("uncovered_lines", state.get("prompt_uncovered_lines", [])),
            uncovered_line_tags={},
            description_html=state.get("description_html", ""),
            sample_input_anchor=state.get("sample_input_anchor", ""),
            gtor_prompt_profile=state.get("gtor_prompt_profile", "legacy"),
            iteration=state.get("iteration", 0) + 1,
        )
    prompt_config = SimpleNamespace(strategy="L1", test_input_count=5)
    return build_user_message(
        prompt_config,
        code_text=state.get("prompt_code_text", state["code_text"]),
        target_lines=state.get("uncovered_lines", state.get("prompt_uncovered_lines", [])),
        uncovered_line_tags={},
        description_html=state.get("description_html", ""),
        sample_input_anchor=state.get("sample_input_anchor", ""),
    )


# ── Agent Node ──────────────────────────────────────────────────────────


def _feedback_level(strategy: str) -> str:
    if strategy == "R1.1":
        return "rich_tool_feedback_plus_mutation_prompt"
    return "rich_tool_feedback"


def _configured_generator_seed_count(config: R1Config) -> int:
    return max(1, int(getattr(config, "num_seeds", 5)))


def _visible_seed_count_in_prompt(config: R1Config, strategy: str) -> int:
    if strategy != "AgentG":
        return 0
    if getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal":
        return 0
    return _configured_generator_seed_count(config)


def make_agent_node(
    config: R1Config,
    client: LLMClient,
    trajectory_writer: Optional[TrajectoryWriter] = None,
):
    """Return an agent_node function with bound config and LLM client."""

    def agent_node(state: AgentState) -> Dict[str, Any]:
        strategy = state["strategy"]
        uncovered = state.get("uncovered_lines", [])

        if config.dynamic_prompt_swap and not uncovered:
            prompt_key = f"{strategy}_CC"
        else:
            prompt_key = strategy

        generator_seed_count = _configured_generator_seed_count(config) if strategy == "AgentG" else 5
        system = SystemMessage(content=get_system_prompt(
            prompt_key,
            num_seeds=generator_seed_count,
            model_name=getattr(config, "model", None),
            qwen_output_constraint_mode=getattr(config, "qwen_output_constraint_mode", "auto"),
            gtor_prompt_profile=getattr(config, "gtor_prompt_profile", "legacy"),
        ))
        state["gtor_prompt_profile"] = getattr(config, "gtor_prompt_profile", "legacy")
        task_pkg = _build_task_package(state)
        user_msg = HumanMessage(content=task_pkg)

        history = list(state.get("messages", []))
        messages = [system] + history + [user_msg]
        next_iteration = state.get("iteration", 0) + 1

        tools = get_tools(
            strategy,
            generator_seed_count=generator_seed_count,
            exact_input_count=getattr(config, "exact_input_count", 5),
            gtor_prompt_profile=getattr(config, "gtor_prompt_profile", "legacy"),
        )

        prompt_text = "\n\n".join(
            [
                system.content or "",
                task_pkg,
            ]
        )
        if trajectory_writer is not None:
            trajectory_writer.append_event({
                "event_type": "prompt_built",
                "iteration": next_iteration,
                "strategy": strategy,
                "submission_id": state["submission_id"],
                "feedback_visible_level": _feedback_level(strategy),
                "qwen_output_constraint_mode": getattr(config, "qwen_output_constraint_mode", "auto"),
                "qwen_output_constraint_applied": bool(getattr(config, "qwen_output_constraint_applied", False)),
                "qwen_output_constraint_text": getattr(config, "qwen_output_constraint_text", ""),
                "seed_contract_clarification_applied": bool(getattr(config, "seed_contract_clarification_applied", False)),
                "seed_contract_clarification_text": getattr(config, "seed_contract_clarification_text", ""),
                "gtor_prompt_profile": getattr(config, "gtor_prompt_profile", "legacy"),
                "visible_seed_count_in_prompt": _visible_seed_count_in_prompt(config, strategy),
                "small_model_minimal_prompt_applied": getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal",
                "visible_uncovered_lines": list(uncovered),
                "history_visible_to_llm": {
                    "has_history": bool(history),
                    "message_count": len(history),
                },
                "prompt_hash": stable_hash(prompt_text),
                "prompt_text": prompt_text,
                "prompt_chars": len(prompt_text),
            })

        _t0 = time.time()
        result = client.call(messages, tools, tool_choice="required")
        _t1 = time.time()

        # Check LLM parse repair / retry metadata
        _parse_meta = getattr(result, 'additional_kwargs', {}).get('_parse_meta', {})
        if _parse_meta.get('llm_parse_failed'):
            return {
                "messages": [user_msg, result],
                "iteration": state.get("iteration", 0) + 1,
                "terminated_reason": "llm_parse_failed",
                "stop_reason": "llm_parse_failed",
                "error": _parse_meta.get("final_error", "JSON parse failed after retry"),
            }
        _parse_repair_used = _parse_meta.get('parse_repair_used', False)

        if config.verbose:
            total_chars = sum(
                len(m.content) if hasattr(m, "content") and m.content else 0
                for m in messages
            )
            print(
                f"[TIMING] agent_node — LLM call {_t1 - _t0:.1f}s "
                f"(iter={state.get('iteration', 0) + 1}, chars={total_chars})",
                flush=True,
            )

        if trajectory_writer is not None:
            tool_calls = getattr(result, "tool_calls", []) or []
            num_inputs = 0
            parse_error = None
            if tool_calls:
                tool_name = tool_calls[0].get("name")
                args = tool_calls[0].get("args", {})
                if tool_name == "run_generator_and_trace":
                    raw_seeds = args.get("seeds", [])
                    generator_code = args.get("generator_code", "")
                    if not isinstance(generator_code, str) or not generator_code.strip():
                        parse_error = "tool_call_missing_generator_code"
                    elif getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal":
                        num_inputs = _configured_generator_seed_count(config)
                    elif isinstance(raw_seeds, list):
                        num_inputs = len(raw_seeds)
                    else:
                        parse_error = "tool_call_missing_seeds"
                else:
                    raw_inputs = args.get("test_inputs", [])
                    if isinstance(raw_inputs, str):
                        num_inputs = 1
                    elif isinstance(raw_inputs, list):
                        num_inputs = len(raw_inputs)
                    else:
                        parse_error = "tool_call_missing_test_inputs"
            else:
                parse_error = "no_tool_call"
            parse_ok = bool(tool_calls and parse_error is None and num_inputs > 0)
            trajectory_writer.append_event({
                "event_type": "llm_response",
                "iteration": next_iteration,
                "strategy": strategy,
                "submission_id": state["submission_id"],
                "raw_response": response_payload_text(result),
                "raw_response_hash": stable_hash(response_payload_text(result)),
                "parse_ok": parse_ok,
                "parse_error": parse_error,
                "num_extracted_inputs": num_inputs,
                "parse_repair_used": _parse_repair_used,
                "first_parse_error": _parse_meta.get("first_error") if _parse_repair_used else None,
                "first_finish_reason": _parse_meta.get("first_finish_reason") if _parse_repair_used else None,
                "finish_reason": result.response_metadata.get("finish_reason") if hasattr(result, "response_metadata") else None,
                "usage": result.response_metadata.get("usage") if hasattr(result, "response_metadata") else None,
                "latency_ms": round((_t1 - _t0) * 1000, 1),
            })
            if tool_calls:
                tool_name = tool_calls[0].get("name")
                args = tool_calls[0].get("args", {})
                if tool_name == "run_and_trace":
                    raw_inputs = args.get("test_inputs", [])
                    if isinstance(raw_inputs, str):
                        raw_inputs = [raw_inputs]
                    elif not isinstance(raw_inputs, list):
                        raw_inputs = [str(raw_inputs)]
                    input_entries = trajectory_writer.make_input_entries(
                        next_iteration,
                        [str(x) for x in raw_inputs],
                        None,
                    )
                    trajectory_writer.append_event({
                        "event_type": "inputs_extracted",
                        "iteration": next_iteration,
                        "strategy": strategy,
                        "submission_id": state["submission_id"],
                        "num_inputs": len(input_entries),
                        "inputs": input_entries,
                    })
            else:
                is_api_error = (
                    result.content
                    and result.content.startswith("[LLM API Error]")
                )
                reason = "llm_api_error" if is_api_error else "AIMessage has no tool_calls"
                trajectory_writer.append_event({
                    "event_type": "no_tool_call",
                    "iteration": next_iteration,
                    "strategy": strategy,
                    "submission_id": state["submission_id"],
                    "reason": reason,
                    "visible_uncovered_lines": list(uncovered),
                    "history_message_count": len(history),
                    "raw_response_preview": safe_preview(response_payload_text(result)),
                })

        no_tool_call = state.get("no_tool_call_count", 0)

        # API error disguised as text response
        api_error = (
            not result.tool_calls
            and result.content
            and result.content.startswith("[LLM API Error]")
        )
        if api_error:
            llm_error = getattr(result, "additional_kwargs", {}).get("llm_error", {})
            return {
                "messages": [user_msg, result],
                "no_tool_call_count": no_tool_call,
                "iteration": state.get("iteration", 0) + 1,
                "terminated_reason": "api_error",
                "stop_reason": "api_error",
                "error": llm_error,
            }

        if not result.tool_calls:
            no_tool_call += 1
        else:
            no_tool_call = 0

        return {
            "messages": [user_msg, result],
            "no_tool_call_count": no_tool_call,
            "iteration": state.get("iteration", 0) + 1,
        }

    return agent_node


# ── Tool Executor Node ──────────────────────────────────────────────────


def _handle_run_and_trace(
    state: AgentState, tool_id: str, args: Dict[str, Any],
    run_timeout: int,
    trajectory_writer: Optional[TrajectoryWriter] = None,
) -> Dict[str, Any]:
    """Execute run_and_trace: dual-run trace → coverage + verdict → update state.

    Uses trace_coverage_dual() — reference solution is run first to produce
    expected output for EACH agent-generated input, then student code is run
    with coverage tracing.  This is the correct approach: the agent generates
    NOVEL inputs that have no pre-computed expected output.
    """
    # Parse inputs
    try:
        test_inputs = args.get("test_inputs", [])
        if isinstance(test_inputs, str):
            test_inputs = [test_inputs]
        elif not isinstance(test_inputs, list):
            test_inputs = [str(test_inputs)]
        if not test_inputs:
            raise KeyError("test_inputs is empty")
        if len(test_inputs) != 5:
            raise ValueError(f"expected exactly 5 test_inputs, got {len(test_inputs)}")
    except (KeyError, TypeError) as e:
        return {
            "messages": [
                ToolMessage(
                    content=(
                        f"[Parameter Error] Invalid arguments for run_and_trace: {e}. "
                        "Required: test_inputs (array of strings). "
                        'Example: {"test_inputs": ["5\\n1 2 3 4 5", "3\\n1 2 3"]}'
                    ),
                    tool_call_id=tool_id,
                )
            ]
        }
    except ValueError as e:
        return {
            "messages": [
                ToolMessage(
                    content=(
                        f"[Parameter Error] Invalid arguments for run_and_trace: {e}. "
                        'Required: exactly 5 test_inputs. Example: {"test_inputs": ["5\\n1 2 3 4 5", "...", "...", "...", "..."]}'
                    ),
                    tool_call_id=tool_id,
                )
            ]
        }

    ref_code = state.get("ref_code", "")
    if not ref_code:
        return {
            "messages": [
                ToolMessage(
                    content="[Error] No reference code available for dual-run comparison.",
                    tool_call_id=tool_id,
                )
            ]
        }

    # Run all inputs through dual-run sandbox
    try:
        dual_results = trace_coverage_dual(
            state["code_text"], ref_code, test_inputs,
            timeout=run_timeout, memory_mb=256,
            pid=state["pid"],
        )
    except Exception as e:
        return {
            "messages": [
                ToolMessage(
                    content=f"[Error] Dual-run execution failed: {e}",
                    tool_call_id=tool_id,
                )
            ]
        }

    all_newly_covered: set = set()
    all_remaining = set(state["uncovered_lines"])
    breakthroughs: List[str] = []
    per_input: List[tuple] = []  # (idx, visible_status, new_list, note)
    invalid_count = 0
    valid_count = 0
    current_iteration = state.get("iteration", 0)

    for i, (test_input, dr) in enumerate(zip(test_inputs, dual_results)):
        inp_compact = test_input.replace("\n", "\\n")

        covered = set(dr.covered_lines)
        newly_covered = set(state["uncovered_lines"]) & covered
        all_newly_covered |= newly_covered
        all_remaining -= covered

        visible_status, note = _classify_feedback_status(dr, newly_covered)
        if visible_status == "INVALID":
            invalid_count += 1
        per_input.append((i + 1, visible_status, sorted(newly_covered), note))

        if dr.breakthrough:
            breakthroughs.append(test_input)
        if is_valid_dual_status(dr.status):
            valid_count += 1

        if trajectory_writer is not None:
            input_id = f"it{current_iteration}_in{i}"
            trajectory_writer.append_event({
                "event_type": "sandbox_result",
                "iteration": current_iteration,
                "strategy": state.get("strategy"),
                "submission_id": state["submission_id"],
                "input_id": input_id,
                "input_hash": stable_input_hash(test_input),
                "status": dr.status,
                "breakthrough": dr.breakthrough,
                "valid": is_valid_dual_status(dr.status),
                "reference_ok": dr.reference_ok,
                "stdout": dr.stdout,
                "stderr": dr.stderr,
                "expected_output": dr.expected_output,
                "covered_lines": sorted(dr.covered_lines),
                "newly_covered_targets": sorted(newly_covered),
                "error": dr.error or None,
                "validator_ok": getattr(dr, "validator_ok", None),
                "validator_reason": getattr(dr, "validator_reason", None),
                "pure_status": getattr(dr, "pure_status", ""),
                "trace_status": getattr(dr, "trace_status", ""),
                "coverage_available": getattr(dr, "coverage_available", True),
                "ref_stdout": getattr(dr, "ref_stdout", ""),
                "ref_stderr": getattr(dr, "ref_stderr", ""),
                "ref_returncode": getattr(dr, "ref_returncode", None),
            })

    # Build batch summary
    remaining = sorted(all_remaining)
    newly_covered_list = sorted(all_newly_covered)

    batch_lines = []
    batch_lines.append("Batch execution finished.")
    batch_lines.append(f"New target lines covered: {newly_covered_list if newly_covered_list else '[]'}")
    if remaining:
        batch_lines.append(f"Remaining target lines: {remaining}")
    else:
        batch_lines.append("Remaining target lines: []")
    batch_lines.append(f"Countercases found: {len(breakthroughs)}")
    batch_lines.append(f"Valid inputs: {valid_count}/{len(test_inputs)}")

    batch_lines.append("")
    batch_lines.append("Per-input results:")
    for idx, visible_status, new_lines, note in per_input:
        batch_lines.append(
            f"  {idx}. [{visible_status}] new_lines={new_lines} note={note}"
        )
    if breakthroughs:
        batch_lines.append("")
        batch_lines.extend(_format_countercase_inputs(breakthroughs))

    # ── Structured trajectory data (full, no truncation) ────────────
    is_stagnation = not newly_covered_list and not breakthroughs
    traj_case_results = []
    for test_input, dr in zip(test_inputs, dual_results):
        traj_case_results.append({
            "test_input": test_input,
            "status": dr.status,
            "stdout": dr.stdout,
            "stderr": dr.stderr,
            "expected_output": dr.expected_output,
            "covered_lines": sorted(dr.covered_lines),
            "is_ac": (dr.status == "AC"),
            "reference_ok": dr.reference_ok,
        })
    # Extract thought_process from the trigger AIMessage
    _msgs = list(state.get("messages", []))
    _thought = ""
    if _msgs:
        _last = _msgs[-1]
        if hasattr(_last, "content") and _last.content:
            _thought = _last.content
    traj_entry = {
        "iteration": state.get("iteration", 0) + 1,
        "test_inputs": [str(x) for x in test_inputs],
        "uncovered_before": list(state.get("uncovered_lines", [])),
        "per_case_results": traj_case_results,
        "newly_covered": newly_covered_list,
        "breakthroughs": breakthroughs,
        "thought_process": _thought,
        "stagnation": is_stagnation,
        "invalid_count": invalid_count,
    }
    existing_traj = list(state.get("trajectory_data", []))
    existing_traj.append(traj_entry)

    updates: Dict[str, Any] = {
        "messages": [
            ToolMessage(content="\n".join(batch_lines), tool_call_id=tool_id)
        ],
        "uncovered_lines": remaining,
        "last_newly_covered": newly_covered_list,
        "trajectory_data": existing_traj,
    }

    # Stagnation: round produced neither coverage progress nor breakthrough CCs
    if not newly_covered_list and not breakthroughs:
        updates["stagnation_counter"] = state.get("stagnation_counter", 0) + 1
    else:
        updates["stagnation_counter"] = 0

    if breakthroughs:
        existing = state.get("countercases", [])
        new_ccs = [inp for inp in breakthroughs if inp not in existing]
        if new_ccs:
            updates["countercases"] = existing + new_ccs
            updates["first_countercase_round"] = state.get("first_countercase_round") or current_iteration
            updates["first_countercase_input"] = state.get("first_countercase_input") or new_ccs[0]
        updates["terminated_reason"] = "countercase_found"
        updates["stop_reason"] = "countercase_found"
        countercases_total = len(existing) + len(new_ccs)
    else:
        countercases_total = len(state.get("countercases", []))

    if trajectory_writer is not None:
        next_stagnation_counter = (
            state.get("stagnation_counter", 0) + 1 if is_stagnation else 0
        )
        trajectory_writer.append_event({
            "event_type": "iteration_state_update",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "uncovered_before": list(state.get("uncovered_lines", [])),
            "newly_covered_targets": newly_covered_list,
            "uncovered_after": remaining,
            "num_inputs": len(test_inputs),
            "num_valid": valid_count,
            "num_invalid": invalid_count,
            "num_breakthroughs": len(breakthroughs),
            "countercases_total": countercases_total,
            "stagnation": is_stagnation,
            "stagnation_counter": next_stagnation_counter,
            "terminated_reason_candidate": None,
            "should_continue": None,
        })

    return updates


def _resolve_generator_seed_policy(
    args: Dict[str, Any],
    config: R1Config,
) -> tuple[list[int], list[int], list[int] | None, bool]:
    configured_num_seeds = _configured_generator_seed_count(config)
    config_seed_list = getattr(config, "seed_list", None)
    if config_seed_list:
        configured_seed_list = [int(seed) for seed in config_seed_list[:configured_num_seeds]]
    else:
        seed_base = int(getattr(config, "seed_base", 0))
        configured_seed_list = list(range(seed_base, seed_base + configured_num_seeds))

    explicit = args.get("seeds")
    model_requested_seed_list = None
    if isinstance(explicit, list) and explicit:
        try:
            model_requested_seed_list = [int(seed) for seed in explicit[:configured_num_seeds]]
        except Exception:
            model_requested_seed_list = None

    actual_seed_list = list(configured_seed_list)
    seed_override_applied = (
        model_requested_seed_list is not None
        and model_requested_seed_list != actual_seed_list
    )
    return configured_seed_list, actual_seed_list, model_requested_seed_list, seed_override_applied


def _handle_run_generator_and_trace(
    state: AgentState,
    tool_id: str,
    args: Dict[str, Any],
    config: R1Config,
    trajectory_writer: Optional[TrajectoryWriter] = None,
) -> Dict[str, Any]:
    try:
        generator_code = args.get("generator_code", "")
        if not isinstance(generator_code, str) or not generator_code.strip():
            raise KeyError("generator_code is empty")
        generator_code, norm_meta = normalize_generator_code_transport_escapes(generator_code)
    except (KeyError, TypeError, ValueError) as e:
        return {
            "messages": [
                ToolMessage(
                    content=(
                        f"[Parameter Error] Invalid arguments for run_generator_and_trace: {e}. "
                        "Required: generator_code (string). Seeds are controlled by system-fixed seed policy in the mainline experiment."
                    ),
                    tool_call_id=tool_id,
                )
            ]
        }

    configured_seed_list, seeds, model_requested_seed_list, seed_override_applied = _resolve_generator_seed_policy(args, config)
    model_provided_seeds_ignored = bool(isinstance(args.get("seeds"), list) and args.get("seeds"))

    current_iteration = state.get("iteration", 0)
    compile_result = compile_generator_code(
        generator_code,
        max_code_bytes=getattr(config, "generator_max_code_bytes", 256 * 1024),
    )
    if trajectory_writer is not None:
        trajectory_writer.append_event({
            "event_type": "generator_code_extracted",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "extraction_status": "GENERATOR_OK",
            "code_hash": stable_hash(generator_code),
            "code_preview": safe_preview(generator_code),
            "code_text": generator_code if trajectory_writer.keep_full_text else None,
            "normalization_meta": norm_meta,
        })
        trajectory_writer.append_event({
            "event_type": "generator_code_built",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "num_seeds": len(seeds),
            "seed_list": seeds,
            "configured_seed_list": configured_seed_list,
            "actual_seed_list": list(seeds),
            "model_requested_seed_list": model_requested_seed_list,
            "seed_policy": "system_fixed",
            "seed_override_applied": seed_override_applied,
            "model_provided_seeds_ignored": model_provided_seeds_ignored,
            "agent_tool_seed_source": "runtime_config",
            "gtor_prompt_profile": getattr(config, "gtor_prompt_profile", "legacy"),
            "visible_seed_count_in_prompt": _visible_seed_count_in_prompt(config, "AgentG"),
            "small_model_minimal_prompt_applied": getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal",
            "code_hash": stable_hash(generator_code),
            "code_preview": safe_preview(generator_code),
            "code_text": generator_code if trajectory_writer.keep_full_text else None,
            "normalization_meta": norm_meta,
        })
        trajectory_writer.append_event({
            "event_type": "generator_compile",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "compile_status": compile_result.status,
            "compile_ok": compile_result.ok,
            "compile_error": compile_result.error,
            "code_bytes": compile_result.code_bytes,
        })

    if not compile_result.ok:
        return {
            "messages": [
                ToolMessage(
                    content=(
                        "Generator batch execution failed.\n"
                        "Generator compile status: failed\n"
                        f"Failure reason: {compile_result.error}\n"
                        "Countercases found: 0"
                    ),
                    tool_call_id=tool_id,
                )
            ],
            "stagnation_counter": state.get("stagnation_counter", 0) + 1,
        }

    gen_results = run_generator_code(
        generator_code,
        seeds=seeds,
        timeout=getattr(config, "generator_timeout", 2.0),
        memory_mb=getattr(config, "generator_memory_mb", 256),
        max_output_bytes=getattr(config, "generator_max_output_bytes", 256 * 1024),
    )

    test_inputs: List[str] = []
    generated_input_entries = []
    for idx, item in enumerate(gen_results):
        if trajectory_writer is not None:
            trajectory_writer.append_event({
                "event_type": "generator_run",
                "iteration": current_iteration,
                "strategy": state.get("strategy"),
                "submission_id": state["submission_id"],
                "seed": item.seed,
                "generator_status": item.status,
                "stdout": getattr(item, "stdout", item.stdout_preview),
                "stderr": getattr(item, "stderr", item.stderr_preview),
                "runtime_sec": round(item.runtime_sec, 4),
                "generator_error": item.error,
            })
        if item.status == "GEN_OK" and item.input_text is not None:
            test_inputs.append(item.input_text)

    if trajectory_writer is not None:
        generated_input_entries = trajectory_writer.make_input_entries(
            current_iteration,
            test_inputs,
            [f"generator_seed={seed}" for seed in seeds[: len(test_inputs)]],
        )
        trajectory_writer.append_event({
            "event_type": "inputs_extracted",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "num_inputs": len(generated_input_entries),
            "inputs": generated_input_entries,
        })
        for idx, entry in enumerate(generated_input_entries):
            trajectory_writer.append_event({
                "event_type": "generated_input",
                "iteration": current_iteration,
                "strategy": state.get("strategy"),
                "submission_id": state["submission_id"],
                "seed": seeds[idx] if idx < len(seeds) else None,
                **entry,
            })

    if not test_inputs:
        return {
            "messages": [
                ToolMessage(
                    content=(
                        "Generator batch execution failed.\n"
                        "Generator compile status: ok\n"
                        "Failure reason: generator produced empty stdout for all seeds\n"
                        "Countercases found: 0"
                    ),
                    tool_call_id=tool_id,
                )
            ],
            "stagnation_counter": state.get("stagnation_counter", 0) + 1,
        }

    ref_code = state.get("ref_code", "")
    if not ref_code:
        return {
            "messages": [
                ToolMessage(content="[Error] No reference code available for dual-run comparison.", tool_call_id=tool_id)
            ]
        }

    try:
        dual_results = trace_coverage_dual(
            state["code_text"],
            ref_code,
            test_inputs,
            timeout=config.run_timeout,
            memory_mb=256,
            pid=state["pid"],
        )
    except Exception as e:
        return {
            "messages": [
                ToolMessage(content=f"[Error] Dual-run execution failed: {e}", tool_call_id=tool_id)
            ]
        }

    all_newly_covered: set[int] = set()
    all_remaining = set(state["uncovered_lines"])
    breakthroughs: List[str] = []
    traj_case_results = []
    batch_lines = [
        "Generator batch execution finished.",
        "Generator compile status: ok",
        f"Seeds executed: {list(seeds)}",
        f"Generated inputs: {len(test_inputs)}",
    ]
    valid_count = 0
    invalid_count = 0

    per_seed_lines = ["Per-seed results:"]
    for idx, (test_input, dr) in enumerate(zip(test_inputs, dual_results)):
        covered = set(dr.covered_lines)
        newly_covered = set(state["uncovered_lines"]) & covered
        all_newly_covered |= newly_covered
        all_remaining -= covered
        if dr.breakthrough:
            breakthroughs.append(test_input)
        if is_valid_dual_status(dr.status):
            valid_count += 1
        else:
            invalid_count += 1
        visible_status, note = _classify_feedback_status(dr, newly_covered)
        traj_case_results.append({
            "test_input": test_input,
            "status": dr.status,
            "stdout": dr.stdout,
            "stderr": dr.stderr,
            "expected_output": dr.expected_output,
            "covered_lines": sorted(dr.covered_lines),
            "is_ac": (dr.status == "AC"),
            "reference_ok": dr.reference_ok,
        })
        if trajectory_writer is not None:
            input_id = (
                generated_input_entries[idx]["input_id"]
                if idx < len(generated_input_entries)
                else f"it{current_iteration}_in{idx}"
            )
            input_hash = (
                generated_input_entries[idx]["input_hash"]
                if idx < len(generated_input_entries)
                else stable_input_hash(test_input)
            )
            trajectory_writer.append_event({
                "event_type": "sandbox_result",
                "iteration": current_iteration,
                "strategy": state.get("strategy"),
                "submission_id": state["submission_id"],
                "input_id": input_id,
                "input_hash": input_hash,
                "status": dr.status,
                "breakthrough": dr.breakthrough,
                "valid": is_valid_dual_status(dr.status),
                "reference_ok": dr.reference_ok,
                "stdout": dr.stdout,
                "stderr": dr.stderr,
                "expected_output": dr.expected_output,
                "covered_lines": sorted(dr.covered_lines),
                "newly_covered_targets": sorted(newly_covered),
                "error": dr.error or None,
                "validator_ok": getattr(dr, "validator_ok", None),
                "validator_reason": getattr(dr, "validator_reason", None),
                "pure_status": getattr(dr, "pure_status", ""),
                "trace_status": getattr(dr, "trace_status", ""),
                "coverage_available": getattr(dr, "coverage_available", True),
                "ref_stdout": getattr(dr, "ref_stdout", ""),
                "ref_stderr": getattr(dr, "ref_stderr", ""),
                "ref_returncode": getattr(dr, "ref_returncode", None),
            })
        per_seed_lines.append(
            f"  seed={seeds[idx] if idx < len(seeds) else '?'}: "
            f"[{visible_status}] new_lines={sorted(newly_covered)} note={note}"
        )

    remaining = sorted(all_remaining)
    newly_covered_list = sorted(all_newly_covered)
    batch_lines.insert(4, f"New target lines covered: {newly_covered_list if newly_covered_list else '[]'}")
    batch_lines.insert(5, f"Remaining target lines: {remaining if remaining else '[]'}")
    batch_lines.insert(6, f"Countercases found: {len(breakthroughs)}")
    batch_lines.insert(7, f"Valid generated inputs: {valid_count}/{len(test_inputs)}")
    batch_lines.append("")
    batch_lines.extend(per_seed_lines)
    if breakthroughs:
        batch_lines.append("")
        batch_lines.extend(_format_countercase_inputs(breakthroughs))

    existing_traj = list(state.get("trajectory_data", []))
    existing_traj.append({
        "iteration": current_iteration,
        "test_inputs": test_inputs,
        "uncovered_before": list(state.get("uncovered_lines", [])),
        "per_case_results": traj_case_results,
        "newly_covered": newly_covered_list,
        "breakthroughs": breakthroughs,
        "thought_process": generator_code,
        "stagnation": not newly_covered_list and not breakthroughs,
        "invalid_count": invalid_count,
    })

    updates: Dict[str, Any] = {
        "messages": [ToolMessage(content="\n".join(batch_lines), tool_call_id=tool_id)],
        "uncovered_lines": remaining,
        "last_newly_covered": newly_covered_list,
        "trajectory_data": existing_traj,
        "stagnation_counter": state.get("stagnation_counter", 0) + 1 if not newly_covered_list and not breakthroughs else 0,
    }
    if breakthroughs:
        existing = state.get("countercases", [])
        new_ccs = [inp for inp in breakthroughs if inp not in existing]
        if new_ccs:
            updates["countercases"] = existing + new_ccs
            updates["first_countercase_round"] = state.get("first_countercase_round") or current_iteration
            updates["first_countercase_input"] = state.get("first_countercase_input") or new_ccs[0]
        updates["terminated_reason"] = "countercase_found"
        updates["stop_reason"] = "countercase_found"

    if trajectory_writer is not None:
        trajectory_writer.append_event({
            "event_type": "iteration_state_update",
            "iteration": current_iteration,
            "strategy": state.get("strategy"),
            "submission_id": state["submission_id"],
            "uncovered_before": list(state.get("uncovered_lines", [])),
            "newly_covered_targets": newly_covered_list,
            "uncovered_after": remaining,
            "num_inputs": len(test_inputs),
            "num_valid": valid_count,
            "num_invalid": invalid_count,
            "num_breakthroughs": len(breakthroughs),
            "countercases_total": len(updates.get("countercases", state.get("countercases", []))),
            "stagnation": not newly_covered_list and not breakthroughs,
            "stagnation_counter": updates["stagnation_counter"],
            "terminated_reason_candidate": "countercase_found" if breakthroughs else None,
            "should_continue": None,
        })

    return updates


def make_tool_executor_node(
    config: R1Config,
    trajectory_writer: Optional[TrajectoryWriter] = None,
):
    """Return a tool_executor_node function with bound config."""

    def tool_executor_node(state: AgentState) -> Dict[str, Any]:
        last_msg = state["messages"][-1]
        if not isinstance(last_msg, AIMessage) or not last_msg.tool_calls:
            return {
                "messages": [
                    ToolMessage(
                        content="No tool call to execute.", tool_call_id="dummy"
                    )
                ]
            }

        all_messages = []
        result = None
        ran_primary = False

        for tool_call in last_msg.tool_calls:
            tool_id = tool_call.get("id", "")
            tool_name = tool_call["name"]
            args = tool_call.get("args", {})

            if tool_name == "run_and_trace":
                r = _handle_run_and_trace(
                    state, tool_id, args, config.run_timeout, trajectory_writer,
                )
            elif tool_name == "run_generator_and_trace":
                r = _handle_run_generator_and_trace(
                    state, tool_id, args, config, trajectory_writer,
                )
            else:
                r = {
                    "messages": [
                        ToolMessage(
                            content=f"Unknown tool: {tool_name}",
                            tool_call_id=tool_id,
                        )
                    ]
                }
            all_messages.extend(r.pop("messages", []))
            if not ran_primary:
                result = r
                ran_primary = True

        if result is None:
            result = {}
        result["messages"] = all_messages
        return result

    return tool_executor_node
