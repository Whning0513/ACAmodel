"""G-family runner: process_one_submission for G0, G1, and ITERG."""

import time
from typing import Dict, List, Optional

from ACA.agent.g_family.config import GConfig
from ACA.agent.g_family.prompts import build_system_prompt, build_user_message
from ACA.agent.shared.datatypes import CaseResult, IterationRecord, SubmissionResult
from ACA.agent.shared.generator_utils import (
    GENERATOR_EXTRACTION_ERROR,
    extract_generator_code,
    normalize_generator_code_transport_escapes,
)
from ACA.agent.shared.llm_client import LLMClient
from ACA.agent.shared.prompt_templates import resolve_prompt_view
from ACA.agent.shared.trajectory import (
    TrajectoryWriter,
    compute_submission_end_fields,
    response_payload_text,
    safe_preview,
    stable_hash,
    write_debug_trace,
)
from ACA.agent.shared.verdicts import is_valid_dual_status
from ACA.tool.generator_runner import compile_generator_code, run_generator_code
from ACA.tool.problem_loader import SubmissionRecord as InputRecord


def _feedback_level(strategy: str) -> str:
    if strategy == "G0":
        return "none"
    if strategy == "G1":
        return "static_uncovered_annotation"
    return "updated_uncovered_set_only"


def _system_prompt_for(config: GConfig) -> str:
    return build_system_prompt(
        config.strategy,
        num_seeds=getattr(config, "num_seeds", 5),
        model_name=getattr(config, "model", None),
        qwen_output_constraint_mode=getattr(config, "qwen_output_constraint_mode", "auto"),
        gtor_prompt_profile=getattr(config, "gtor_prompt_profile", "legacy"),
    )


def _seed_batch(config: GConfig) -> list[int]:
    if getattr(config, "seed_list", None):
        return [int(seed) for seed in config.seed_list[: config.num_seeds]]
    base = int(getattr(config, "seed_base", 0))
    return list(range(base, base + config.num_seeds))


def _visible_seed_count_in_prompt(config: GConfig) -> int:
    return 0 if getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal" else int(getattr(config, "num_seeds", 5))


def _previous_failure_type(trajectory: List[IterationRecord]) -> str:
    if not trajectory:
        return ""
    last = trajectory[-1]
    statuses = [cr.status for cr in last.per_case_results]
    for candidate in ("WA", "RE", "TLE", "OOM", "MLE", "TIMEOUT", "INVALID"):
        if candidate in statuses:
            return candidate
    return ""


def process_one_submission(
    rec: InputRecord,
    config: GConfig,
    test_cases: Dict[str, list],
    description_html: str = "",
    verbose: bool = False,
    trace_dir: str = "",
    trajectory_dir: Optional[str] = None,
) -> SubmissionResult:
    """Run G0, G1, or ITERG on one submission."""
    del test_cases
    t_start = time.time()
    writer = TrajectoryWriter(
        trajectory_dir,
        config.strategy,
        rec.submission_id,
        keep_full_text=bool(trace_dir),
    )

    client = LLMClient(config.to_llm_config())
    _debug_rounds: list[dict] = []
    max_iterations = getattr(config, "max_iterations", 1)
    patience = getattr(config, "patience", 1)
    ref_code = getattr(rec, "ref_code", "")
    prompt_view = resolve_prompt_view(rec)
    initial_targets = list(prompt_view.target_lines)
    tags = rec.uncovered_line_tags if hasattr(rec, "uncovered_line_tags") else {}
    current_targets = sorted(set(initial_targets))
    trajectory: List[IterationRecord] = []
    all_countercases: list[str] = []
    stagnation_count = 0
    first_countercase_round = None
    first_countercase_input = None

    from ACA.tool.sandbox import trace_coverage_dual

    def _finish(result: SubmissionResult) -> SubmissionResult:
        end_payload = compute_submission_end_fields(
            result.trajectory,
            initial_targets,
            result.final_uncovered_lines,
        )
        writer.append_event({
            "event_type": "submission_end",
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "terminated_reason": result.terminated_reason,
            "final_uncovered_lines": result.final_uncovered_lines,
            "total_iterations": result.iterations,
            "duplicate_exact_inputs": writer.duplicate_exact_inputs,
            "error": result.error,
            **end_payload,
        })
        writer.close()

        if trace_dir and _debug_rounds:
            all_msgs: list[dict] = []
            all_inputs: list[str] = []
            all_results: list = []
            last_response = None
            for rd in _debug_rounds:
                all_msgs.extend(rd.get("messages", []))
                all_inputs.extend(rd.get("test_inputs", []))
                all_results.extend(rd.get("dual_results", []))
                last_response = rd.get("response", last_response)
            write_debug_trace(
                trace_dir,
                rec.submission_id,
                messages=all_msgs,
                response=last_response,
                parsed_inputs=all_inputs or None,
                dual_results=all_results or None,
                strategy=config.strategy,
                terminated_reason=result.terminated_reason,
                final_uncovered_lines=result.final_uncovered_lines,
            )

        return result

    writer.append_event({
        "event_type": "submission_start",
        "strategy": config.strategy,
        "model": config.model,
        "submission_id": rec.submission_id,
        "pid": rec.pid,
        "source": rec.source,
        "source_kind": getattr(rec, "source_kind", None),
        "initial_target_lines": initial_targets,
        "code_size_lines": getattr(rec, "code_size_lines", None),
        "max_iterations": max_iterations,
        "patience": patience if config.strategy == "ITERG" else None,
        "run_timeout": getattr(config, "run_timeout", 10.0),
        "run_label": str(writer.path.parent.parent.parent) if writer.path else None,
        "trajectory_path": str(writer.path) if writer.path else None,
    })

    if not ref_code:
        return _finish(SubmissionResult(
            submission_id=rec.submission_id,
            pid=rec.pid,
            source=rec.source,
            strategy=config.strategy,
            trajectory=[],
            final_uncovered_lines=current_targets,
            terminated_reason="no_ref_code",
            countercases=[],
            total_newly_covered=0,
            total_stagnation=0,
            iterations=0,
            elapsed_sec=0.0,
        ))

    terminated_reason = "max_iterations" if config.strategy == "ITERG" else "single_round_complete"
    error_message = None

    for iteration in range(1, max_iterations + 1):
        if config.strategy == "ITERG" and not current_targets:
            terminated_reason = "all_covered"
            break

        visible_targets = initial_targets if config.strategy == "G0" else current_targets
        system_prompt = _system_prompt_for(config)
        user_msg = build_user_message(
            config=config,
            code_text=prompt_view.code_text,
            target_lines=visible_targets,
            uncovered_line_tags=tags,
            description_html=description_html,
            sample_input_anchor=getattr(rec, "sample_input_anchor", ""),
            gtor_prompt_profile=getattr(config, "gtor_prompt_profile", "legacy"),
            iteration=iteration,
            previous_failure_type=_previous_failure_type(trajectory),
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        debug_round = {"messages": messages, "response": None, "test_inputs": [], "dual_results": []}
        _debug_rounds.append(debug_round)

        prompt_text = f"{system_prompt}\n\n{user_msg}"
        writer.append_event({
            "event_type": "prompt_built",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "feedback_visible_level": _feedback_level(config.strategy),
            "qwen_output_constraint_mode": getattr(config, "qwen_output_constraint_mode", "auto"),
            "qwen_output_constraint_applied": bool(getattr(config, "qwen_output_constraint_applied", False)),
            "qwen_output_constraint_text": getattr(config, "qwen_output_constraint_text", ""),
            "seed_contract_clarification_applied": bool(getattr(config, "seed_contract_clarification_applied", False)),
            "seed_contract_clarification_text": getattr(config, "seed_contract_clarification_text", ""),
            "gtor_prompt_profile": getattr(config, "gtor_prompt_profile", "legacy"),
            "visible_seed_count_in_prompt": _visible_seed_count_in_prompt(config),
            "small_model_minimal_prompt_applied": getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal",
            "visible_uncovered_lines": visible_targets,
            "history_visible_to_llm": False,
            "prompt_hash": stable_hash(prompt_text),
            "prompt_text": prompt_text,
            "prompt_chars": len(prompt_text),
        })

        llm_t0 = time.time()
        try:
            response = client.call(messages, [])
        except Exception as exc:
            terminated_reason = "llm_error"
            error_message = str(exc)
            break
        llm_latency_ms = round((time.time() - llm_t0) * 1000, 1)
        debug_round["response"] = response

        extraction_status, generator_code = extract_generator_code(response)
        generator_code, norm_meta = normalize_generator_code_transport_escapes(generator_code or "")
        writer.append_event({
            "event_type": "llm_response",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "raw_response": response_payload_text(response),
            "raw_response_hash": stable_hash(response_payload_text(response)),
            "parse_ok": extraction_status != GENERATOR_EXTRACTION_ERROR,
            "parse_error": None if extraction_status != GENERATOR_EXTRACTION_ERROR else "generator_extraction_error",
            "num_extracted_inputs": 0,
            "finish_reason": response.response_metadata.get("finish_reason") if hasattr(response, "response_metadata") else None,
            "usage": response.response_metadata.get("usage") if hasattr(response, "response_metadata") else None,
            "latency_ms": llm_latency_ms,
        })
        writer.append_event({
            "event_type": "generator_code_extracted",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "extraction_status": extraction_status,
            "code_hash": stable_hash(generator_code or ""),
            "code_preview": safe_preview(generator_code or ""),
            "code_text": generator_code if writer.keep_full_text else None,
            "normalization_meta": norm_meta,
        })

        if extraction_status == GENERATOR_EXTRACTION_ERROR or not generator_code:
            terminated_reason = "generator_extraction_error"
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": visible_targets,
                "newly_covered_targets": [],
                "uncovered_after": current_targets,
                "num_inputs": 0,
                "num_valid": 0,
                "num_invalid": 0,
                "num_breakthroughs": len(all_countercases),
                "countercases_total": len(set(all_countercases)),
                "stagnation": True,
                "stagnation_counter": stagnation_count + 1,
                "terminated_reason_candidate": "generator_extraction_error",
                "should_continue": False,
            })
            break

        seeds = _seed_batch(config)
        configured_seed_list = list(seeds)
        writer.append_event({
            "event_type": "generator_code_built",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "num_seeds": len(seeds),
            "seed_list": seeds,
            "configured_seed_list": configured_seed_list,
            "actual_seed_list": list(seeds),
            "model_requested_seed_list": None,
            "seed_policy": "system_fixed",
            "seed_override_applied": False,
            "agent_tool_seed_source": "runtime_config",
            "gtor_prompt_profile": getattr(config, "gtor_prompt_profile", "legacy"),
            "visible_seed_count_in_prompt": _visible_seed_count_in_prompt(config),
            "small_model_minimal_prompt_applied": getattr(config, "gtor_prompt_profile", "legacy") == "small_model_minimal",
            "code_hash": stable_hash(generator_code),
            "code_preview": safe_preview(generator_code),
            "code_text": generator_code if writer.keep_full_text else None,
        })
        compile_result = compile_generator_code(
            generator_code,
            max_code_bytes=getattr(config, "generator_max_code_bytes", 256 * 1024),
        )
        writer.append_event({
            "event_type": "generator_compile",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "compile_status": compile_result.status,
            "compile_ok": compile_result.ok,
            "compile_error": compile_result.error,
            "code_bytes": compile_result.code_bytes,
        })
        if not compile_result.ok:
            terminated_reason = "generator_compile_error"
            error_message = compile_result.error
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": visible_targets,
                "newly_covered_targets": [],
                "uncovered_after": current_targets,
                "num_inputs": 0,
                "num_valid": 0,
                "num_invalid": 0,
                "num_breakthroughs": len(all_countercases),
                "countercases_total": len(set(all_countercases)),
                "stagnation": True,
                "stagnation_counter": stagnation_count + 1,
                "terminated_reason_candidate": "generator_compile_error",
                "should_continue": False,
            })
            break
        gen_results = run_generator_code(
            generator_code,
            seeds=seeds,
            timeout=config.generator_timeout,
            memory_mb=config.generator_memory_mb,
            max_output_bytes=config.generator_max_output_bytes,
        )

        generated_inputs: List[str] = []
        generated_reasons: List[str] = []
        generated_seed_map: List[int] = []
        for item in gen_results:
            writer.append_event({
                "event_type": "generator_run",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "seed": item.seed,
                "generator_status": item.status,
                "stdout": getattr(item, "stdout", item.stdout_preview),
                "stderr": getattr(item, "stderr", item.stderr_preview),
                "runtime_sec": round(item.runtime_sec, 4),
                "generator_error": item.error,
            })
            if item.status == "GEN_OK" and item.input_text is not None:
                generated_inputs.append(item.input_text)
                generated_reasons.append(f"generator_seed={item.seed}")
                generated_seed_map.append(item.seed)

        debug_round["test_inputs"] = generated_inputs
        input_entries = writer.make_input_entries(iteration, generated_inputs, generated_reasons)
        writer.append_event({
            "event_type": "inputs_extracted",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "num_inputs": len(input_entries),
            "inputs": input_entries,
        })
        for idx, entry in enumerate(input_entries):
            writer.append_event({
                "event_type": "generated_input",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "seed": generated_seed_map[idx] if idx < len(generated_seed_map) else None,
                **entry,
            })

        if not generated_inputs:
            terminated_reason = "no_inputs_generated"
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": visible_targets,
                "newly_covered_targets": [],
                "uncovered_after": current_targets,
                "num_inputs": 0,
                "num_valid": 0,
                "num_invalid": 0,
                "num_breakthroughs": len(all_countercases),
                "countercases_total": len(set(all_countercases)),
                "stagnation": True,
                "stagnation_counter": stagnation_count + 1,
                "terminated_reason_candidate": "no_inputs_generated",
                "should_continue": False,
            })
            break

        dual_results = trace_coverage_dual(
            rec.code,
            ref_code,
            generated_inputs,
            timeout=getattr(config, "run_timeout", 10.0),
            memory_mb=256,
            pid=rec.pid,
        )
        debug_round["dual_results"] = dual_results

        per_case_results = []
        breakthroughs = []
        new_covered = set()
        valid_count = 0
        invalid_count = 0
        target_set = set(current_targets)
        for idx, (inp, dr) in enumerate(zip(generated_inputs, dual_results)):
            per_case_results.append(CaseResult(
                test_input=inp,
                status=dr.status,
                covered_lines=dr.covered_lines,
                stdout=dr.stdout,
                stderr=dr.stderr,
                expected_output=dr.expected_output,
                timed_out=(dr.status == "TIMEOUT"),
                is_ac=(dr.status == "AC"),
            ))
            valid = is_valid_dual_status(dr.status)
            if valid:
                valid_count += 1
            else:
                invalid_count += 1
            if dr.breakthrough:
                breakthroughs.append(inp)
                if inp not in all_countercases:
                    all_countercases.append(inp)
                    if first_countercase_round is None:
                        first_countercase_round = iteration
                        first_countercase_input = inp
            new_covered.update(dr.covered_lines)
            writer.append_event({
                "event_type": "sandbox_result",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "input_id": input_entries[idx]["input_id"],
                "input_hash": input_entries[idx]["input_hash"],
                "status": dr.status,
                "breakthrough": dr.breakthrough,
                "valid": valid,
                "reference_ok": dr.reference_ok,
                "stdout": dr.stdout,
                "stderr": dr.stderr,
                "expected_output": dr.expected_output,
                "covered_lines": dr.covered_lines,
                "newly_covered_targets": sorted(target_set & set(dr.covered_lines)),
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

        newly_covered_targets = sorted(target_set & new_covered)
        final_uncovered = sorted(target_set - set(newly_covered_targets))
        iteration_record = IterationRecord(
            iteration=iteration,
            uncovered_before=visible_targets,
            test_inputs=generated_inputs,
            per_case_results=per_case_results,
            newly_covered=newly_covered_targets,
            breakthroughs=breakthroughs,
            thought_process=response.content if hasattr(response, "content") else "",
            stagnation=len(newly_covered_targets) == 0 and len(breakthroughs) == 0,
        )
        trajectory.append(iteration_record)

        if iteration_record.stagnation:
            stagnation_count += 1
        else:
            stagnation_count = 0

        should_continue = False
        terminated_reason_candidate = None
        if breakthroughs:
            terminated_reason = "countercase_found" if config.strategy == "ITERG" else "single_round_complete"
        elif not final_uncovered and config.strategy == "ITERG":
            terminated_reason = "all_covered"
        elif config.strategy == "ITERG" and stagnation_count >= patience:
            terminated_reason = "stagnation"
        elif config.strategy == "ITERG" and iteration < max_iterations:
            should_continue = True
            terminated_reason_candidate = None
        else:
            terminated_reason = "single_round_complete" if config.strategy != "ITERG" else "max_iterations"

        if breakthroughs:
            terminated_reason_candidate = "countercase_found"
        elif not final_uncovered and config.strategy == "ITERG":
            terminated_reason_candidate = "all_covered"
        elif config.strategy == "ITERG" and stagnation_count >= patience:
            terminated_reason_candidate = "stagnation"
        elif config.strategy != "ITERG":
            terminated_reason_candidate = "single_round_complete"

        writer.append_event({
            "event_type": "iteration_state_update",
            "iteration": iteration,
            "submission_id": rec.submission_id,
            "uncovered_before": visible_targets,
            "newly_covered_targets": newly_covered_targets,
            "uncovered_after": final_uncovered,
            "num_inputs": len(generated_inputs),
            "num_valid": valid_count,
            "num_invalid": invalid_count,
            "num_breakthroughs": len(breakthroughs),
            "countercases_total": len(set(all_countercases)),
            "stagnation": iteration_record.stagnation,
            "stagnation_counter": stagnation_count,
            "terminated_reason_candidate": terminated_reason_candidate,
            "should_continue": should_continue,
        })

        current_targets = final_uncovered
        if not should_continue:
            break

    elapsed = time.time() - t_start
    if verbose:
        print(
            f"  [{rec.submission_id}] {config.strategy} | "
            f"{sum(len(it.newly_covered) for it in trajectory)} newly covered | "
            f"{len(set(all_countercases))} CCs | {len(trajectory)} iters | {elapsed:.1f}s",
            flush=True,
        )

    return _finish(SubmissionResult(
        submission_id=rec.submission_id,
        pid=rec.pid,
        source=rec.source,
        strategy=config.strategy,
        trajectory=trajectory,
        final_uncovered_lines=current_targets,
        terminated_reason=terminated_reason,
        countercases=list(dict.fromkeys(all_countercases)),
        total_newly_covered=sum(len(it.newly_covered) for it in trajectory),
        total_stagnation=sum(1 for it in trajectory if it.stagnation),
        iterations=len(trajectory),
        elapsed_sec=round(elapsed, 1),
        stop_reason=terminated_reason,
        first_countercase_round=first_countercase_round,
        first_countercase_input=first_countercase_input,
        error=error_message,
    ))
