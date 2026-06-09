"""Agent state definition — aligned with step6 ndjson format.

Single source of truth for all strategy families. R-family extends this
with message history; L/V families use a subset.
"""

from typing import Annotated, Dict, List, Optional, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Unified agent state consumed by all strategy families.

    Fields come directly from step6 ndjson records and are augmented
    at runtime with problem descriptions and engine tracking.
    """

    # ── Step6 ndjson fields ──────────────────────────────────────────
    # All fields below are loaded directly from step6_final.ndjson records
    submission_id: str
    pid: str
    source: str                           # "origin" (real student submission from matrixstudio)
                                           # "constructed" (synthetic buggy variant we generated)
    code_text: str
    ref_code: str
    # Cases where student code output matches the reference solution (Accepted)
    ac_indices: List[int]
    # Cases where student code output differs from reference (Ground Truth bug indicator)
    gt_indices: List[int]
    uncovered_effective_lines: List[int]  # target lines for agent
    candidate_lines: List[int]            # all executable lines
    uncovered_line_tags: Dict[str, str]   # line → logic|io_read|io_write|debug_print|pass_stmt|control_flow
    ac_count: int
    gt_count: int
    total_cases: int
    ac_ratio: float
    max_depth: int
    code_size_lines: int
    code_size_chars: int

    # Constructed-only
    parent_submission_id: Optional[str]
    buggy_lines: Optional[List[int]]
    dropped_ac_indices: Optional[List[int]]

    # ── Problem metadata (loaded from references) ───────────────────
    description_html: str
    sample_input_anchor: str

    # ── Engine state ────────────────────────────────────────────────
    strategy: str
    iteration: int
    uncovered_lines: List[int]            # U_t — dynamically shrinking
    original_uncovered_lines: List[int]   # frozen snapshot at start
    stagnation_counter: int
    no_tool_call_count: int               # consecutive LLM responses without tool calls
    last_newly_covered: List[int]

    # ── Message window (R-family) ───────────────────────────────────
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # ── Structured trajectory data (R-family) ───────────────────────
    # Populated by _handle_run_and_trace alongside ToolMessage.
    # Avoids lossy text round-trip (ToolMessage → text parsing).
    # Each entry: {iteration, test_inputs, per_case_results,
    #               newly_covered, breakthroughs, stagnation}
    trajectory_data: List[dict]

    # ── Termination ─────────────────────────────────────────────────
    terminated_reason: str
    stop_reason: str
    error: str
    countercases: List[str]               # WA/RE/TLE/OOM-inducing test inputs found
    first_countercase_round: Optional[int]
    first_countercase_input: Optional[str]


def make_initial_state(
    submission_id: str,
    pid: str,
    source: str,
    code_text: str,
    prompt_code_text: str,
    ref_code: str,
    ac_indices: List[int],
    gt_indices: List[int],
    uncovered_effective_lines: List[int],
    candidate_lines: List[int],
    uncovered_line_tags: Dict[str, str],
    ac_count: int,
    gt_count: int,
    total_cases: int,
    ac_ratio: float,
    max_depth: int,
    code_size_lines: int,
    code_size_chars: int,
    description_html: str = "",
    sample_input_anchor: str = "",
    prompt_uncovered_lines: Optional[List[int]] = None,
    prompt_view_version: Optional[str] = None,
    strategy: str = "R1.1",
    parent_submission_id: Optional[str] = None,
    buggy_lines: Optional[List[int]] = None,
    dropped_ac_indices: Optional[List[int]] = None,
) -> dict:
    """Build the initial state dictionary from a step6 record + problem metadata."""
    return {
        "submission_id": submission_id,
        "pid": pid,
        "source": source,
        "code_text": code_text,
        "prompt_code_text": prompt_code_text,
        "ref_code": ref_code,
        "ac_indices": ac_indices,
        "gt_indices": gt_indices,
        "uncovered_effective_lines": uncovered_effective_lines,
        "candidate_lines": candidate_lines,
        "uncovered_line_tags": uncovered_line_tags,
        "ac_count": ac_count,
        "gt_count": gt_count,
        "total_cases": total_cases,
        "ac_ratio": ac_ratio,
        "max_depth": max_depth,
        "code_size_lines": code_size_lines,
        "code_size_chars": code_size_chars,
        "parent_submission_id": parent_submission_id,
        "buggy_lines": buggy_lines,
        "dropped_ac_indices": dropped_ac_indices,
        "description_html": description_html,
        "sample_input_anchor": sample_input_anchor,
        "prompt_uncovered_lines": list(prompt_uncovered_lines or uncovered_effective_lines),
        "prompt_view_version": prompt_view_version,
        "strategy": strategy,
        "iteration": 0,
        "uncovered_lines": list(uncovered_effective_lines),
        "original_uncovered_lines": list(uncovered_effective_lines),
        "stagnation_counter": 0,
        "no_tool_call_count": 0,
        "last_newly_covered": [],
        "messages": [],
        "trajectory_data": [],
        "terminated_reason": "",
        "stop_reason": "",
        "error": "",
        "countercases": [],
        "first_countercase_round": None,
        "first_countercase_input": None,
    }
