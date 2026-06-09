"""Shared data types for agent processing results."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class CaseResult:
    """Result of executing a single test case."""
    test_input: str
    status: str                        # "AC" | "WA" | "RE" | "TLE" | "MLE" | "OOM" | "INVALID" | ...
    covered_lines: List[int] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    expected_output: str = ""
    timed_out: bool = False
    # True if student output matches reference — for this single input, not the whole submission
    is_ac: bool = False


@dataclass
class IterationRecord:
    """Snapshot of one agent iteration."""
    iteration: int
    uncovered_before: List[int]
    test_inputs: List[str]             # inputs submitted in this batch
    per_case_results: List[CaseResult]
    newly_covered: List[int]
    breakthroughs: List[str]           # inputs that caused WA/RE/TLE/MLE/OOM
    thought_process: str
    stagnation: bool                   # True iff this round achieved NEITHER:
                                       #   - newly covered any target line
                                       #   - found any breakthrough (CC)
                                       # A round with breakthroughs but no coverage is
                                       # NOT stagnation — finding bugs is progress.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "uncovered_before": self.uncovered_before,
            "test_inputs": self.test_inputs,
            "newly_covered": self.newly_covered,
            "breakthroughs": self.breakthroughs,
            "thought_process": self.thought_process,
            "stagnation": self.stagnation,
            "per_case_results": [
                {
                    "test_input": cr.test_input,
                    "status": cr.status,
                    "covered_lines": cr.covered_lines,
                    "stdout": cr.stdout,
                    "stderr": cr.stderr,
                    "expected_output": cr.expected_output,
                    "is_ac": cr.is_ac,
                }
                for cr in self.per_case_results
            ],
        }


@dataclass
class SubmissionResult:
    """Complete agent processing result for one submission."""
    submission_id: str
    pid: str
    source: str
    strategy: str
    trajectory: List[IterationRecord]
    final_uncovered_lines: List[int]
    terminated_reason: str
    countercases: List[str]
    total_newly_covered: int
    total_stagnation: int             # count of iterations where stagnation=True
    iterations: int
    elapsed_sec: float
    stop_reason: Optional[str] = None
    first_countercase_round: Optional[int] = None
    first_countercase_input: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "submission_id": self.submission_id,
            "pid": self.pid,
            "source": self.source,
            "strategy": self.strategy,
            "trajectory": [t.to_dict() for t in self.trajectory],
            "final_uncovered_lines": self.final_uncovered_lines,
            "terminated_reason": self.terminated_reason,
            "countercases": self.countercases,
            "total_newly_covered": self.total_newly_covered,
            "total_stagnation": self.total_stagnation,
            "iterations": self.iterations,
            "elapsed_sec": self.elapsed_sec,
            "stop_reason": self.stop_reason,
            "first_countercase_round": self.first_countercase_round,
            "first_countercase_input": self.first_countercase_input,
            "error": self.error,
        }
