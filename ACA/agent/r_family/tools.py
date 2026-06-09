"""R-family tool definitions."""


def build_run_and_trace_tool(exact_input_count: int = 5) -> dict:
    return {
        "type": "function",
        "function": {
            "name": "run_and_trace",
            "description": (
                f"Execute the student code with exactly {exact_input_count} test inputs and return validator, "
                "reference/student verdict, and coverage feedback for those inputs."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "test_inputs": {
                        "type": "array",
                        "minItems": exact_input_count,
                        "maxItems": exact_input_count,
                        "items": {"type": "string"},
                        "description": (
                            f"An array of exactly {exact_input_count} strings. Each string represents ONE COMPLETE test case. "
                            "If a test case requires multiple lines, use the literal '\\n' "
                            "character within that single string (e.g., '5\\n1 2 3 4 5'). "
                            "Each input MUST STRICTLY ADHERE to the problem's exact input format."
                        ),
                    },
                },
                "required": ["test_inputs"],
            },
        },
    }


def build_run_generator_and_trace_tool(generator_seed_count: int = 5, *, gtor_prompt_profile: str = "legacy") -> dict:
    if gtor_prompt_profile == "small_model_minimal":
        return {
            "type": "function",
            "function": {
                "name": "run_generator_and_trace",
                "description": (
                    "Compile Python generator code, run it, then validate and execute "
                    "the generated inputs against the reference solution and the student's code."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "generator_code": {
                            "type": "string",
                            "description": (
                                "Python code for generator.py. It will be executed as `python generator.py <seed>` "
                                "and should print one complete stdin string to stdout for each seed."
                            ),
                        },
                    },
                    "required": ["generator_code"],
                },
            },
        }
    return {
        "type": "function",
        "function": {
            "name": "run_generator_and_trace",
            "description": (
                f"Compile Python generator code, run it on exactly {generator_seed_count} seeds, then validate and execute "
                "the generated inputs against the reference solution and the student's code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "generator_code": {
                        "type": "string",
                        "description": (
                            "Python code for generator.py. It will be executed as `python generator.py <seed>` "
                            "and should print one complete stdin string to stdout for each seed."
                        ),
                    },
                    "seeds": {
                        "type": "array",
                        "minItems": generator_seed_count,
                        "maxItems": generator_seed_count,
                        "items": {"type": "integer"},
                        "description": f"An array of exactly {generator_seed_count} integer seeds.",
                    },
                },
                "required": ["generator_code", "seeds"],
            },
        },
    }


RUN_AND_TRACE_TOOL = build_run_and_trace_tool(exact_input_count=5)
RUN_GENERATOR_AND_TRACE_TOOL = build_run_generator_and_trace_tool(generator_seed_count=5)


RUN_AND_TRACE_TOOL_R1_1 = {
    "type": "function",
    "function": {
        "name": "run_and_trace",
        "description": (
            "Execute the student code with EXACTLY 5 test inputs and return coverage "
            "information + execution status. Each input must use a completely different attack vector."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mutation_strategy": {
                    "type": "string",
                    "description": (
                        "CRITICAL: Before generating test inputs, analyze the PREVIOUS "
                        "execution result. Explain WHY the previous inputs SURVIVED or "
                        "failed to cover targets, and declare your RADICAL MUTATION strategy "
                        "for this batch (e.g., negative bounds, completely empty strings, "
                        "worst-case topologies, constraint boundary violations)."
                    ),
                },
                "test_inputs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "An array of EXACTLY 5 strings. These 5 inputs MUST use completely "
                        "different attack vectors. Each string represents ONE COMPLETE test case."
                    ),
                },
            },
            "required": ["mutation_strategy", "test_inputs"],
        },
    },
}


def get_tools(
    strategy: str,
    *,
    generator_seed_count: int = 5,
    exact_input_count: int = 5,
    gtor_prompt_profile: str = "legacy",
) -> list:
    """Return tool definitions for the given R-family strategy."""
    if strategy == "AgentG":
        return [build_run_generator_and_trace_tool(
            generator_seed_count=generator_seed_count,
            gtor_prompt_profile=gtor_prompt_profile,
        )]
    if strategy == "R1.1":
        return [RUN_AND_TRACE_TOOL_R1_1]
    return [build_run_and_trace_tool(exact_input_count=exact_input_count)]
