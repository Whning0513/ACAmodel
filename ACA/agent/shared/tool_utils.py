"""Shared utilities for parsing LLM tool call responses.

Used by L-family and V-family runners to extract test_inputs
from the standardized tool call schema.
"""

from typing import List, Tuple


def extract_test_inputs(msg) -> Tuple[List[str], List[str]]:
    """Extract test_inputs and reasons from a tool-call AIMessage.

    Returns (test_inputs, reasons) — both as lists of strings.
    Designed for the L0_TOOLS schema (function: provide_test_inputs).
    """
    if not hasattr(msg, "tool_calls") or not msg.tool_calls:
        return [], []
    tc = msg.tool_calls[0]
    args = tc.get("args", {})
    inputs = args.get("test_inputs", [])
    reasons = args.get("reasons", [])
    if isinstance(inputs, str):
        inputs = [inputs]
    if isinstance(reasons, str):
        reasons = [reasons]
    return [str(x) for x in inputs], [str(x) for x in reasons]


def validate_exact_batch(
    test_inputs: List[str],
    reasons: List[str],
    expected_count: int,
) -> str | None:
    """Return an error string if extracted inputs/reasons violate exact-count contract."""
    if len(test_inputs) != expected_count:
        return f"expected exactly {expected_count} test_inputs, got {len(test_inputs)}"
    if len(reasons) != expected_count:
        return f"expected exactly {expected_count} reasons, got {len(reasons)}"
    return None
