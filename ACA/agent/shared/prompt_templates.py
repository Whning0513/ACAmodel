"""Shared prompt templates and prompt-view helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

EXPERIMENT_STATS_RULE = (
    "If you need to summarize, compare, or report experiment metrics, you must "
    "reuse the official ACA statistics pipeline (`ACA/stat/metrics.py` and "
    "`ACA/stat/compare.py`). Do not invent new metric definitions, do not write "
    "ad-hoc statistics scripts, and do not change the metric scope on your own."
)

QWEN_OUTPUT_CONSTRAINT_TEXT = (
    "Return only short executable Python statements for generator.py; comments, "
    "reasoning, explanations, Markdown, and copied solution code are forbidden."
)

SEED_CONTRACT_CLARIFICATION_TEXT = (
    "Use the provided seed to generate exactly one input for this run; do not "
    "loop over multiple seeds or print multiple generated inputs."
)


def should_apply_qwen_output_constraint(mode: str, model_name: Optional[str]) -> bool:
    normalized_mode = (mode or "auto").strip().lower()
    if normalized_mode == "off":
        return False
    if normalized_mode == "on":
        return True
    model_text = str(model_name or "").lower()
    if not model_text:
        return False
    qwen_markers = (
        "qwen",
        "qwen3.5",
        "qwen2.5-coder",
    )
    return any(marker in model_text for marker in qwen_markers)


def build_small_model_minimal_generator_system_prompt(
    *,
    num_seeds: int,
    extra_notes: list[str] | None = None,
    tool_use_notes: list[str] | None = None,
    required_response: str | None = None,
    required_heading: str = "# Required Response",
) -> str:
    notes = [note.strip() for note in (extra_notes or []) if note and note.strip()]
    note_block = ""
    if notes:
        note_lines = "\n".join(f"- {note}" for note in notes)
        note_block = f"\n# Additional Information\n{note_lines}\n"
    tool_notes = [note.strip() for note in (tool_use_notes or []) if note and note.strip()]
    tool_block = ""
    if tool_notes:
        tool_lines = "\n".join(f"- {note}" for note in tool_notes)
        tool_block = f"\n# Tool Use\n{tool_lines}\n"
    coverage_rule = ""
    if notes:
        coverage_rule = "- Coverage is a hint, not the final objective.\n"

    prompt = (
        "# Role\n"
        "You are a test-case generation assistant for competitive programming test generation.\n\n"
        "# Objective\n"
        "Output Python code only.\n"
        "Do not explain, analyze, use Markdown, or write comments.\n"
        "The file is executed once as python generator.py <seed>.\n"
        "The program receives exactly one seed from sys.argv[1].\n"
        "It must print exactly one complete stdin input.\n"
        "Do not loop over multiple seeds.\n"
        "Do not print multiple test inputs.\n\n"
        "# Inputs\n"
        "You will be given:\n"
        "1. A problem description\n"
        "2. A sample input format, if available\n"
        "3. The student's code\n"
        f"{note_block}"
        f"{tool_block}\n"
        "# Generator Contract\n"
        "- Output Python code only.\n"
        "- The code will be saved as generator.py and executed as python generator.py <seed>\n"
        "- The program must accept the seed argument and print exactly one stdin string\n"
        "\n# Strategy\n"
        "Prefer simple boundary or special cases: zero, one, min/max values, equal values, "
        "duplicates, sorted/reversed arrays, empty/min-size cases, and special strings.\n"
        "\n# Rules\n"
        "- Every generated input must satisfy the official input format, constraints, and numeric ranges.\n"
        "- Boundary cases are encouraged, but out-of-range or malformed inputs are invalid.\n"
        "- Do not rely on external files, network access, subprocesses, or non-standard packages.\n"
        "- If a fixed counterexample is best, you may ignore the seed, but the program must still accept the seed argument.\n"
        f"{coverage_rule}"
    )
    if required_response:
        prompt += f"\n{required_heading}\n{required_response}"
    return prompt


def apply_qwen_output_constraint(
    prompt: str,
    *,
    mode: str,
    model_name: Optional[str],
    constraint_text: str = QWEN_OUTPUT_CONSTRAINT_TEXT,
    seed_contract_clarification_text: str = SEED_CONTRACT_CLARIFICATION_TEXT,
) -> tuple[str, bool]:
    if not should_apply_qwen_output_constraint(mode, model_name):
        return prompt, False
    suffix_parts = [constraint_text.strip(), seed_contract_clarification_text.strip()]
    suffix = "\n".join(part for part in suffix_parts if part)
    prompt_text = prompt.rstrip()
    if prompt_text.endswith(suffix):
        return prompt_text, True
    return f"{prompt_text}\n{suffix}", True


@dataclass(frozen=True)
class PromptView:
    code_text: str
    target_lines: list[int]
    original_to_prompt_line: dict[int, int]
    prompt_view_version: str | None = None


def resolve_prompt_view(rec) -> PromptView:
    sanitized_code = getattr(rec, "sanitized_student_code", None)
    sanitized_targets = getattr(rec, "effective_uncovered_sanitized_lines", None)
    raw_map = getattr(rec, "original_line_to_sanitized_line", {}) or {}
    original_to_prompt_line = {
        int(k): int(v)
        for k, v in raw_map.items()
    }
    if sanitized_code and sanitized_targets is not None:
        return PromptView(
            code_text=sanitized_code,
            target_lines=list(sanitized_targets),
            original_to_prompt_line=original_to_prompt_line,
            prompt_view_version=getattr(rec, "prompt_view_version", None),
        )
    raw_targets = list(getattr(rec, "uncovered_effective_lines", []))
    return PromptView(
        code_text=getattr(rec, "code", ""),
        target_lines=raw_targets,
        original_to_prompt_line={int(ln): int(ln) for ln in raw_targets},
        prompt_view_version=getattr(rec, "prompt_view_version", None),
    )


def map_covered_lines_to_prompt(prompt_view: PromptView, covered_lines: list[int]) -> list[int]:
    if not covered_lines:
        return []
    mapped = {
        prompt_view.original_to_prompt_line.get(int(line), int(line))
        for line in covered_lines
    }
    return sorted(mapped)


def build_shared_base_system_prompt(
    *,
    test_input_count: int,
    extra_notes: list[str] | None = None,
    tool_use_notes: list[str] | None = None,
    required_response: str,
    required_heading: str = "# Required Response",
) -> str:
    notes = [note.strip() for note in (extra_notes or []) if note and note.strip()]
    note_block = ""
    if notes:
        note_lines = "\n".join(f"- {note}" for note in notes)
        note_block = f"\n# Additional Information\n{note_lines}\n"
    tool_notes = [note.strip() for note in (tool_use_notes or []) if note and note.strip()]
    tool_block = ""
    if tool_notes:
        tool_lines = "\n".join(f"- {note}" for note in tool_notes)
        tool_block = f"\n# Tool Use\n{tool_lines}\n"
    coverage_rule = ""
    if notes:
        coverage_rule = "- Coverage is a hint, not the final objective.\n"

    return (
        "# Role\n"
        "You are a test-case generation assistant. "
        "You are a test-case generation assistant for competitive programming submissions.\n\n"
        "# Objective\n"
        "Generate valid stdin test inputs that may expose bugs in a student's code.\n\n"
        "# Inputs\n"
        "You will be given:\n"
        "1. A problem description\n"
        "2. A sample input format, if available\n"
        "3. The student's code\n"
        f"{note_block}"
        f"{tool_block}\n"
        "# Output Contract\n"
        f"- Generate exactly {test_input_count} complete stdin strings\n"
        "- Each input must be one complete stdin string for a single execution\n"
        "- Do not provide expected outputs\n"
        f"- Provide exactly {test_input_count} brief reasons, one for each input\n\n"
        "# Rules\n"
        "- Every input must satisfy the official input format, constraints, and numeric ranges.\n"
        "- Boundary cases are encouraged, but out-of-range or malformed inputs are invalid.\n"
        "- The inputs will be checked by a validator, then executed against the reference solution and the student's code.\n"
        "- The goal is to find valid countercases, not merely unusual or invalid inputs.\n"
        f"- {EXPERIMENT_STATS_RULE}\n"
        f"{coverage_rule}\n"
        f"{required_heading}\n"
        f"{required_response}"
    )


def build_shared_generator_system_prompt(
    *,
    num_seeds: int,
    extra_notes: list[str] | None = None,
    tool_use_notes: list[str] | None = None,
    required_response: str | None = None,
    required_heading: str = "# Required Response",
) -> str:
    notes = [note.strip() for note in (extra_notes or []) if note and note.strip()]
    note_block = ""
    if notes:
        note_lines = "\n".join(f"- {note}" for note in notes)
        note_block = f"\n# Additional Information\n{note_lines}\n"
    tool_notes = [note.strip() for note in (tool_use_notes or []) if note and note.strip()]
    tool_block = ""
    if tool_notes:
        tool_lines = "\n".join(f"- {note}" for note in tool_notes)
        tool_block = f"\n# Tool Use\n{tool_lines}\n"
    coverage_rule = ""
    if notes:
        coverage_rule = "- Coverage is a hint, not the final objective.\n"

    prompt = (
        "# Role\n"
        "You are a test-case generation assistant and generator-code assistant for competitive programming test generation.\n\n"
        "# Objective\n"
        "Write Python code that prints valid stdin test inputs which may expose bugs in a student's code.\n\n"
        "# Critical Rules\n"
        "1. Write generator code immediately. Do not explain, analyze, or discuss the bug.\n"
        "2. The program handles exactly one seed. Never iterate over multiple seeds.\n"
        "3. Prefer short code. A 20-line generator is better than a 100-line generator.\n\n"
        "# Inputs\n"
        "You will be given:\n"
        "1. A problem description\n"
        "2. A sample input format, if available\n"
        "3. The student's code\n"
        f"{note_block}"
        f"{tool_block}\n"
        "# Generator Contract\n"
        "- Output Python code only.\n"
        "- The code will be saved as `generator.py` and executed as `python generator.py <seed>`\n"
        "- The program must accept the seed argument\n"
        "- For each seed, the program must print exactly one complete stdin string to stdout using standard `print()` output\n"
        f"- The evaluator will run the program on exactly {num_seeds} seeds\n"
        "- Do not print expected outputs\n"
        "\n# Rules\n"
        "- Every generated input must satisfy the official input format, constraints, and numeric ranges.\n"
        "- Boundary cases are encouraged, but out-of-range or malformed inputs are invalid.\n"
        "- Do not rely on external files, network access, subprocesses, or non-standard packages.\n"
        "- If a fixed counterexample is best, you may ignore the seed, but the program must still accept the seed argument.\n"
        "- The goal is to generate a useful input family, not merely random valid inputs.\n"
        f"- {EXPERIMENT_STATS_RULE}\n"
        f"{coverage_rule}"
    )
    if required_response:
        prompt += f"\n{required_heading}\n{required_response}"
    return prompt
