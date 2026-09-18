"""AWS Lambda entry point (generic).

This is the only entry point in the framework — there is no CLI. It runs
the configured agent (``cfg.flavor``) against an input query and returns the
final answer.

Supported invocation shapes:
  1. Direct/test invoke:      {"query": "..."}
  2. API Gateway proxy:       {"body": "{\"query\": \"...\"}"}
  3. SQS event source:        {"Records": [{"eventSource": "aws:sqs",
                                            "body": "{\"query\": \"...\"}"}]}

Runtime config overrides may be passed alongside ``query``::

    {"query": "...", "config_overrides": {"provider": "...", "model": "...",
                                          "flavor": "..."}}

To build a new agent you never touch this file — you add an agent directory
(instructions.md + tools/) and point ``cfg.flavor`` at it.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def lambda_handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        force=True,
    )

    try:
        # SQS event source mapping: process each record's body as a request.
        records = event.get("Records")
        if records and any(r.get("eventSource") == "aws:sqs" for r in records):
            return _handle_sqs(records)

        body = _parse_body(event)
        query = body.get("query", "")
        if not query:
            return _response(400, {"error": "Missing 'query' in request"})

        overrides = body.get("config_overrides", {})
        result = _run_sync(query, overrides)
        return _response(200, result)

    except Exception as e:
        log.exception("Lambda handler error")
        return _response(500, {"error": f"{type(e).__name__}: {e}"})


def _handle_sqs(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Process SQS records. Each body is a JSON request with a 'query'."""
    for record in records:
        if record.get("eventSource") != "aws:sqs":
            continue
        try:
            payload = json.loads(record.get("body", "{}"))
        except (json.JSONDecodeError, TypeError):
            log.exception("Failed to parse SQS record body; skipping")
            continue
        query = payload.get("query", "")
        if not query:
            log.warning("SQS record missing 'query'; skipping")
            continue
        _run_sync(query, payload.get("config_overrides", {}))
    return {}


def _run_sync(query: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Run the async agent on a fresh event loop (Lambda-safe)."""
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_run(query, overrides))
    finally:
        loop.close()


async def _run(query: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Load config, build the agent, run the loop, return structured results."""
    from agent.config import apply_provider_defaults, load_config
    from agent.core.context import ConversationContext
    from agent.core.loop import run_agent
    from agent.core.types import Message, Role
    from agent.llm.registry import get_provider
    from agent.setup import build_registry, get_flavor, get_system_prompt

    cfg = load_config()

    # Runtime overrides
    if v := overrides.get("provider"):
        cfg.llm.provider = v
    if v := overrides.get("model"):
        cfg.llm.model = v
    if v := overrides.get("flavor"):
        cfg.flavor = v
    apply_provider_defaults(cfg.llm)

    provider = get_provider(cfg.llm.provider, cfg)
    flavor = get_flavor(cfg)
    registry = build_registry(cfg, flavor)
    context = ConversationContext(system_prompt=get_system_prompt(cfg, flavor))
    context.add(Message(role=Role.USER, content=query))

    log.info(
        "Running agent '%s' (provider=%s model=%s max_iterations=%d)",
        cfg.flavor, cfg.llm.provider, cfg.llm.model, cfg.max_iterations,
    )
    result = await run_agent(provider, registry, context, max_iterations=cfg.max_iterations)

    return {
        "answer": result.content or "",
        "agent": cfg.flavor,
        "provider": cfg.llm.provider,
        "model": cfg.llm.model,
        "tokens": context.estimate_tokens(),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    body = event.get("body", event)
    if isinstance(body, str):
        body = json.loads(body)
    return body


def _response(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }
