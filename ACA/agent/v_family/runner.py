"""V-family runner: process_one_submission for V0.

V0 = recursive L1 — the L1 prompt but in a multi-round loop:
  1. Generate test inputs targeting current uncovered lines
  2. Execute via sandbox
  3. Update uncovered lines
  4. Repeat until all covered, max_iterations, or stagnation

No LangGraph dependency — just a simple state machine loop.
"""

import time
from typing import Dict, List, Optional

from ACA.agent.l_family.prompts import (
    L1_SYSTEM_PROMPT,
    L0_TOOLS,
    build_user_message,
)
from ACA.agent.shared.datatypes import (
    CaseResult,
    IterationRecord,
    SubmissionResult,
)
from ACA.agent.shared.llm_client import LLMClient
from ACA.agent.shared.trajectory import (
    TrajectoryWriter,
    compute_submission_end_fields,
    response_payload_text,
    safe_preview,
    stable_hash,
    write_debug_trace,
)
from ACA.agent.shared.tool_utils import extract_test_inputs
from ACA.agent.shared.tool_utils import validate_exact_batch
from ACA.agent.shared.prompt_templates import resolve_prompt_view
from ACA.agent.shared.verdicts import is_valid_dual_status
from ACA.agent.v_family.config import V0Config
from ACA.tool.problem_loader import SubmissionRecord as InputRecord


def process_one_submission(
    rec: InputRecord,
    config: V0Config,
    test_cases: Dict[str, list],
    description_html: str = "",
    verbose: bool = False,
    trace_dir: str = "",
    trajectory_dir: Optional[str] = None,
) -> SubmissionResult:
    """Run V0 (recursive L1) on one submission."""
    t_start = time.time()
    writer = TrajectoryWriter(
        trajectory_dir,
        config.strategy,
        rec.submission_id,
        keep_full_text=bool(trace_dir),
    )

    client = LLMClient(config.to_llm_config())
    from ACA.tool.sandbox import trace_coverage_dual

    ref_code = getattr(rec, 'ref_code', '')
    writer.append_event({
        "event_type": "submission_start",
        "strategy": config.strategy,
        "model": config.model,
        "submission_id": rec.submission_id,
        "pid": rec.pid,
        "source": rec.source,
        "source_kind": getattr(rec, "source_kind", None),
        "initial_target_lines": rec.uncovered_effective_lines,
        "code_size_lines": getattr(rec, "code_size_lines", None),
        "max_iterations": getattr(config, "max_iterations", None),
        "patience": getattr(config, "patience", None),
        "run_timeout": getattr(config, "run_timeout", None),
        "run_label": str(writer.path.parent.parent.parent) if writer.path else None,
        "trajectory_path": str(writer.path) if writer.path else None,
    })

    _debug_rounds: list = []

    def _finish(result: SubmissionResult) -> SubmissionResult:
        end_payload = compute_submission_end_fields(
            result.trajectory,
            rec.uncovered_effective_lines,
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
            # Flatten all rounds into one debug trace
            all_msgs: list[dict] = []
            all_inputs: list[str] = []
            all_results: list = []
            for rd in _debug_rounds:
                all_msgs.extend(rd.get("messages", []))
                all_inputs.extend(rd.get("test_inputs", []))
                all_results.extend(rd.get("dual_results", []))
            write_debug_trace(
                trace_dir, rec.submission_id,
                messages=all_msgs,
                parsed_inputs=all_inputs or None,
                dual_results=all_results or None,
                strategy=config.strategy,
                terminated_reason=result.terminated_reason,
                final_uncovered_lines=result.final_uncovered_lines,
            )

        return result

    if not ref_code:
        return _finish(SubmissionResult(
            submission_id=rec.submission_id,
            pid=rec.pid,
            source=rec.source,
            strategy=config.strategy,
            trajectory=[],
            final_uncovered_lines=rec.uncovered_effective_lines,
            terminated_reason="no_ref_code",
            countercases=[],
            total_newly_covered=0,
            total_stagnation=0,
            iterations=0,
            elapsed_sec=0.0,
        ))

    # U_t: dynamic uncovered target set, shrinks as lines get covered over iterations
    prompt_view = resolve_prompt_view(rec)
    U_t = sorted(set(prompt_view.target_lines))
    tags = rec.uncovered_line_tags if hasattr(rec, 'uncovered_line_tags') else {}
    trajectory: List[IterationRecord] = []
    all_countercases = set()
    stagnation_count = 0
    terminated_reason = "max_iterations"
    first_countercase_round = None
    first_countercase_input = None

    for iteration in range(1, config.max_iterations + 1):
        if not U_t:
            terminated_reason = "all_covered"
            break

        # Build prompt for current uncovered lines
        system_prompt = L1_SYSTEM_PROMPT.format(test_input_count=config.test_input_count)
        user_msg = build_user_message(
            config=config,
            code_text=prompt_view.code_text,
            target_lines=U_t,
            uncovered_line_tags=tags,
            description_html=description_html,
            sample_input_anchor=getattr(rec, 'sample_input_anchor', ''),
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        _debug_rounds.append({"messages": messages, "test_inputs": [], "dual_results": []})

        prompt_text = f"{system_prompt}\n\n{user_msg}"
        writer.append_event({
            "event_type": "prompt_built",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "feedback_visible_level": "updated_uncovered_set_only",
                "visible_uncovered_lines": U_t.copy(),
            "history_visible_to_llm": False,
            "prompt_hash": stable_hash(prompt_text),
            "prompt_text": prompt_text,
            "prompt_chars": len(prompt_text),
        })

        # Call LLM
        llm_t0 = time.time()
        try:
            response = client.call(messages, L0_TOOLS)
        except Exception as e:
            terminated_reason = "llm_error"
            break
        llm_latency_ms = round((time.time() - llm_t0) * 1000, 1)

        # Check LLM parse repair / retry metadata
        _parse_meta = getattr(response, 'additional_kwargs', {}).get('_parse_meta', {})
        if _parse_meta.get('llm_parse_failed'):
            writer.append_event({
                "event_type": "llm_response",
                "iteration": iteration,
                "strategy": config.strategy,
                "submission_id": rec.submission_id,
                "raw_response": response_payload_text(response),
                "raw_response_hash": stable_hash(response_payload_text(response)),
                "parse_ok": False,
                "parse_error": _parse_meta.get('final_error', 'JSON parse failed after retry'),
                "num_extracted_inputs": 0,
                "parse_repair_used": _parse_meta.get('parse_repair_used', False),
                "first_parse_error": _parse_meta.get("first_error"),
                "first_finish_reason": _parse_meta.get("first_finish_reason"),
                "finish_reason": response.response_metadata.get("finish_reason") if hasattr(response, "response_metadata") else None,
                "usage": response.response_metadata.get("usage") if hasattr(response, "response_metadata") else None,
                "latency_ms": llm_latency_ms,
            })
            terminated_reason = "llm_parse_failed"
            break
        _parse_repair_used = _parse_meta.get('parse_repair_used', False)

        test_inputs, reasons = extract_test_inputs(response)
        batch_error = validate_exact_batch(test_inputs, reasons, config.test_input_count) if test_inputs else None
        if batch_error:
            test_inputs = []
            reasons = []
        _debug_rounds[-1]["test_inputs"] = test_inputs
        is_llm_api_error = (
            not getattr(response, "tool_calls", None)
            and bool(getattr(response, "content", ""))
            and str(getattr(response, "content", "")).startswith("[LLM API Error]")
        )
        writer.append_event({
            "event_type": "llm_response",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "raw_response": response_payload_text(response),
            "raw_response_hash": stable_hash(response_payload_text(response)),
            "parse_ok": bool(test_inputs),
            "parse_error": (
                None if test_inputs else (
                    "llm_api_error" if is_llm_api_error else (batch_error or "no_inputs_extracted")
                )
            ),
            "num_extracted_inputs": len(test_inputs),
            "parse_repair_used": _parse_repair_used,
            "first_parse_error": _parse_meta.get("first_error") if _parse_repair_used else None,
            "first_finish_reason": _parse_meta.get("first_finish_reason") if _parse_repair_used else None,
            "finish_reason": response.response_metadata.get("finish_reason") if hasattr(response, "response_metadata") else None,
            "usage": response.response_metadata.get("usage") if hasattr(response, "response_metadata") else None,
            "latency_ms": llm_latency_ms,
        })

        if not test_inputs:
            stagnation_count += 1
            writer.append_event({
                "event_type": "inputs_extracted",
                "iteration": iteration,
                "strategy": config.strategy,
                "submission_id": rec.submission_id,
                "num_inputs": 0,
                "inputs": [],
            })
            should_continue = stagnation_count < config.patience
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": U_t.copy(),
                "newly_covered_targets": [],
                "uncovered_after": U_t.copy(),
                "num_inputs": 0,
                "num_valid": 0,
                "num_invalid": 0,
                "num_breakthroughs": 0,
                "countercases_total": len(all_countercases),
                "stagnation": True,
                "stagnation_counter": stagnation_count,
                "terminated_reason_candidate": "stagnation" if not should_continue else None,
                "should_continue": should_continue,
            })
            if stagnation_count >= config.patience:
                terminated_reason = "llm_error" if is_llm_api_error else "stagnation"
                break
            if is_llm_api_error:
                terminated_reason = "llm_error"
                break
            if batch_error:
                terminated_reason = "invalid_input_count"
                break
            continue

        input_entries = writer.make_input_entries(iteration, test_inputs, reasons)
        writer.append_event({
            "event_type": "inputs_extracted",
            "iteration": iteration,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "num_inputs": len(input_entries),
            "inputs": input_entries,
        })

        # Execute via dual-run sandbox — reference code computes expected output
        dual_results = trace_coverage_dual(
            rec.code, ref_code, test_inputs, timeout=config.run_timeout, memory_mb=256,
            pid=rec.pid,
        )
        _debug_rounds[-1]["dual_results"] = dual_results

        per_case_results = []
        breakthroughs = []
        new_covered = set()
        valid_count = 0
        invalid_count = 0
        for idx, (inp, dr) in enumerate(zip(test_inputs, dual_results)):
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

            # Breakthrough: input found WA/RE — a confirmed bug in student code
            if dr.breakthrough:
                breakthroughs.append(inp)
                all_countercases.add(inp)
                if first_countercase_round is None:
                    first_countercase_round = iteration
                    first_countercase_input = inp
            new_covered.update(dr.covered_lines)
            newly_covered_targets_for_input = sorted(set(U_t) & set(dr.covered_lines))
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
                "newly_covered_targets": newly_covered_targets_for_input,
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

        newly_covered_targets = sorted(set(U_t) & new_covered)

        trajectory.append(IterationRecord(
            iteration=iteration,
            uncovered_before=U_t.copy(),
            test_inputs=test_inputs,
            per_case_results=per_case_results,
            newly_covered=newly_covered_targets,
            breakthroughs=breakthroughs,
            thought_process=response.content if hasattr(response, 'content') else "",
            # Stagnation: round produced neither coverage progress nor breakthrough CCs
            stagnation=len(newly_covered_targets) == 0 and len(breakthroughs) == 0,
        ))

        # Reset stagnation counter if any progress (coverage or breakthroughs)
        if newly_covered_targets or breakthroughs:
            stagnation_count = 0
        else:
            stagnation_count += 1

        if breakthroughs and getattr(config, "stop_on_first_hack", True):
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": trajectory[-1].uncovered_before,
                "newly_covered_targets": newly_covered_targets,
                "uncovered_after": sorted(set(U_t) - set(newly_covered_targets)),
                "num_inputs": len(test_inputs),
                "num_valid": valid_count,
                "num_invalid": invalid_count,
                "num_breakthroughs": len(breakthroughs),
                "countercases_total": len(all_countercases),
                "stagnation": trajectory[-1].stagnation,
                "stagnation_counter": stagnation_count,
                "terminated_reason_candidate": "countercase_found",
                "should_continue": False,
            })
            terminated_reason = "countercase_found"
            U_t = sorted(set(U_t) - set(newly_covered_targets))
            break

        if stagnation_count >= config.patience:
            writer.append_event({
                "event_type": "iteration_state_update",
                "iteration": iteration,
                "submission_id": rec.submission_id,
                "uncovered_before": trajectory[-1].uncovered_before,
                "newly_covered_targets": newly_covered_targets,
                "uncovered_after": sorted(set(U_t) - set(newly_covered_targets)),
                "num_inputs": len(test_inputs),
                "num_valid": valid_count,
                "num_invalid": invalid_count,
                "num_breakthroughs": len(breakthroughs),
                "countercases_total": len(all_countercases),
                "stagnation": trajectory[-1].stagnation,
                "stagnation_counter": stagnation_count,
                "terminated_reason_candidate": "stagnation",
                "should_continue": False,
            })
            terminated_reason = "stagnation"
            break

        next_uncovered = sorted(set(U_t) - set(newly_covered_targets))
        writer.append_event({
            "event_type": "iteration_state_update",
            "iteration": iteration,
            "submission_id": rec.submission_id,
            "uncovered_before": trajectory[-1].uncovered_before,
            "newly_covered_targets": newly_covered_targets,
            "uncovered_after": next_uncovered,
            "num_inputs": len(test_inputs),
            "num_valid": valid_count,
            "num_invalid": invalid_count,
            "num_breakthroughs": len(breakthroughs),
            "countercases_total": len(all_countercases),
            "stagnation": trajectory[-1].stagnation,
            "stagnation_counter": stagnation_count,
            "terminated_reason_candidate": "all_covered" if not next_uncovered else None,
            "should_continue": bool(next_uncovered),
        })
        U_t = sorted(set(U_t) - set(newly_covered_targets))

    elapsed = time.time() - t_start

    if verbose:
        total_cc = len(all_countercases)
        total_cov = sum(len(it.newly_covered) for it in trajectory)
        print(
            f"  [{rec.submission_id}] {terminated_reason} | "
            f"{total_cov} newly covered | "
            f"{total_cc} CCs | {len(trajectory)} iters | {elapsed:.1f}s",
            flush=True,
        )

    result = SubmissionResult(
        submission_id=rec.submission_id,
        pid=rec.pid,
        source=rec.source,
        strategy=config.strategy,
        trajectory=trajectory,
        final_uncovered_lines=U_t,
        terminated_reason=terminated_reason,
        countercases=list(all_countercases),
        total_newly_covered=sum(len(it.newly_covered) for it in trajectory),
        total_stagnation=sum(1 for it in trajectory if it.stagnation),
        iterations=len(trajectory),
        elapsed_sec=round(elapsed, 1),
        stop_reason=terminated_reason,
        first_countercase_round=first_countercase_round,
        first_countercase_input=first_countercase_input,
        error=(
            getattr(response, "additional_kwargs", {}).get("llm_error", {}).get("message")
            if terminated_reason == "llm_error"
            else None
        ),
    )
    return _finish(result)
