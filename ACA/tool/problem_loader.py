"""Data loader: step6_final.ndjson + step4_references.json.

Usage:
    from ACA.tool.problem_loader import load_dataset

    dataset = load_dataset("outputs/step6_final.ndjson", "outputs/step4_references.json")
    # dataset.submissions — list of SubmissionRecord (passed-filter only)
    # dataset.test_cases[pid] — list of TestCase (input, expected_output_norm)
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class TestCase:
    """A single test case with pre-normalized expected output."""
    case_idx: int
    input_text: str
    expected_output: str           # original
    expected_output_norm: str      # pre-normalized by step4


@dataclass
class SubmissionRecord:
    """A single submission from step6_final.ndjson, ready for agent consumption."""
    submission_id: str
    pid: str
    source: str                    # "origin" | "constructed"
    code: str
    ref_code: str
    ac_indices: List[int]
    gt_indices: List[int]
    uncovered_effective_lines: List[int]
    candidate_lines: List[int]
    uncovered_line_tags: Dict[str, str]
    ac_count: int
    gt_count: int
    total_cases: int
    ac_ratio: float
    max_depth: int
    code_size_lines: int
    code_size_chars: int
    original_verdict: Optional[str] = None
    source_raw: Optional[str] = None
    source_kind: Optional[str] = None        # "origin" | "total_origin" | "constructed"
    source_family: Optional[str] = None      # "origin_family" | "constructed"
    fuse_group: Optional[str] = None  # submissions grouped by similar uncovered-line patterns
    filter_tag: Optional[str] = None  # non-None = submission failed step6 quality filter
    sample_input_anchor: str = ""
    sample_input_anchor_source: Optional[str] = None
    prompt_view_version: Optional[str] = None
    sanitized_student_code: Optional[str] = None
    original_line_to_sanitized_line: Dict[str, int] = field(default_factory=dict)
    sanitized_line_to_original_line: Dict[str, Optional[int]] = field(default_factory=dict)
    removed_or_folded_original_lines: List[int] = field(default_factory=list)
    effective_uncovered_original_lines: Optional[List[int]] = None
    effective_uncovered_sanitized_lines: Optional[List[int]] = None
    # Constructed-only fields
    parent_submission_id: Optional[str] = None
    buggy_lines: Optional[List[int]] = None
    dropped_ac_indices: Optional[List[int]] = None


@dataclass
class Dataset:
    """Loaded dataset: submissions + test cases ready for agent consumption."""
    submissions: List[SubmissionRecord]
    test_cases: Dict[str, List[TestCase]]
    references: dict                # raw step4_references.json
    descriptions: Dict[str, str] = field(default_factory=dict)  # pid → description_html


def load_descriptions(descriptions_path: Optional[str] = None) -> Dict[str, str]:
    """Load pid→description_html mapping from a JSON file.

    If no path is given, tries ACA/tool/problem_descriptions.json.
    Returns {} if no file found.
    """
    if descriptions_path is None:
        descriptions_path = str(Path(__file__).parent / "problem_descriptions.json")
    try:
        with open(descriptions_path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _strip_simple_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def extract_sample_input_anchor(description_text: str) -> tuple[str, Optional[str]]:
    """Extract the first sample input block from problem text if present.

    We intentionally only extract from the examples section. If the statement
    has no example/sample block, return an empty anchor rather than fabricating
    one from the formal input specification.
    """
    text = _strip_simple_html(description_text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    lowered = [line.strip().lower() for line in lines]

    example_start = None
    for i, line in enumerate(lowered):
        if line in {"example", "examples", "sample", "samples"}:
            example_start = i
            break
    if example_start is None:
        return "", None

    input_start = None
    for i in range(example_start + 1, len(lines)):
        if lowered[i] in {"input", "sample input"}:
            input_start = i + 1
            break
    if input_start is None:
        return "", None

    block: List[str] = []
    started = False
    stop_markers = {"output", "sample output", "note", "notes"}
    for i in range(input_start, len(lines)):
        marker = lowered[i]
        if marker in stop_markers:
            break
        current = lines[i]
        if not started and not current.strip():
            continue
        started = True
        block.append(current)

    while block and not block[-1].strip():
        block.pop()

    if not block:
        return "", None
    return "\n".join(block), "problem_descriptions.examples_first_input"


def load_dataset(
    step6_path: str,
    references_path: str,
    filter_passed_only: bool = True,
    limit: Optional[int] = None,
    pids: Optional[List[str]] = None,
    descriptions: Optional[Dict[str, str]] = None,
) -> Dataset:
    """Load submissions and test cases.

    Args:
        step6_path: Path to step6_final.ndjson.
        references_path: Path to step4_references.json.
        filter_passed_only: If True, only include submissions with filter==None.
        limit: Max submissions to load.
        pids: Only load submissions for these problem IDs.
    """
    # Load references
    with open(references_path) as f:
        references = json.load(f)

    test_cases: Dict[str, List[TestCase]] = {}
    for pid, ref_info in references.items():
        cases = []
        for i, c in enumerate(ref_info.get("cases", [])):
            cases.append(TestCase(
                case_idx=i,
                input_text=c["input"],
                expected_output=c.get("output", ""),
                expected_output_norm=c.get("_norm_out", c.get("output", "")),
            ))
        test_cases[pid] = cases

    # Load submissions
    submissions = []
    with open(step6_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)

            if filter_passed_only and r.get("filter"):
                continue
            if pids and r["pid"] not in pids:
                continue

            tags = r.get("uncovered_line_tags", {})
            # Keep keys as str — they're already strings from JSON
            # (step6 stores them as {"5": "logic", "6": "io_read"})

            # Normalize: step6 uses "matrixstudio" for original submissions
            source_raw = r.get("source", "matrixstudio")
            # Normalize: step6 labels original submissions by their platform name
            source = "origin" if source_raw == "matrixstudio" else source_raw
            source_kind = r.get("source_kind")
            source_family = r.get("source_family")
            if source_kind is None or source_family is None:
                if source_raw == "constructed":
                    source_kind = "constructed"
                    source_family = "constructed"
                elif (
                    abs(float(r.get("ac_ratio", 0.0)) - 1.0) < 1e-12
                    and r.get("original_verdict") is not None
                    and r.get("original_verdict") not in ("OK", "COMPILATION_ERROR", "")
                ):
                    source_kind = "total_origin"
                    source_family = "origin_family"
                else:
                    source_kind = "origin"
                    source_family = "origin_family"

            sample_input_anchor = r.get("sample_input_anchor") or ""
            sample_input_anchor_source = None
            if sample_input_anchor:
                sample_input_anchor_source = "dataset.sample_input_anchor"
            else:
                desc = descriptions.get(r["pid"], "") if descriptions else ""
                if desc:
                    sample_input_anchor, sample_input_anchor_source = extract_sample_input_anchor(desc)

            submissions.append(SubmissionRecord(
                submission_id=r["submission_id"],
                pid=r["pid"],
                source=source,
                code=r["code"],
                ref_code=r["ref_code"],
                ac_indices=r.get("ac_indices", []),
                gt_indices=r.get("gt_indices", []),
                uncovered_effective_lines=r.get("uncovered_effective_lines", []),
                candidate_lines=r.get("candidate_lines", []),
                uncovered_line_tags=tags,
                ac_count=r.get("ac_count", 0),
                gt_count=r.get("gt_count", 0),
                total_cases=r.get("total_cases", 0),
                ac_ratio=r.get("ac_ratio", 0),
                max_depth=r.get("max_depth", 0),
                code_size_lines=r.get("code_size_lines", 0),
                code_size_chars=r.get("code_size_chars", 0),
                original_verdict=r.get("original_verdict"),
                source_raw=r.get("source_raw", source_raw),
                source_kind=source_kind,
                source_family=source_family,
                fuse_group=r.get("fuse_group"),
                filter_tag=r.get("filter"),
                sample_input_anchor=sample_input_anchor,
                sample_input_anchor_source=sample_input_anchor_source,
                prompt_view_version=r.get("prompt_view_version"),
                sanitized_student_code=r.get("sanitized_student_code"),
                original_line_to_sanitized_line=r.get("original_line_to_sanitized_line", {}),
                sanitized_line_to_original_line=r.get("sanitized_line_to_original_line", {}),
                removed_or_folded_original_lines=r.get("removed_or_folded_original_lines", []),
                effective_uncovered_original_lines=r.get("effective_uncovered_original_lines"),
                effective_uncovered_sanitized_lines=r.get("effective_uncovered_sanitized_lines"),
                parent_submission_id=r.get("parent_submission_id"),
                buggy_lines=r.get("buggy_lines"),
                dropped_ac_indices=r.get("dropped_ac_indices"),
            ))

            if limit and len(submissions) >= limit:
                break

    if descriptions is None:
        descriptions = {}

    return Dataset(
        submissions=submissions,
        test_cases=test_cases,
        references=references,
        descriptions=descriptions,
    )


def get_test_inputs(pid: str, test_cases: Dict[str, List[TestCase]],
                    indices: List[int]) -> List[str]:
    """Return test input strings for the given case indices."""
    cases = test_cases.get(pid, [])
    return [cases[i].input_text for i in indices if i < len(cases)]


def get_expected_outputs_norm(pid: str, test_cases: Dict[str, List[TestCase]],
                              indices: List[int]) -> List[str]:
    """Return pre-normalized expected outputs for the given case indices."""
    cases = test_cases.get(pid, [])
    return [cases[i].expected_output_norm for i in indices if i < len(cases)]
