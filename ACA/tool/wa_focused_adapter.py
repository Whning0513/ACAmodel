"""waFocusedData submit/problem adapter for ACA runners.

Builds a runner-ready single-table ndjson plus companion assets from the
waFocusedData dual-table dataset:

- submit table: submission-level rows
- problem table: problem-level assets (statement/ref/validator/blind_cases)

The generated ndjson is intentionally shaped to be consumable by
ACA.tool.problem_loader.load_dataset without changing agent logic.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional

from ACA.tool.problem_loader import extract_sample_input_anchor


ADAPTER_VERSION = "wa_focused_adapter_20260530"
DEFAULT_HARD_EXCLUDE = {
    "atcoder__p03069 Tenka1 Programmer Beginner Contest 2019 - Stones",
}


@dataclass
class AdapterPaths:
    runner_ready_ndjson: str
    references_json: str
    descriptions_json: str
    validator_root: str
    validator_registry: str
    summary_json: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sanitize_filename(pid: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", pid.strip())
    return safe[:180] or "validator"


def _normalize_output(text: str) -> str:
    return (text or "").rstrip() + "\n"


def _indent_depth(line: str) -> int:
    if not line or not line.strip():
        return 0
    expanded = line.replace("\t", "    ")
    leading = len(expanded) - len(expanded.lstrip(" "))
    return max(0, leading // 4)


def _estimate_max_uncovered_depth(code_text: str, uncovered_lines: list[int]) -> int:
    """Approximate max depth by indentation on uncovered lines.

    The waFocused submit table currently does not carry `max_depth`, so we
    recover a lightweight proxy from the student's Python indentation.
    """
    if not code_text or not uncovered_lines:
        return 0
    lines = code_text.splitlines()
    depths = []
    for line_no in uncovered_lines:
        if 1 <= int(line_no) <= len(lines):
            depths.append(_indent_depth(lines[int(line_no) - 1]))
    return max(depths) if depths else 0


def _sample_input_from_problem(problem: dict) -> tuple[str, Optional[str]]:
    statement = problem.get("statement") or ""
    sample_input_anchor, source = extract_sample_input_anchor(statement)
    if sample_input_anchor:
        return sample_input_anchor, f"problem.statement:{source}"

    sample_tests = problem.get("sample_tests") or ""
    m = re.search(r"Input:\s*```(?:\w+)?\n(.*?)```", sample_tests, flags=re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).strip(), "problem.sample_tests.first_input"

    example_valid = (problem.get("example_valid_input") or "").strip()
    if example_valid:
        return example_valid, "problem.example_valid_input"
    return "", None


def _build_description(problem: dict) -> str:
    parts = []
    title = (problem.get("title") or "").strip()
    if title:
        parts.append(title)
    statement = (problem.get("statement") or "").strip()
    if statement:
        parts.append(statement)
    input_spec = (problem.get("input_spec") or "").strip()
    if input_spec:
        parts.append("Input\n" + input_spec)
    output_spec = (problem.get("output_spec") or "").strip()
    if output_spec:
        parts.append("Output\n" + output_spec)
    sample_tests = (problem.get("sample_tests") or "").strip()
    if sample_tests:
        parts.append(sample_tests)
    return "\n\n".join(part for part in parts if part).strip()


def build_problem_map(problem_ndjson: str | Path) -> dict[str, dict]:
    problems: dict[str, dict] = {}
    with open(problem_ndjson, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            problems[row["global_pid"]] = row
    return problems


def resolve_wa_focused_submit_problem_paths(base_dir: str | Path) -> tuple[Path, Path]:
    base = Path(base_dir)
    candidates = [
        (
            base / "waFocusedData_submit_0601_7659.ndjson",
            base / "waFocusedData_problem_0601_7659.ndjson",
        ),
        (
            base / "waFocusedData_submit_0601_final.ndjson",
            base / "waFocusedData_problem_0601_final.ndjson",
        ),
        (
            base / "waFocusedData_submit_0526_final.ndjson",
            base / "waFocusedData_problem_0526_final.ndjson",
        ),
    ]
    for submit_path, problem_path in candidates:
        if submit_path.exists() and problem_path.exists():
            return submit_path, problem_path

    submit_matches = sorted(base.glob("waFocusedData_submit_*_final.ndjson"))
    problem_matches = sorted(base.glob("waFocusedData_problem_*_final.ndjson"))
    if len(submit_matches) == 1 and len(problem_matches) == 1:
        return submit_matches[0], problem_matches[0]
    raise FileNotFoundError(
        f"Could not resolve waFocused submit/problem ndjson under {base}. "
        "Expected 0526/0601_7659/0601 file names or a single matching submit/problem pair."
    )


def load_wa_focused_submit_problem(base_dir: str | Path) -> tuple[list[dict], dict[str, dict]]:
    base = Path(base_dir)
    submit_path, problem_path = resolve_wa_focused_submit_problem_paths(base)
    submits = []
    with submit_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                submits.append(json.loads(line))
    prompt_view_matches = sorted(base.glob("waFocusedData_submit_*_harness_pruned_v1.ndjson"))
    if len(prompt_view_matches) == 1:
        prompt_view_by_id: dict[str, dict] = {}
        with prompt_view_matches[0].open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                cid = row.get("candidate_id") or row.get("submission_id")
                if cid:
                    prompt_view_by_id[cid] = row
        prompt_only_keys = {
            "prompt_view_version",
            "sanitized_student_code",
            "original_line_to_sanitized_line",
            "sanitized_line_to_original_line",
            "removed_or_folded_original_lines",
            "effective_uncovered_original_lines",
            "effective_uncovered_sanitized_lines",
        }
        for submit in submits:
            cid = submit.get("candidate_id") or submit.get("submission_id")
            if cid in prompt_view_by_id:
                for key in prompt_only_keys:
                    if key in prompt_view_by_id[cid]:
                        submit[key] = prompt_view_by_id[cid][key]
    return submits, build_problem_map(problem_path)


def join_submit_problem(submit_record: dict, problem_map: dict[str, dict]) -> dict:
    pid = submit_record["global_pid"]
    problem = problem_map.get(pid)
    joined_problem_ok = problem is not None
    sample_input_anchor = ""
    sample_input_anchor_source = None
    description_html = ""
    ref_code = ""
    validator_code = ""
    ref_status = None
    validator_status = None
    blind_cases = []
    num_valid_blind_cases = 0
    title = submit_record.get("title") or ""
    input_spec = ""
    output_spec = ""
    sample_tests = ""

    if problem:
        sample_input_anchor, sample_input_anchor_source = _sample_input_from_problem(problem)
        description_html = _build_description(problem)
        ref_code = problem.get("ref_code") or ""
        validator_code = problem.get("validator_code") or ""
        ref_status = problem.get("ref_status")
        validator_status = problem.get("validator_status")
        blind_cases = problem.get("blind_cases") or []
        num_valid_blind_cases = int(problem.get("num_valid_blind_cases") or len(blind_cases))
        title = problem.get("title") or title
        input_spec = problem.get("input_spec") or ""
        output_spec = problem.get("output_spec") or ""
        sample_tests = problem.get("sample_tests") or ""

    effective_uncovered = list(submit_record.get("effective_uncovered_lines") or [])
    clean_ready = (
        joined_problem_ok
        and submit_record.get("canonical_split") == "main"
        and ref_status == "ref_ready"
        and validator_status == "validator_ready"
        and bool(ref_code.strip())
        and bool(validator_code.strip())
    )

    clean_exclude_reason = None
    if not joined_problem_ok:
        clean_exclude_reason = "missing_problem_row"
    elif submit_record.get("canonical_split") != "main":
        clean_exclude_reason = f"canonical_split={submit_record.get('canonical_split')}"
    elif ref_status != "ref_ready":
        clean_exclude_reason = f"ref_status={ref_status}"
    elif validator_status != "validator_ready":
        clean_exclude_reason = f"validator_status={validator_status}"
    elif not ref_code.strip():
        clean_exclude_reason = "missing_ref_code"
    elif not validator_code.strip():
        clean_exclude_reason = "missing_validator_code"

    passed_count = int(submit_record.get("passed_case_count") or 0)
    failed_count = int(submit_record.get("failed_case_count") or 0)
    total_cases = max(
        num_valid_blind_cases,
        passed_count + failed_count,
        int(submit_record.get("new_blind_case_count") or 0),
    )
    ac_ratio = 0.0
    if total_cases > 0:
        ac_ratio = passed_count / total_cases

    code_text = submit_record.get("code") or ""
    raw_max_depth = submit_record.get("max_depth")
    max_depth = (
        int(raw_max_depth)
        if raw_max_depth not in (None, "")
        else _estimate_max_uncovered_depth(code_text, effective_uncovered)
    )

    return {
        # Canonical identifiers
        "candidate_id": submit_record.get("candidate_id"),
        "submission_id": submit_record.get("submission_id") or submit_record.get("candidate_id"),
        "global_pid": pid,
        "pid": pid,
        "title": title,
        "platform": submit_record.get("source"),
        "source": submit_record.get("source"),
        "source_raw": submit_record.get("source"),
        "source_kind": "origin",
        "source_family": "origin_family",
        # Submission-level
        "code": code_text,
        "student_code": code_text,
        "canonical_split": submit_record.get("canonical_split"),
        "original_split": submit_record.get("original_split"),
        "failed_case_count": failed_count,
        "failed_case_ratio": submit_record.get("failed_case_ratio"),
        "passed_case_count": passed_count,
        "passed_case_ids": list(submit_record.get("passed_case_ids") or []),
        "failed_case_ids": list(submit_record.get("failed_case_ids") or []),
        "effective_uncovered_lines": effective_uncovered,
        "uncovered_effective_lines": effective_uncovered,
        "effective_uncovered_count": int(submit_record.get("effective_uncovered_count") or len(effective_uncovered)),
        "uncovered_line_tags": {},
        "candidate_lines": effective_uncovered,
        "ac_indices": [],
        "gt_indices": [],
        "ac_count": passed_count,
        "gt_count": failed_count,
        "total_cases": total_cases,
        "ac_ratio": ac_ratio,
        "max_depth": max_depth,
        "code_size_lines": len(code_text.splitlines()),
        "code_size_chars": len(code_text),
        "original_verdict": submit_record.get("original_verdict"),
        "fuse_group": submit_record.get("fuse_group"),
        "filter": None,
        # Problem-level
        "statement": problem.get("statement") if problem else "",
        "description_html": description_html,
        "input_spec": input_spec,
        "output_spec": output_spec,
        "sample_tests": sample_tests,
        "sample_input_anchor": sample_input_anchor,
        "sample_input_anchor_source": sample_input_anchor_source,
        "prompt_view_version": submit_record.get("prompt_view_version"),
        "sanitized_student_code": submit_record.get("sanitized_student_code"),
        "original_line_to_sanitized_line": submit_record.get("original_line_to_sanitized_line", {}),
        "sanitized_line_to_original_line": submit_record.get("sanitized_line_to_original_line", {}),
        "removed_or_folded_original_lines": submit_record.get("removed_or_folded_original_lines", []),
        "effective_uncovered_original_lines": submit_record.get("effective_uncovered_original_lines", effective_uncovered),
        "effective_uncovered_sanitized_lines": submit_record.get("effective_uncovered_sanitized_lines"),
        "ref_code": ref_code,
        "validator_code": validator_code,
        "ref_status": ref_status,
        "validator_status": validator_status,
        "blind_cases": blind_cases,
        "num_valid_blind_cases": num_valid_blind_cases,
        # Adapter metadata
        "joined_problem_ok": joined_problem_ok,
        "clean_ready": clean_ready,
        "clean_exclude_reason": clean_exclude_reason,
        "adapter_source": "waFocusedData_submit_problem_join",
        "adapter_version": ADAPTER_VERSION,
        "problem_ref_hash": _sha256_text(ref_code),
        "problem_validator_hash": _sha256_text(validator_code),
        "raw_submit": submit_record,
        "raw_problem": problem if problem else None,
    }


def iter_clean_main_records(
    submits: Iterable[dict],
    problem_map: dict[str, dict],
    hard_exclude: Optional[set[str]] = None,
) -> Iterator[dict]:
    hard_exclude = hard_exclude or set(DEFAULT_HARD_EXCLUDE)
    for submit in submits:
        joined = join_submit_problem(submit, problem_map)
        pid = joined["pid"]
        if pid in hard_exclude:
            joined["clean_ready"] = False
            joined["clean_exclude_reason"] = "hard_exclude"
            continue
        if joined["clean_ready"]:
            yield joined


def _materialize_descriptions(problem_map: dict[str, dict], out_path: Path) -> dict[str, str]:
    descriptions = {pid: _build_description(problem) for pid, problem in problem_map.items()}
    out_path.write_text(json.dumps(descriptions, ensure_ascii=False, indent=2), encoding="utf-8")
    return descriptions


def _materialize_references(problem_map: dict[str, dict], pids: set[str], out_path: Path) -> dict:
    references = {}
    for pid in sorted(pids):
        problem = problem_map[pid]
        cases = []
        for case in problem.get("blind_cases") or []:
            out = _normalize_output(case.get("output", ""))
            cases.append({
                "input": (case.get("input") or "").rstrip() + "\n",
                "output": out,
                "_norm_out": out,
                "test_id": case.get("test_id"),
                "split": case.get("split"),
                "visibility": case.get("visibility"),
            })
        references[pid] = {
            "title": problem.get("title"),
            "cases": cases,
            "source": "waFocusedData_problem.blind_cases",
            "ref_hash": _sha256_text(problem.get("ref_code") or ""),
        }
    out_path.write_text(json.dumps(references, ensure_ascii=False, indent=2), encoding="utf-8")
    return references


def _materialize_validators(problem_map: dict[str, dict], pids: set[str], validator_root: Path) -> tuple[Path, dict]:
    validator_root.mkdir(parents=True, exist_ok=True)
    validators_dir = validator_root / "validators"
    validators_dir.mkdir(parents=True, exist_ok=True)
    registry = {}
    for pid in sorted(pids):
        problem = problem_map[pid]
        code = problem.get("validator_code") or ""
        filename = f"{_sanitize_filename(pid)}.py"
        rel_path = f"validators/{filename}"
        (validator_root / rel_path).write_text(code, encoding="utf-8")
        registry[pid] = {
            "status": "reviewed",
            "path": rel_path,
            "source": "waFocusedData_problem.validator_code",
            "version": ADAPTER_VERSION,
            "validator_hash": _sha256_text(code),
        }
    registry_path = validator_root / "registry.json"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry_path, registry


def write_adapter_dataset(
    base_dir: str | Path,
    output_dir: str | Path,
    hard_exclude: Optional[set[str]] = None,
) -> AdapterPaths:
    hard_exclude = hard_exclude or set(DEFAULT_HARD_EXCLUDE)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    submits, problem_map = load_wa_focused_submit_problem(base_dir)
    joined_ok_count = 0
    clean_records = []
    raw_main_count = 0
    excluded_by_ref_not_ready = 0
    excluded_by_validator_not_ready = 0
    excluded_by_missing_ref_code = 0
    excluded_by_missing_validator_code = 0
    excluded_by_hard_exclude = 0
    p03069_excluded_count = 0
    joined_missing_count = 0

    for submit in submits:
        if submit.get("canonical_split") == "main":
            raw_main_count += 1
        joined = join_submit_problem(submit, problem_map)
        if joined["joined_problem_ok"]:
            joined_ok_count += 1
        else:
            joined_missing_count += 1
            continue

        pid = joined["pid"]
        if submit.get("canonical_split") != "main":
            continue
        if pid in hard_exclude:
            excluded_by_hard_exclude += 1
            if pid == "atcoder__p03069 Tenka1 Programmer Beginner Contest 2019 - Stones":
                p03069_excluded_count += 1
            continue
        if joined["ref_status"] != "ref_ready":
            excluded_by_ref_not_ready += 1
            continue
        if joined["validator_status"] != "validator_ready":
            excluded_by_validator_not_ready += 1
            continue
        if not (joined["ref_code"] or "").strip():
            excluded_by_missing_ref_code += 1
            continue
        if not (joined["validator_code"] or "").strip():
            excluded_by_missing_validator_code += 1
            continue
        clean_records.append(joined)

    clean_pids = {r["pid"] for r in clean_records}
    runner_ready_ndjson = output_dir / "waFocused_clean_main_runner_ready.ndjson"
    references_json = output_dir / "waFocused_clean_main_references.json"
    descriptions_json = output_dir / "waFocused_clean_main_descriptions.json"
    validator_root = output_dir / "waFocused_validators"
    summary_json = output_dir / "waFocused_clean_main_summary.json"

    with runner_ready_ndjson.open("w", encoding="utf-8") as fh:
        for rec in clean_records:
            out = {k: v for k, v in rec.items() if k not in {"raw_submit", "raw_problem"}}
            fh.write(json.dumps(out, ensure_ascii=False) + "\n")

    _materialize_references(problem_map, clean_pids, references_json)
    _materialize_descriptions(problem_map, descriptions_json)
    registry_path, registry = _materialize_validators(problem_map, clean_pids, validator_root)

    from collections import Counter

    pid_counts = Counter(r["pid"] for r in clean_records)
    summary = {
        "adapter_version": ADAPTER_VERSION,
        "base_dir": str(base_dir),
        "total_submit_records": len(submits),
        "total_problem_records": len(problem_map),
        "joined_ok_count": joined_ok_count,
        "joined_missing_count": joined_missing_count,
        "raw_main_count": raw_main_count,
        "clean_main_count": len(clean_records),
        "clean_main_unique_pids": len(clean_pids),
        "excluded_by_ref_not_ready": excluded_by_ref_not_ready,
        "excluded_by_validator_not_ready": excluded_by_validator_not_ready,
        "excluded_by_missing_ref_code": excluded_by_missing_ref_code,
        "excluded_by_missing_validator_code": excluded_by_missing_validator_code,
        "excluded_by_hard_exclude": excluded_by_hard_exclude,
        "p03069_excluded_count": p03069_excluded_count,
        "cf_1328_F_clean_main_count": pid_counts.get("codeforces__cf_1328_F", 0),
        "cf_1328_F_hard_tail_count": sum(
            1
            for submit in submits
            if submit.get("global_pid") == "codeforces__cf_1328_F"
            and submit.get("canonical_split") == "hard_tail"
        ),
        "runner_ready_ndjson": str(runner_ready_ndjson),
        "references_json": str(references_json),
        "descriptions_json": str(descriptions_json),
        "validator_root": str(validator_root),
        "validator_registry": str(registry_path),
        "materialized_validator_count": len(registry),
    }
    summary_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    return AdapterPaths(
        runner_ready_ndjson=str(runner_ready_ndjson),
        references_json=str(references_json),
        descriptions_json=str(descriptions_json),
        validator_root=str(validator_root),
        validator_registry=str(registry_path),
        summary_json=str(summary_json),
    )
