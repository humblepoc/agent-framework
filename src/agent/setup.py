"""Agent setup helpers — shared by the Lambda entry point and tests.

Headless-only: no console/terminal dependencies, so it runs cleanly in
Lambda. Wiring is fully generic — the selected flavor (``cfg.flavor``) is
loaded from its agent directory, contributing the system prompt and tools.
"""

from __future__ import annotations

import logging

from agent.config import AgentConfig
from agent.flavors.base import Flavor
from agent.flavors.loader import load_flavor
from agent.tools.base import ToolRegistry
from agent.tools.bash import BashTool

log = logging.getLogger(__name__)

# Built-in tools available to every agent. Set INCLUDE_BASH=False in a future
# revision if you want a locked-down agent; kept on by default to mirror the
# original debugging-agent behavior.
_BUILTIN_TOOLS = [BashTool]


def get_flavor(cfg: AgentConfig) -> Flavor:
    """Load the flavor named by ``cfg.flavor``."""
    return load_flavor(cfg.flavor)


def build_registry(cfg: AgentConfig, flavor: Flavor | None = None) -> ToolRegistry:
    """Build the tool registry: built-ins + the flavor's discovered tools."""
    registry = ToolRegistry()
    for builtin in _BUILTIN_TOOLS:
        registry.register(builtin())

    flavor = flavor or get_flavor(cfg)
    for tool in flavor.tools(cfg):
        registry.register(tool)

    return registry


def get_system_prompt(cfg: AgentConfig, flavor: Flavor | None = None) -> str:
    """Return the system prompt for the configured flavor."""
    flavor = flavor or get_flavor(cfg)
    prompt = flavor.system_prompt(cfg)
    if prompt:
        return prompt
    return "You are a helpful assistant with access to tools. Use them to help the user."
