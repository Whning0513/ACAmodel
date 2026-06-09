"""Shared configuration base class for all strategy families.

Provides:
  - _env()  — manual .env file parser (no python-dotenv dependency)
  - BaseConfig — common LLM/API fields, __post_init__, to_llm_config()

All strategy configs inherit from BaseConfig, avoiding the previously
triplicated _env / __post_init__ / to_llm_config across 3 config files.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from ACA.agent.shared.prompt_templates import (
    QWEN_OUTPUT_CONSTRAINT_TEXT,
    SEED_CONTRACT_CLARIFICATION_TEXT,
)


_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _REPO_ROOT.parent
_ENV_FILES_LOADED = False
_ENV_FILE_SOURCES: List[str] = []
_ENV_KEY_SOURCES: Dict[str, str] = {}


def _candidate_env_paths() -> List[Path]:
    return [
        _REPO_ROOT / ".env",
        _WORKSPACE_ROOT / ".env",
    ]


def _load_env_files_once() -> None:
    global _ENV_FILES_LOADED
    if _ENV_FILES_LOADED:
        return

    for path in _candidate_env_paths():
        if not path.exists():
            continue
        _ENV_FILE_SOURCES.append(str(path))
        with path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                value = v.strip().strip("\"'")
                if not value:
                    # Empty placeholders in .env should not block later fallback files.
                    continue
                # Shell env wins; earlier env files also win over later ones.
                if key in os.environ:
                    _ENV_KEY_SOURCES.setdefault(key, "shell")
                    continue
                os.environ[key] = value
                _ENV_KEY_SOURCES.setdefault(key, str(path))

    _ENV_FILES_LOADED = True


def get_env_source(key: str) -> str:
    if key in os.environ and key not in _ENV_KEY_SOURCES:
        _ENV_KEY_SOURCES[key] = "shell"
    return _ENV_KEY_SOURCES.get(key, "default")


def get_loaded_env_files() -> List[str]:
    _load_env_files_once()
    return list(_ENV_FILE_SOURCES)


def _env(key: str, default: str = "") -> str:
    """Read env var with fallback order: shell > ACA/.env > workspace/.env."""
    val = os.environ.get(key, "")
    if val:
        _ENV_KEY_SOURCES.setdefault(key, "shell")
        return val

    _load_env_files_once()
    val = os.environ.get(key, "")
    return val or default


@dataclass
class BaseConfig:
    """Shared LLM + API fields and initialization logic.

    Subclass this for each strategy family, then add strategy-specific fields.
    __post_init__ auto-resolves model, seed, api_base, api_key from env.
    """

    # LLM
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 16383
    seed: Optional[int] = None
    llm_timeout: int = 320

    # API routing (auto-resolved in __post_init__)
    api_base: str = ""
    api_key: str = ""

    verbose: bool = False
    qwen_output_constraint_mode: str = "auto"
    qwen_output_constraint_applied: bool = False
    qwen_output_constraint_text: str = QWEN_OUTPUT_CONSTRAINT_TEXT
    seed_contract_clarification_applied: bool = False
    seed_contract_clarification_text: str = SEED_CONTRACT_CLARIFICATION_TEXT
    gtor_prompt_profile: str = "legacy"
    env_source: Dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self):
        if not self.model:
            self.model = _env("LLM_MODEL", "gpt-4o-mini-ca")
        if self.seed is None:
            raw = _env("LLM_SEED", "")
            self.seed = int(raw) if raw.strip() else None

        # Model-aware API routing
        if self.model == "deepseek-v4-pro":
            self.api_base = _env("DEEPSEEK_API_BASE", "https://api.deepseek.com")
            self.api_key = _env("DEEPSEEK_API_KEY", "")
            api_base_source = get_env_source("DEEPSEEK_API_BASE")
            api_key_source = get_env_source("DEEPSEEK_API_KEY")
        else:
            self.api_base = _env("CHATANYWHERE_API_BASE", "")
            self.api_key = _env("CHATANYWHERE_API_KEY", "")
            api_base_source = get_env_source("CHATANYWHERE_API_BASE")
            api_key_source = get_env_source("CHATANYWHERE_API_KEY")
            if not self.api_base:
                self.api_base = _env("LLM_API_BASE", "")
                api_base_source = get_env_source("LLM_API_BASE")
            if not self.api_key:
                self.api_key = _env("LLM_API_KEY", "")
                api_key_source = get_env_source("LLM_API_KEY")

        self.env_source = {
            "model": get_env_source("LLM_MODEL"),
            "api_base": api_base_source,
            "api_key": api_key_source,
            "env_files": ",".join(get_loaded_env_files()) if get_loaded_env_files() else "none",
        }

    def to_llm_config(self):
        from ACA.agent.shared.llm_client import LLMConfig
        return LLMConfig(
            model=self.model,
            api_base=self.api_base,
            api_key=self.api_key,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            seed=self.seed,
            llm_timeout=self.llm_timeout,
            verbose=self.verbose,
            env_source=self.env_source,
        )
