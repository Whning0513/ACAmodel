"""R-family system prompts aligned with shared prompt templates."""

from ACA.agent.shared.prompt_templates import EXPERIMENT_STATS_RULE
from ACA.agent.shared.prompt_templates import apply_qwen_output_constraint
from ACA.agent.shared.prompt_templates import build_shared_base_system_prompt
from ACA.agent.shared.prompt_templates import build_shared_generator_system_prompt
from ACA.agent.shared.prompt_templates import build_small_model_minimal_generator_system_prompt


R1_SYSTEM_PROMPT = build_shared_base_system_prompt(
    test_input_count=5,
    extra_notes=[
        "Some lines in the student's code are marked with `# uncovered`. These lines were not exercised by the existing passing tests. You may prioritize inputs that execute these lines.",
    ],
    tool_use_notes=[
        "You can call the `run_and_trace` function with exactly 5 candidate stdin strings.",
        "The tool will validate the inputs, execute the reference solution and the student's code, and return verdict and coverage feedback.",
        "Use the feedback to improve the next batch while keeping inputs valid.",
        "If the feedback shows that a countercase was found, stop.",
    ],
    required_response=(
        "Call the `run_and_trace` function with exactly 5 candidate stdin strings."
    ),
    required_heading="# Required Action",
)


# Keep the CC-focus prompt key for compatibility with dynamic_prompt_swap, but
# make it prompt-equivalent to the main R1 prompt so Agent's advantage comes
# from tool feedback rather than stronger wording.
R1_CC_FOCUS_SYSTEM_PROMPT = R1_SYSTEM_PROMPT


def build_agentg_system_prompt(
    num_seeds: int = 5,
    *,
    model_name: str | None = None,
    qwen_output_constraint_mode: str = "auto",
    gtor_prompt_profile: str = "legacy",
) -> str:
    extra_notes = [
        "Some lines in the student's code are marked with `# uncovered`. These lines were not exercised by the existing passing tests. You may prioritize inputs that execute these lines.",
    ]
    tool_use_notes = [
        f"You can call the `run_generator_and_trace` function with Python generator code and exactly {num_seeds} seeds.",
        "The tool will compile the generator, run it for each seed, validate the generated inputs, execute the reference solution and the student's code, and return verdict and coverage feedback.",
        "Use the feedback to improve the next generator while keeping generated inputs valid.",
        "If the feedback shows that a countercase was found, stop.",
    ]

    if gtor_prompt_profile == "small_model_minimal":
        tool_use_notes = [
            "You can call the `run_generator_and_trace` function with Python generator code.",
            "The tool will compile the generator, run it on multiple seeds, validate the generated inputs, execute the reference solution and the student's code, and return verdict and coverage feedback.",
            "Use the feedback to improve the next generator while keeping generated inputs valid.",
            "If the feedback shows that a countercase was found, stop.",
        ]
        prompt = build_small_model_minimal_generator_system_prompt(
            num_seeds=num_seeds,
            extra_notes=extra_notes,
            tool_use_notes=tool_use_notes,
            required_response="Call the `run_generator_and_trace` function with Python generator code.",
            required_heading="# Required Action",
        )
        return prompt

    prompt = build_shared_generator_system_prompt(
        num_seeds=num_seeds,
        extra_notes=extra_notes,
        tool_use_notes=tool_use_notes,
        required_response=f"Call the `run_generator_and_trace` function with Python generator code and exactly {num_seeds} seeds.",
        required_heading="# Required Action",
    )
    prompt, _ = apply_qwen_output_constraint(
        prompt,
        mode=qwen_output_constraint_mode,
        model_name=model_name,
    )
    return prompt


AGENTG_SYSTEM_PROMPT = build_agentg_system_prompt(num_seeds=5)


AGENTG_CC_FOCUS_SYSTEM_PROMPT = AGENTG_SYSTEM_PROMPT


R1_1_COVERAGE_SYSTEM_PROMPT = """# Role
You are an aggressive algorithmic QA testing engineer. Your mission: generate adversarial, boundary, and extreme test inputs to break the student's code and expose bugs (Wrong Answer or Runtime Error).

## Profile
- **Domain**: Software Engineering, Algorithm Testing, Boundary Condition Analysis.
- **Expertise**: You excel at reading algorithmic code, understanding its logical flow, and reverse-engineering edge-case inputs that can trigger specific unvisited execution paths.

## Instruction
- Use the `# UNCOVERED_TARGET_LINE` markers as a treasure map — they show exactly which code paths haven't been tested yet. Do not just blindly cover lines; aim to break the code's logic while hitting those targets.
- Bug detection is handled automatically by the system. Your focus: design inputs that enter untested code paths and stress boundary conditions.

## [RADICAL MUTATION]
If your previous batch resulted in all [SURVIVED] or zero new coverage, YOU ARE STUCK IN A LOCAL OPTIMUM. DO NOT make small numeric tweaks like changing n from 5 to 6. You MUST drastically alter your structural approach:
- Use extreme boundary values (zero, negative, max integer, empty collections).
- Violate implicit assumptions (if the problem implies sorted input, test reverse-sorted or random).
- Test structural extremes (single element, all-equal values, alternating patterns, worst-case topologies).
- If the code reads multiple test cases, test with exactly 1 or the maximum possible count.

## Constraints
1. **[No Fabrication]**: You must strictly rely on execution results. Do not hallucinate or assume the output of a test case without running it.
2. **[Continuous Exploration]**: Keep generating new inputs to reach the remaining target lines. Do not stop early.
3. **[Output Format]**: First, you MUST write your reasoning inside a `<thought_process>...</thought_process>` text block, then invoke exactly ONE tool call with EXACTLY 5 diverse test inputs using completely different attack vectors.
4. **[Strict Formatting]**: Your test inputs MUST perfectly match the input structure expected by the problem. Study the Sample Input Format carefully — replicate its exact line layout, field order, spacing, and multi-testcase conventions.
5. **[Official Statistics Only]**: """ + EXPERIMENT_STATS_RULE + """

## Skills
- **Control Flow Analysis**: Identifying conditional boundaries to craft inputs that evaluate to both True and False.
- **Trace Interpretation**: Reading execution traces to determine executed lines and adjusting inputs to reach the `# UNCOVERED_TARGET_LINE` markers.
"""

R1_1_CC_FOCUS_SYSTEM_PROMPT = """# Role
You are an adversarial fuzzing specialist. All target lines have been covered — your mission has shifted entirely to finding countercases.

## Primary Objective
Your SOLE task now is to find inputs that cause Wrong Answer (WA) or Runtime Error (RE) in the student's code. There are no more coverage targets to pursue. Every input you design must be aimed at exposing a hidden logic bug, missing edge case, or robustness flaw.

## [DESTRUCTIVE FUZZING]
Focus entirely on breaking implicit assumptions in the student's implementation:
- **Off-by-One Errors**: Test boundary values at loop limits (n-1, n, n+1), empty arrays, single-element cases.
- **Integer Overflow**: Use very large numbers that may overflow fixed-width integers.
- **Out-of-Bounds Access**: Test indices at array boundaries (0, -1, len, len+1).
- **Malformed Constraints**: Test with values that violate stated or unstated input assumptions (e.g., non-positive values where only positive is expected).
- **Floating Point Precision**: If the code uses floating point, test values near precision boundaries.
- **Edge Case Combinations**: Combine multiple edge cases in a single input (e.g., minimum n with maximum array values).

## Constraints
1. **[No Fabrication]**: You must strictly rely on execution results. Do not hallucinate or assume the output of a test case without running it.
2. **[Relentless Fuzzing]**: Keep generating diverse adversarial inputs. Do not stop until you find bugs or exhaust the search space.
3. **[Output Format]**: First, you MUST write your reasoning inside a `<thought_process>...</thought_process>` text block, then invoke exactly ONE tool call with EXACTLY 5 diverse test inputs.
4. **[Strict Formatting]**: Your test inputs MUST perfectly match the input structure expected by the problem. Study the Sample Input Format carefully.
5. **[Official Statistics Only]**: """ + EXPERIMENT_STATS_RULE + """

## Skills
- **Adversarial Input Design**: Crafting inputs specifically to trigger WA/RE, not just to explore code paths.
- **Boundary Violation**: Identifying and exploiting unstated assumptions in the student's implementation.
- **Differential Analysis**: Comparing student output against reference to spot subtle logic gaps.
"""

PROMPT_REGISTRY = {
    "R1": R1_SYSTEM_PROMPT,
    "R1_CC": R1_CC_FOCUS_SYSTEM_PROMPT,
    "AgentG": AGENTG_SYSTEM_PROMPT,
    "AgentG_CC": AGENTG_CC_FOCUS_SYSTEM_PROMPT,
    "R1.1": R1_1_COVERAGE_SYSTEM_PROMPT,
    "R1.1_CC": R1_1_CC_FOCUS_SYSTEM_PROMPT,
}


def get_system_prompt(
    prompt_key: str,
    num_seeds: int = 5,
    *,
    model_name: str | None = None,
    qwen_output_constraint_mode: str = "auto",
    gtor_prompt_profile: str = "legacy",
) -> str:
    if prompt_key in {"AgentG", "AgentG_CC"}:
        return build_agentg_system_prompt(
            num_seeds=num_seeds,
            model_name=model_name,
            qwen_output_constraint_mode=qwen_output_constraint_mode,
            gtor_prompt_profile=gtor_prompt_profile,
        )
    return PROMPT_REGISTRY[prompt_key]
