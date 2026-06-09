"""L-family configuration: L0 and L1 strategy parameters.

L0 = target-only prompt (no coverage annotation).
L1 = mismatch-augment prompt (annotated uncovered lines).
"""

from dataclasses import dataclass

from ACA.agent.shared.config_base import BaseConfig


@dataclass
class LConfig(BaseConfig):
    """Base config for L-family strategies (single-round, non-agent)."""
    strategy: str = "L1"
    test_input_count: int = 5          # how many test inputs to generate per round
    run_timeout: int = 30


@dataclass
class L0Config(LConfig):
    """L0: target-only prompt — no coverage annotation in prompt."""
    strategy: str = "L0"


@dataclass
class L1Config(LConfig):
    """L1: mismatch-augment prompt — uncovered lines annotated in code."""
    strategy: str = "L1"
