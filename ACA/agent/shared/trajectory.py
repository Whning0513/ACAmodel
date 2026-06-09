"""Lightweight JSONL trajectory writer for per-submission execution traces."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


SCHEMA_VERSION = "aca_traj_v1"
VALID_STATUSES = {"AC", "WA", "RE", "TIMEOUT", "TRACE_TIMEOUT", "TLE", "MLE", "OOM"}
BREAKTHROUGH_STATUSES = {"WA", "RE", "TLE", "MLE", "OOM"}


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_input_text(text: Any) -> str:
    """Normalize line endings while preserving the original logical input."""
    if text is None:
        return ""
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def normalize_input_tokens(text: Any) -> str:
    """Normalize input by token sequence for duplicate detection/statistics."""
    normalized = normalize_input_text(text)
    if not normalized:
        return ""
    return " ".join(normalized.split())


def stable_hash(text: Any) -> str:
    normalized = normalize_input_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def stable_input_hash(text: Any) -> str:
    normalized = normalize_input_tokens(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def safe_preview(text: Any, limit: int = 500) -> str:
    normalized = normalize_input_text(text)
    preview = normalized.replace("\n", "\\n")
    if len(preview) <= limit:
        return preview
    return preview[: max(0, limit - 3)] + "..."


def response_payload_text(msg: Any) -> str:
    """Serialize the observable LLM response for hashing/debug previews."""
    payload = {
        "content": getattr(msg, "content", "") or "",
        "tool_calls": getattr(msg, "tool_calls", []) or [],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _coerce_case_result(case_result: Any) -> dict[str, Any]:
    if is_dataclass(case_result):
        return asdict(case_result)
    return dict(case_result)


def _safe_field(obj: Any, key: str, default: Any = None) -> Any:
    if is_dataclass(obj) or hasattr(obj, key):
        return getattr(obj, key, default)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def compute_submission_end_fields(
    trajectory: Iterable[Any],
    initial_target_lines: list[int],
    final_uncovered_lines: list[int],
) -> dict[str, Any]:
    """Derive summary fields for submission_end from the trajectory only."""
    total_inputs = 0
    total_valid_inputs = 0
    total_invalid_inputs = 0
    countercases_seen: set[str] = set()
    first_cc_iteration: Optional[int] = None
    first_full_coverage_iteration: Optional[int] = None
    touched = False
    remaining = set(initial_target_lines)

    for it in trajectory:
        if is_dataclass(it):
            iteration = it.iteration
            per_case_results = it.per_case_results
            breakthroughs = it.breakthroughs
            newly_covered = it.newly_covered
        else:
            iteration = int(it.get("iteration", 0))
            per_case_results = it.get("per_case_results", [])
            breakthroughs = it.get("breakthroughs", [])
            newly_covered = it.get("newly_covered", [])

        total_inputs += len(per_case_results)
        for cr in per_case_results:
            item = _coerce_case_result(cr)
            status = item.get("status")
            if status in VALID_STATUSES:
                total_valid_inputs += 1
            else:
                total_invalid_inputs += 1
            covered = set(item.get("covered_lines", []))
            if covered & set(initial_target_lines):
                touched = True

        for inp in breakthroughs:
            countercases_seen.add(normalize_input_tokens(inp))
        if breakthroughs and first_cc_iteration is None:
            first_cc_iteration = iteration

        remaining -= set(newly_covered)
        if not remaining and first_full_coverage_iteration is None:
            first_full_coverage_iteration = iteration

    all_covered = not final_uncovered_lines
    tcc = bool(countercases_seen)
    return {
        "total_inputs": total_inputs,
        "total_valid_inputs": total_valid_inputs,
        "total_invalid_inputs": total_invalid_inputs,
        "total_countercases": len(countercases_seen),
        "first_cc_iteration": first_cc_iteration,
        "first_full_coverage_iteration": first_full_coverage_iteration,
        "tcc": tcc,
        "tcc_strict": tcc and touched,
        "tcc_loose": tcc and not touched,
        "all_covered": all_covered,
    }


class TrajectoryWriter:
    """Per-submission JSONL writer with exact-duplicate input bookkeeping."""

    def __init__(
        self,
        trajectory_root: Optional[str | Path],
        strategy: str,
        submission_id: str,
        keep_full_text: bool = False,
    ):
        self.enabled = trajectory_root is not None
        self.strategy = strategy
        self.submission_id = submission_id
        self.keep_full_text = keep_full_text
        self._seen_inputs: dict[str, str] = {}
        self.duplicate_exact_inputs = 0
        self.path: Optional[Path] = None
        self._fh = None

        if self.enabled:
            self.path = Path(trajectory_root) / strategy / f"{submission_id}.jsonl"
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.path.open("w", encoding="utf-8")

    def make_input_entries(
        self,
        iteration: int,
        test_inputs: list[str],
        reasons: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        reasons = reasons or []
        for idx, raw in enumerate(test_inputs):
            input_id = f"it{iteration}_in{idx}"
            normalized_text = normalize_input_text(raw)
            normalized_tokens = normalize_input_tokens(raw)
            duplicate_of = self._seen_inputs.get(normalized_tokens)
            duplicate_exact = duplicate_of is not None
            if duplicate_exact:
                self.duplicate_exact_inputs += 1
            else:
                self._seen_inputs[normalized_tokens] = input_id
            entries.append({
                "input_id": input_id,
                "input_hash": stable_input_hash(normalized_text),
                "input_preview": safe_preview(normalized_text),
                "input_text": normalized_text if self.keep_full_text else None,
                "reason": reasons[idx] if idx < len(reasons) else None,
                "duplicate_exact": duplicate_exact,
                "duplicate_of": duplicate_of,
            })
        return entries

    def append_event(self, event: dict[str, Any]) -> None:
        if not self.enabled or self._fh is None:
            return
        payload = dict(event)
        payload.setdefault("schema_version", SCHEMA_VERSION)
        payload.setdefault("timestamp", utc_timestamp())
        self._fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None


def write_debug_trace(
    trace_dir: str,
    submission_id: str,
    *,
    messages: list[dict],
    response: Any = None,
    parsed_inputs: Optional[list[str]] = None,
    dual_results: Optional[list[Any]] = None,
    strategy: str = "",
    terminated_reason: str = "",
    final_uncovered_lines: Optional[list[int]] = None,
) -> None:
    """Write a full debug trace (JSON + Markdown) for one submission.

    This is the shared version used by L/V/G-family runners.
    R-family has its own (graph-specific) variant in r_family/runner.py.

    Writes to ``{trace_dir}/{submission_id}_trace.json`` and
    ``{trace_dir}/{submission_id}_trace.md``.
    """
    import os
    from datetime import datetime

    os.makedirs(trace_dir, exist_ok=True)

    # ── Build structured trace ──────────────────────────────────────
    trace_entries: list[dict] = []
    for i, msg in enumerate(messages):
        entry: dict = {"index": i, "role": msg.get("role", "?")}
        content = msg.get("content", "")
        if content:
            entry["content"] = content
        tc = msg.get("tool_calls")
        if tc:
            entry["tool_calls"] = [
                {"id": t.get("id", ""), "name": t.get("name", ""), "args": t.get("args", {})}
                for t in tc
            ]
        tool_call_id = msg.get("tool_call_id")
        if tool_call_id:
            entry["tool_call_id"] = tool_call_id
        trace_entries.append(entry)

    # Add parsed + execution info at the end
    extras: dict = {
        "strategy": strategy,
        "submission_id": submission_id,
        "terminated_reason": terminated_reason,
        "final_uncovered_lines": final_uncovered_lines or [],
    }
    if parsed_inputs:
        extras["parsed_inputs"] = parsed_inputs
    if dual_results is not None:
        extras["dual_results"] = []
        for dr in dual_results:
            extras["dual_results"].append({
                "status": _safe_field(dr, "status", ""),
                "breakthrough": _safe_field(dr, "breakthrough", False),
                "covered_lines": _safe_field(dr, "covered_lines", []),
                "stdout": _safe_field(dr, "stdout", ""),
                "stderr": _safe_field(dr, "stderr", ""),
                "expected_output": _safe_field(dr, "expected_output", ""),
                "reference_ok": _safe_field(dr, "reference_ok", True),
                "error": _safe_field(dr, "error", ""),
                "ref_stdout": _safe_field(dr, "ref_stdout", ""),
                "ref_stderr": _safe_field(dr, "ref_stderr", ""),
                "ref_returncode": _safe_field(dr, "ref_returncode", None),
            })

    trace = {
        "submission_id": submission_id,
        "strategy": strategy,
        "terminated_reason": terminated_reason,
        "final_uncovered_lines": final_uncovered_lines or [],
        "conversation": trace_entries,
        "extras": extras,
    }

    json_path = os.path.join(trace_dir, f"{submission_id}_trace.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(trace, f, indent=2, ensure_ascii=False)

    # ── Human-readable markdown ─────────────────────────────────────
    md_path = os.path.join(trace_dir, f"{submission_id}_trace.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Trace: {submission_id}\n\n")
        f.write(f"- **Strategy**: {strategy}\n")
        f.write(f"- **Terminated**: {terminated_reason}\n")
        if final_uncovered_lines:
            f.write(f"- **Final uncovered lines**: {final_uncovered_lines}\n")
        if parsed_inputs:
            f.write(f"- **Parsed inputs**: {len(parsed_inputs)}\n")
        f.write(f"- **Timestamp**: {datetime.now().isoformat()}\n\n")
        f.write("---\n\n")

        for entry in trace_entries:
            role = entry["role"]
            idx = entry["index"]
            content = entry.get("content", "")

            f.write(f"## Step {idx}: {role.upper()}\n\n")

            # Reasoning (from additional_kwargs on assistant messages)
            reasoning = entry.get("reasoning", "")
            if reasoning:
                f.write("<details><summary>Reasoning</summary>\n\n")
                f.write(f"{reasoning}\n\n")
                f.write("</details>\n\n")

            if entry.get("tool_calls"):
                for tc in entry["tool_calls"]:
                    f.write(f"**Tool call**: `{tc['name']}`\n\n")
                    f.write(f"```json\n{json.dumps(tc['args'], indent=2, ensure_ascii=False)}\n```\n\n")

            if content:
                f.write(f"{content}\n\n")

        # Per-input results
        if dual_results:
            f.write("---\n\n## Execution Results\n\n")
            f.write("| # | Status | Breakthrough | Lines Covered |\n")
            f.write("|---|--------|--------------|---------------|\n")
            for dr in dual_results:
                status = _safe_field(dr, "status", "?")
                bt = _safe_field(dr, "breakthrough", False)
                cov = _safe_field(dr, "covered_lines", [])
                f.write(f"|   | {status} | {bt} | {cov} |\n")
            f.write("\n")

        if parsed_inputs:
            f.write("---\n\n## Parsed Inputs\n\n")
            for inp in parsed_inputs:
                f.write(f"```\n{inp}\n```\n\n")
