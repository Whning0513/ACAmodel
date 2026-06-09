"""ACA tool — shared sandbox, coverage tracing, and data loading."""

from .generator_runner import GeneratorRunResult, run_generator_code
from .sandbox import (
    CoverageResult,
    DualRunResult,
    ExecutionResult,
    compute_uncovered_lines,
    execute_code,
    get_candidate_lines,
    trace_coverage,
    trace_coverage_batch,
    trace_coverage_dual,
)
