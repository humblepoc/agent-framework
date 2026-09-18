"""Sample tool demonstrating how to add a tool to an agent.

Drop a file like this under ``agents/<name>/tools/`` and the framework will
auto-discover any concrete :class:`~agent.tools.base.Tool` subclass it defines.

A tool may take no constructor args, or accept the loaded ``AgentConfig`` —
the loader detects which and passes config when the constructor wants it. Use
``config.extra`` for any agent-specific settings you configure in config.yaml.
"""
from __future__ import annotations

from typing import Any

from agent.config import AgentConfig
from agent.tools.base import Tool
from agent.tools.schema import ToolParameter, ToolSchema


class EchoTool(Tool):
    """Return the given message, optionally uppercased.

    Accepts config so it can read a default prefix from ``config.extra``:

        extra:
          echo_prefix: "[example] "
    """

    def __init__(self, config: AgentConfig) -> None:
        self._prefix = str(config.extra.get("echo_prefix", ""))

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="echo",
            description="Echo a message back to the caller. Useful as a connectivity/sanity check.",
            parameters=[
                ToolParameter(
                    name="message",
                    type="string",
                    description="The message to echo back.",
                ),
                ToolParameter(
                    name="uppercase",
                    type="boolean",
                    description="If true, return the message in uppercase.",
                    required=False,
                    default=False,
                ),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        message: str = kwargs["message"]
        if kwargs.get("uppercase"):
            message = message.upper()
        return f"{self._prefix}{message}"
