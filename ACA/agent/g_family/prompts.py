"""Prompt templates for G0 and G1 programmatic generator strategies."""

import re

from ACA.agent.shared.prompt_templates import (
    apply_qwen_output_constraint,
    build_shared_generator_system_prompt,
    build_small_model_minimal_generator_system_prompt,
)


def build_system_prompt(
    strategy: str,
    num_seeds: int = 5,
    *,
    model_name: str | None = None,
    qwen_output_constraint_mode: str = "auto",
    gtor_prompt_profile: str = "legacy",
) -> str:
    extra_notes = []
    if strategy in {"G1", "ITERG"}:
        extra_notes = [
            "Some lines in the student's code are marked with `# uncovered`. These lines were not exercised by the existing passing tests. You may prioritize inputs that execute these lines.",
        ]

    if gtor_prompt_profile == "small_model_minimal":
        prompt = build_small_model_minimal_generator_system_prompt(
            num_seeds=num_seeds,
            extra_notes=extra_notes,
            required_response="Return Python generator code only.",
        )
        return prompt

    prompt = build_shared_generator_system_prompt(
        num_seeds=num_seeds,
        extra_notes=extra_notes,
        required_response="Return Python generator code only.",
    )
    prompt, _ = apply_qwen_output_constraint(
        prompt,
        mode=qwen_output_constraint_mode,
        model_name=model_name,
    )
    return prompt


G0_SYSTEM_PROMPT = build_system_prompt("G0", num_seeds=5)
G1_SYSTEM_PROMPT = build_system_prompt("G1", num_seeds=5)


def build_user_message(config, code_text: str, target_lines: list,
                       uncovered_line_tags: dict, description_html: str,
                       sample_input_anchor: str = "",
                       *,
                       gtor_prompt_profile: str = "legacy",
                       iteration: int = 1,
                       previous_failure_type: str = "",
                       ) -> str:
    """Build the user message for G0, G1, or ITERG."""
    del uncovered_line_tags
    desc = description_html
    desc = re.sub(r"<script[\s\S]*?</script>", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<style[\s\S]*?</style>", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    if len(desc) > 4000:
        desc = desc[:4000] + "..."

    lines = code_text.split("\n")
    annotated_lines = []
    target_set = set(target_lines)
    for i, line in enumerate(lines, 1):
        if i in target_set and config.strategy in {"G1", "ITERG"}:
            annotated_lines.append(f"{line}  # uncovered")
        else:
            annotated_lines.append(line)

    code_display = "\n".join(annotated_lines)

    if gtor_prompt_profile == "small_model_minimal":
        # Short coverage hint for BaseCG/ITERG
        coverage_hint = ""
        if config.strategy in {"G1", "ITERG"}:
            coverage_hint = (
                "\nSome code lines are marked # uncovered.\n"
                "You may try inputs that execute those lines.\n"
                "Coverage is only a hint; generated inputs must still be valid and bug-triggering.\n"
            )
        # ITERG feedback for iterations 2+
        iterg_feedback = ""
        if config.strategy == "ITERG" and iteration > 1:
            iterg_feedback = (
                "Previous generator did not produce a Pure@16 countercase.\n"
                "Try a different short generator.\n"
                "Avoid repeating the same pattern.\n"
            )
            if previous_failure_type:
                iterg_feedback += f"Previous failure type: {previous_failure_type}\n"
            iterg_feedback += "\n"

        return f"""## Problem Description
{desc}

## Sample Input Format
{sample_input_anchor if sample_input_anchor else "(not available)"}

## Student Code ({len(lines)} lines)
```python
{code_display}
```
{coverage_hint}
{iterg_feedback}## Task
Write generator.py. Execute as python generator.py <seed>.
Print exactly one valid stdin input that may expose bugs.
Output Python code only."""

    return f"""## Problem Description
{desc}

## Sample Input Format
{sample_input_anchor if sample_input_anchor else "(not available)"}

## Student Code ({len(lines)} lines)
```python
{code_display}
```

## Generator Contract
Your output will be saved as `generator.py` and executed as:
python generator.py <seed>

For each seed, the program must print exactly one complete stdin string to stdout.

Generate Python code that prints valid test inputs which may expose bugs in this code.
Output Python code only."""
