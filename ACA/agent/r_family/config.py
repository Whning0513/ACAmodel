"""R-family configuration: R1 and R1.1 strategy parameters.

Each strategy registers its own dataclass — no shared config monolith.
Environment variables override defaults.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from ACA.agent.shared.config_base import BaseConfig


@dataclass
class R1Config(BaseConfig):
    """R1: batch agent, run_and_trace only, continuous coverage + CC finding."""
    strategy: str = "R1"

    # Engine
    max_iterations: int = 5
    patience: int = 5
    run_timeout: int = 30

    # Strategy features
    # Two-stage exit: don't stop at all_covered unless a CC has been found
    two_stage_exit: bool = True
    # Dynamic prompt swap: shift from coverage-guided to pure fuzzing when targets exhausted
    dynamic_prompt_swap: bool = True
    radical_mutation: bool = False
    no_tool_call_limit: int = 10


@dataclass
class R1_1Config(R1Config):
    """R1.1: R1 + radical mutation warning + strict 5-input batches."""
    strategy: str = "R1.1"
    radical_mutation: bool = True
    exact_input_count: int = 5          # LLM must provide exactly 5 inputs


@dataclass
class AgentGConfig(R1Config):
    """AgentG: generator-based feedback agent with generator trace tool."""
    strategy: str = "AgentG"
    dynamic_prompt_swap: bool = False
    num_seeds: int = 5
    generator_timeout: float = 2.0
    generator_memory_mb: int = 256
    generator_max_output_bytes: int = 256 * 1024
    generator_max_code_bytes: int = 256 * 1024
    seed_base: int = 0
    seed_list: Optional[List[int]] = field(default_factory=lambda: [0, 1, 2, 3, 4])
