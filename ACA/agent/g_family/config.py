"""G-family configuration: G0, G1, and ITERG strategy parameters."""

from dataclasses import dataclass, field
from typing import List, Optional

from ACA.agent.shared.config_base import BaseConfig


@dataclass
class GConfig(BaseConfig):
    strategy: str = "G1"
    num_seeds: int = 5
    generator_timeout: float = 2.0
    generator_memory_mb: int = 256
    generator_max_output_bytes: int = 256 * 1024
    generator_max_code_bytes: int = 256 * 1024
    max_iterations: int = 1
    patience: int = 1
    run_timeout: float = 30.0
    seed_base: int = 0
    seed_list: Optional[List[int]] = field(default_factory=lambda: [0, 1, 2, 3, 4])


@dataclass
class G0Config(GConfig):
    strategy: str = "G0"


@dataclass
class G1Config(GConfig):
    strategy: str = "G1"


@dataclass
class ITERGConfig(GConfig):
    strategy: str = "ITERG"
    max_iterations: int = 5
    patience: int = 5
