"""System prompts for L0 and L1 strategies.

L0: target-only — problem description + student code, no coverage annotation.
L1: mismatch-augment — same but with uncovered lines marked in code.
"""

from ACA.agent.shared.prompt_templates import build_shared_base_system_prompt

# L0 uses GENERATE_TEST_INPUTS_TOOL, L1 uses the same tool but different prompt
GENERATE_TEST_INPUTS_TOOL = {
    "type": "function",
    "function": {
        "name": "generate_test_inputs",
        "description": (
            "Submit exactly 5 test inputs for the student's code. "
            "Each test_input is the complete stdin for one execution. "
            "Provide one reason for each input explaining why it may expose a bug."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "test_inputs": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {"type": "string"},
                    "description": "Array of exactly 5 test inputs, each one complete stdin string.",
                },
                "reasons": {
                    "type": "array",
                    "minItems": 5,
                    "maxItems": 5,
                    "items": {"type": "string"},
                    "description": "Exactly 5 reasons, one for each test input.",
                },
            },
            "required": ["test_inputs", "reasons"],
        },
    },
}

L0_TOOLS = [GENERATE_TEST_INPUTS_TOOL]

# ---------------------------------------------------------------------------
# L0 SYSTEM PROMPT — target-only
# ---------------------------------------------------------------------------

L0_SYSTEM_PROMPT = build_shared_base_system_prompt(
    test_input_count=5,
    extra_notes=[],
    required_response=(
        "Return exactly 5 test inputs and exactly 5 brief reasons in the required structured output format."
    ),
)


# ---------------------------------------------------------------------------
# L1 SYSTEM PROMPT — mismatch-augment
# ---------------------------------------------------------------------------

L1_SYSTEM_PROMPT = build_shared_base_system_prompt(
    test_input_count=5,
    extra_notes=[
        "Some lines in the student's code are marked with `# uncovered`. These lines were not exercised by the existing passing tests. You may prioritize inputs that execute these lines.",
    ],
    required_response=(
        "Return exactly 5 test inputs and exactly 5 brief reasons in the required structured output format."
    ),
)


def build_user_message(config, code_text: str, target_lines: list,
                       uncovered_line_tags: dict, description_html: str,
                       sample_input_anchor: str = "") -> str:
    """Build the user message for L0 or L1.

    For L0 (target-only): code is shown without annotation.
    For L1 (mismatch-augment): uncovered lines are annotated in the code.
    """
    # Strip HTML tags for a plain text description
    import re
    desc = description_html
    desc = re.sub(r"<script[\s\S]*?</script>", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<style[\s\S]*?</style>", " ", desc, flags=re.IGNORECASE)
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()

    # Truncate very long descriptions
    if len(desc) > 4000:
        desc = desc[:4000] + "..."

    lines = code_text.split("\n")
    annotated_lines = []
    target_set = set(target_lines)
    for i, line in enumerate(lines, 1):
        # V0 reuses L1's mismatch-augment annotated code display
        if i in target_set and config.strategy in ("L1", "V0"):
            annotated_lines.append(f"{line}  # uncovered")
        else:
            annotated_lines.append(line)

    code_display = "\n".join(annotated_lines)
    total_lines = len(lines)

    # L0: no coverage info, generic prompt
    if config.strategy == "L0":
        msg = f"""## Problem Description
{desc}

## Sample Input Format
{sample_input_anchor if sample_input_anchor else "(not available)"}

## Student Code ({total_lines} lines)
```python
{code_display}
```

Generate exactly {config.test_input_count} valid test inputs that may expose bugs in this code."""
        return msg

    # L1 / V0: same structure as L0, with only # uncovered comments added in code.
    msg = f"""## Problem Description
{desc}

## Sample Input Format
{sample_input_anchor if sample_input_anchor else "(not available)"}

## Student Code ({total_lines} lines)
```python
{code_display}
```

Generate exactly {config.test_input_count} valid test inputs that may expose bugs in this code."""

    return msg
