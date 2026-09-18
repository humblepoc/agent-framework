"""Configuration loader — reads config.yaml and exposes typed objects.

Generalized, Lambda-first design. This keeps the LLM provider configuration
and generic agent settings from the original devops agent, but drops all
domain-specific (AWS service / Athena / CloudWatch) schema.

An agent is defined by:
  * an instructions Markdown file  -> the system prompt
  * a package of Tool subclasses   -> the tools

Config only needs to describe the LLM provider and a few agent-level knobs.
Anything an individual agent's tools need can live under the free-form
``extra`` mapping and be read by those tools.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LLM configuration
# ---------------------------------------------------------------------------

# Per-provider defaults for model and base_url. Used by apply_provider_defaults()
# to fill in empty values so users only need to set ``provider`` in YAML.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "custom":     {"model": "",                          "base_url": ""},
    "anthropic":  {"model": "claude-sonnet-4-6@default", "base_url": ""},
    "openai":     {"model": "",                          "base_url": ""},
    "gemini":     {"model": "",                          "base_url": ""},
    "copilot":    {"model": "claude-sonnet-4",           "base_url": ""},
}


def apply_provider_defaults(llm: "LLMConfig") -> None:
    """Fill in model/base_url defaults for the selected provider.

    Only fills values that are empty, so any explicit YAML / env setting
    always wins. Safe to call repeatedly. No-op for providers without an
    entry in PROVIDER_DEFAULTS.
    """
    defaults = PROVIDER_DEFAULTS.get(llm.provider, {})
    if not llm.model:
        llm.model = defaults.get("model", "")
    if not llm.base_url:
        llm.base_url = defaults.get("base_url", "")


class LLMConfig(BaseModel):
    provider: str = "custom"
    model: str = ""              # resolved by apply_provider_defaults()
    base_url: str = ""           # resolved by apply_provider_defaults()
    api_key: str = ""            # LLM gateway key
    custom_api_key: str = ""     # Custom gateway key; falls back to api_key
    pat: str = ""                # GitHub PAT with copilot scope (only used by copilot provider)
    temperature: float = 0.0
    max_tokens: int = 4096


# ---------------------------------------------------------------------------
# Lambda execution config
# ---------------------------------------------------------------------------
class LambdaConfig(BaseModel):
    """Configuration for Lambda execution mode.

    ``delay_seconds`` is the optional delay between receiving an event and
    starting work, enforced via SQS per-message DelaySeconds. Clamped to the
    SQS-supported range [0, 900] at the use site.
    """
    delay_seconds: int = 0


# ---------------------------------------------------------------------------
# Top-level application config
# ---------------------------------------------------------------------------
class AgentConfig(BaseModel):
    model_config = {"populate_by_name": True}

    llm: LLMConfig = Field(default_factory=LLMConfig)
    lambda_config: LambdaConfig = Field(default_factory=LambdaConfig, alias="lambda")

    # Which agent to run. Matches a directory name under the agents package
    # (see flavors.load_flavor). Defaults to "example".
    flavor: str = "example"
    max_iterations: int = 25
    log_level: str = "INFO"

    # Free-form config bag for agent-specific tool settings. Tools can read
    # values from here without the framework needing to know their schema.
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _config_search_paths() -> list[Path]:
    """Config search paths: cwd, then the package/deploy dir."""
    return [
        Path("config.yaml"),
        Path("config.yml"),
        Path(__file__).resolve().parent.parent.parent / "config.yaml",
    ]


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override into base. Override values win."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val
    return base


def load_config(config_path: str | None = None) -> AgentConfig:
    """Load config from YAML file, then overlay environment variables."""
    raw: dict[str, Any] = {}

    if config_path:
        p: Path | None = Path(config_path)
    else:
        env_path = os.environ.get("AGENT_CONFIG")
        if env_path:
            p = Path(env_path)
        else:
            p = next((f for f in _config_search_paths() if f.exists()), None)

    if p is not None and p.exists():
        with open(p) as f:
            raw = yaml.safe_load(f) or {}

    cfg = AgentConfig(**raw)

    # Environment variable overrides (highest priority)
    _apply_env(cfg)

    # Resolve provider-specific model/base_url defaults for empty values
    apply_provider_defaults(cfg.llm)

    return cfg


def _apply_env(cfg: AgentConfig) -> None:
    """Apply environment variable overrides (highest priority — wins over YAML).

    Supported variables:
        LLM:    AGENT_API_KEY, AGENT_CUSTOM_API_KEY, AGENT_LLM_PROVIDER,
                AGENT_LLM_MODEL, AGENT_BASE_URL, AGENT_LLM_PAT
        Agent:  AGENT_FLAVOR, AGENT_MAX_ITERATIONS, AGENT_LOG_LEVEL
    """
    if v := os.environ.get("AGENT_API_KEY"):
        cfg.llm.api_key = v
    if v := os.environ.get("AGENT_CUSTOM_API_KEY"):
        cfg.llm.custom_api_key = v
    if v := os.environ.get("AGENT_LLM_PROVIDER"):
        cfg.llm.provider = v
    if v := os.environ.get("AGENT_LLM_MODEL"):
        cfg.llm.model = v
    if v := os.environ.get("AGENT_BASE_URL"):
        cfg.llm.base_url = v
    if v := os.environ.get("AGENT_LLM_PAT"):
        cfg.llm.pat = v
    if v := os.environ.get("AGENT_FLAVOR"):
        cfg.flavor = v
    if v := os.environ.get("AGENT_MAX_ITERATIONS"):
        cfg.max_iterations = int(v)
    if v := os.environ.get("AGENT_LOG_LEVEL"):
        cfg.log_level = v
