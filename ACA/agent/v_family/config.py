"""V-family configuration: V0 strategy parameters.

V0 = recursive L1 — L1 prompt but in a multi-round loop with coverage feedback.
"""

from dataclasses import dataclass

from ACA.agent.shared.config_base import BaseConfig


@dataclass
class V0Config(BaseConfig):
    """V0: recursive L1 — multi-round mismatch-augment with coverage feedback."""
    strategy: str = "V0"

    # Engine
    max_iterations: int = 5
    patience: int = 5
    run_timeout: int = 30
    test_input_count: int = 5
