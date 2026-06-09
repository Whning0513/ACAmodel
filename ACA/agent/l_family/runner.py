"""L-family runner: process_one_submission for L0 and L1.

L0: single-round, target-only prompt.
L1: single-round, mismatch-augment prompt (annotated uncovered lines).

Both are non-agent — they call the LLM once, execute the generated inputs
via the sandbox, and return results. No LangGraph dependency.
"""

import time
from typing import Dict, List, Optional

from ACA.agent.l_family.config import LConfig
from ACA.agent.l_family.prompts import (
    L0_SYSTEM_PROMPT,
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
from ACA.tool.problem_loader import SubmissionRecord as InputRecord


def _feedback_level(strategy: str) -> str:
    return "none" if strategy == "L0" else "static_uncovered_annotation"


def process_one_submission(
    rec: InputRecord,
    config: LConfig,
    test_cases: Dict[str, list],
    description_html: str = "",
    verbose: bool = False,
    trace_dir: str = "",
    trajectory_dir: Optional[str] = None,
) -> SubmissionResult:
    """Run L0 or L1 on one submission.

    Args:
        rec: SubmissionRecord from ACA.tool.problem_loader.
        config: L0Config or L1Config.
        test_cases: pid → [{input, _norm_out}, ...].
        description_html: Problem description HTML.
        verbose: Print debug output.

    Returns:
        SubmissionResult.
    """
    t_start = time.time()
    writer = TrajectoryWriter(
        trajectory_dir,
        config.strategy,
        rec.submission_id,
        keep_full_text=bool(trace_dir),
    )

    # Debug context: collected throughout the pipeline, written at the end
    _debug_ctx: dict = {"messages": [], "response": None, "test_inputs": [], "dual_results": []}

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

        if trace_dir:
            write_debug_trace(
                trace_dir, rec.submission_id,
                messages=_debug_ctx["messages"],
                response=_debug_ctx["response"],
                parsed_inputs=_debug_ctx["test_inputs"] or None,
                dual_results=_debug_ctx["dual_results"] or None,
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
        "initial_target_lines": rec.uncovered_effective_lines,
        "code_size_lines": getattr(rec, "code_size_lines", None),
        "max_iterations": 1,
        "patience": None,
        "run_timeout": 10,
        "run_label": str(writer.path.parent.parent.parent) if writer.path else None,
        "trajectory_path": str(writer.path) if writer.path else None,
    })

    client = LLMClient(config.to_llm_config())

    # Build messages
    system_prompt = L0_SYSTEM_PROMPT if config.strategy == "L0" else L1_SYSTEM_PROMPT
    system_prompt = system_prompt.format(test_input_count=config.test_input_count)

    tags = rec.uncovered_line_tags if hasattr(rec, 'uncovered_line_tags') else {}
    prompt_view = resolve_prompt_view(rec)
    user_msg = build_user_message(
        config=config,
        code_text=prompt_view.code_text,
        target_lines=prompt_view.target_lines,
        uncovered_line_tags=tags,
        description_html=description_html,
        sample_input_anchor=getattr(rec, 'sample_input_anchor', ''),
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    _debug_ctx["messages"] = messages

    prompt_text = f"{system_prompt}\n\n{user_msg}"
    writer.append_event({
        "event_type": "prompt_built",
        "iteration": 1,
        "strategy": config.strategy,
        "submission_id": rec.submission_id,
        "feedback_visible_level": _feedback_level(config.strategy),
        "visible_uncovered_lines": rec.uncovered_effective_lines,
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
        elapsed = time.time() - t_start
        result = SubmissionResult(
            submission_id=rec.submission_id,
            pid=rec.pid,
            source=rec.source,
            strategy=config.strategy,
            trajectory=[],
            final_uncovered_lines=rec.uncovered_effective_lines,
            terminated_reason="llm_error",
            countercases=[],
            total_newly_covered=0,
            total_stagnation=0,
            iterations=0,
            elapsed_sec=round(elapsed, 1),
            error=str(e),
        )
        _debug_ctx["trace_reason"] = "llm_error"
        return _finish(result)
    llm_latency_ms = round((time.time() - llm_t0) * 1000, 1)

    _debug_ctx["response"] = response

    # Check LLM parse repair / retry metadata
    _parse_meta = getattr(response, 'additional_kwargs', {}).get('_parse_meta', {})
    if _parse_meta.get('llm_parse_failed'):
        writer.append_event({
            "event_type": "llm_response",
            "iteration": 1,
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
        _debug_ctx["trace_reason"] = "llm_parse_failed"
        elapsed = time.time() - t_start
        return _finish(SubmissionResult(
            submission_id=rec.submission_id,
            pid=rec.pid,
            source=rec.source,
            strategy=config.strategy,
            trajectory=[],
            final_uncovered_lines=rec.uncovered_effective_lines,
            terminated_reason="llm_parse_failed",
            countercases=[],
            total_newly_covered=0,
            total_stagnation=0,
            iterations=0,
            elapsed_sec=round(elapsed, 1),
            error=_parse_meta.get('final_error', 'JSON parse failed after retry'),
        ))
    _parse_repair_used = _parse_meta.get('parse_repair_used', False)

    test_inputs, reasons = extract_test_inputs(response)
    batch_error = validate_exact_batch(test_inputs, reasons, config.test_input_count) if test_inputs else None
    if batch_error:
        test_inputs = []
        reasons = []
    _debug_ctx["test_inputs"] = test_inputs
    is_llm_api_error = (
        not getattr(response, "tool_calls", None)
        and bool(getattr(response, "content", ""))
        and str(getattr(response, "content", "")).startswith("[LLM API Error]")
    )
    writer.append_event({
        "event_type": "llm_response",
        "iteration": 1,
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
        _debug_ctx["test_inputs"] = test_inputs
        elapsed = time.time() - t_start
        writer.append_event({
            "event_type": "inputs_extracted",
            "iteration": 1,
            "strategy": config.strategy,
            "submission_id": rec.submission_id,
            "num_inputs": 0,
            "inputs": [],
        })
        writer.append_event({
            "event_type": "iteration_state_update",
            "iteration": 1,
            "submission_id": rec.submission_id,
            "uncovered_before": rec.uncovered_effective_lines,
            "newly_covered_targets": [],
            "uncovered_after": rec.uncovered_effective_lines,
            "num_inputs": 0,
            "num_valid": 0,
            "num_invalid": 0,
            "num_breakthroughs": 0,
            "countercases_total": 0,
            "stagnation": True,
            "stagnation_counter": 1,
            "terminated_reason_candidate": "no_inputs_generated",
            "should_continue": False,
        })
        terminated_reason = (
            "llm_error" if is_llm_api_error else ("invalid_input_count" if batch_error else "no_inputs_generated")
        )
        error = (
            getattr(response, "additional_kwargs", {}).get("llm_error", {}).get("message")
            if is_llm_api_error
            else None
        )
        return _finish(SubmissionResult(
            submission_id=rec.submission_id,
            pid=rec.pid,
            source=rec.source,
            strategy=config.strategy,
            trajectory=[],
            final_uncovered_lines=rec.uncovered_effective_lines,
            terminated_reason=terminated_reason,
            countercases=[],
            total_newly_covered=0,
            total_stagnation=0,
            iterations=0,
            elapsed_sec=round(elapsed, 1),
            stop_reason=terminated_reason,
            error=error or batch_error,
        ))

    input_entries = writer.make_input_entries(1, test_inputs, reasons)
    writer.append_event({
        "event_type": "inputs_extracted",
        "iteration": 1,
        "strategy": config.strategy,
        "submission_id": rec.submission_id,
        "num_inputs": len(input_entries),
        "inputs": input_entries,
    })

    # Execute via dual-run sandbox — reference code computes expected output on the fly
    from ACA.tool.sandbox import trace_coverage_dual

    ref_code = getattr(rec, 'ref_code', '')
    if not ref_code:
        elapsed = time.time() - t_start
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
            elapsed_sec=round(elapsed, 1),
        ))

    dual_results = trace_coverage_dual(
        rec.code,
        ref_code,
        test_inputs,
        timeout=getattr(config, "run_timeout", 30),
        memory_mb=256,
        pid=rec.pid,
    )
    _debug_ctx["dual_results"] = dual_results

    # Build per-case results from dual-run verdicts
    per_case_results = []
    breakthroughs = []
    new_covered = set()
    valid_count = 0
    invalid_count = 0
    target_set = set(rec.uncovered_effective_lines)
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
        new_covered.update(dr.covered_lines)
        newly_covered_targets = sorted(target_set & set(dr.covered_lines))
        writer.append_event({
            "event_type": "sandbox_result",
            "iteration": 1,
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
            "newly_covered_targets": newly_covered_targets,
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

    # Determine newly covered target lines
    newly_covered_targets = sorted(target_set & new_covered)

    iteration_record = IterationRecord(
        iteration=1,
        uncovered_before=rec.uncovered_effective_lines,
        test_inputs=test_inputs,
        per_case_results=per_case_results,
        newly_covered=newly_covered_targets,
        breakthroughs=breakthroughs,
        thought_process=response.content if hasattr(response, 'content') else "",
        # Stagnation: round produced neither coverage progress nor breakthrough CCs
        stagnation=len(newly_covered_targets) == 0 and len(breakthroughs) == 0,
    )

    final_uncovered = sorted(target_set - set(newly_covered_targets))
    writer.append_event({
        "event_type": "iteration_state_update",
        "iteration": 1,
        "submission_id": rec.submission_id,
        "uncovered_before": rec.uncovered_effective_lines,
        "newly_covered_targets": newly_covered_targets,
        "uncovered_after": final_uncovered,
        "num_inputs": len(test_inputs),
        "num_valid": valid_count,
        "num_invalid": invalid_count,
        "num_breakthroughs": len(breakthroughs),
        "countercases_total": len(set(breakthroughs)),
        "stagnation": iteration_record.stagnation,
        "stagnation_counter": 1 if iteration_record.stagnation else 0,
        "terminated_reason_candidate": "single_round_complete",
        "should_continue": False,
    })
    elapsed = time.time() - t_start

    if verbose:
        print(
            f"  [{rec.submission_id}] {config.strategy} | "
            f"{len(newly_covered_targets)} newly covered | "
            f"{len(breakthroughs)} CCs | {elapsed:.1f}s",
            flush=True,
        )

    return _finish(SubmissionResult(
        submission_id=rec.submission_id,
        pid=rec.pid,
        source=rec.source,
        strategy=config.strategy,
        trajectory=[iteration_record],
        final_uncovered_lines=final_uncovered,
        terminated_reason="single_round_complete",
        countercases=breakthroughs,
        total_newly_covered=len(newly_covered_targets),
        # Stagnation: round produced neither coverage progress nor breakthrough CCs
        total_stagnation=1 if (len(newly_covered_targets) == 0 and len(breakthroughs) == 0) else 0,
        iterations=1,
        elapsed_sec=round(elapsed, 1),
        stop_reason="single_round_complete",
        error=None,
    ))
