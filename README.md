# agent-fw

A generalized, **Lambda-first** LLM agent framework extracted from the
debugging-agent. It keeps the same architecture — universal message types, a
ReAct loop, provider-agnostic tool schemas, and multi-provider LLM support —
but strips out the CLI and all domain-specific code.

**To build a new agent you only add two things:**

1. an `instructions.md` file (the system prompt), and
2. one or more tool `.py` files.

No framework code changes required.

## Layout

```
fw/
├── config.yaml                     # sample config
├── pyproject.toml / requirements.txt
└── src/agent/
    ├── core/                       # types, context, ReAct loop  (unchanged)
    ├── tools/                      # Tool base + ToolSchema + built-in bash tool
    ├── llm/                        # base + registry + providers (anthropic/openai/gemini/custom/copilot)
    ├── flavors/                    # Flavor base + declarative loader (auto-discovery)
    ├── config.py                   # slim LLM + Lambda + agent config
    ├── setup.py                    # build_registry / get_system_prompt
    ├── lambda_handler.py           # THE entry point (no CLI)
    └── agents/                     # <-- your agents live here
        └── example/
            ├── instructions.md
            └── tools/
                └── echo.py
```

## How the loader works

`cfg.flavor` names a directory under `src/agent/agents/`. On each invocation the
framework:

1. reads `agents/<flavor>/instructions.md` as the system prompt, and
2. imports every module under `agents/<flavor>/tools/` and registers every
   concrete `Tool` subclass it finds (plus the built-in `bash` tool).

## Add a new agent (the whole recipe)

```
src/agent/agents/my_agent/
├── instructions.md          # system prompt
└── tools/
    ├── __init__.py          # empty
    └── my_tool.py           # one or more Tool subclasses
```

A tool is a class extending `Tool`:

```python
from typing import Any
from agent.config import AgentConfig
from agent.tools.base import Tool
from agent.tools.schema import ToolParameter, ToolSchema


class MyTool(Tool):
    # __init__ is optional. If it accepts a parameter, the loader passes the
    # AgentConfig so you can read config.extra. Omit it entirely if unneeded.
    def __init__(self, config: AgentConfig) -> None:
        self._setting = config.extra.get("my_setting")

    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="my_tool",
            description="What this tool does (the LLM reads this).",
            parameters=[
                ToolParameter(name="arg", type="string", description="An input."),
            ],
        )

    async def execute(self, **kwargs: Any) -> str:
        return f"got {kwargs['arg']}"
```

Then point config at it:

```yaml
flavor: my_agent
```

or set `AGENT_FLAVOR=my_agent`. That's it — Lambda is ready.

## Configuration

Config comes from `config.yaml` (searched in cwd, then the deploy dir, or
`AGENT_CONFIG`), overlaid by environment variables (which win):

| Env var                  | Purpose                                   |
|--------------------------|-------------------------------------------|
| `AGENT_LLM_PROVIDER`     | `custom` / `anthropic` / `openai` / `gemini` / `copilot` |
| `AGENT_LLM_MODEL`        | model id (else provider default)          |
| `AGENT_BASE_URL`         | gateway base URL (else provider default)  |
| `AGENT_API_KEY`          | LLM gateway key                           |
| `AGENT_CUSTOM_API_KEY`   | custom gateway key                        |
| `AGENT_FLAVOR`           | which agent to run                        |
| `AGENT_MAX_ITERATIONS`   | ReAct loop cap                            |
| `AGENT_LOG_LEVEL`        | logging level                             |

Agent-specific tool settings go under `extra:` and are read via
`config.extra` inside your tools.

## Lambda entry point

Handler: `agent.lambda_handler.lambda_handler`

Invocation shapes:

```jsonc
// direct / test
{"query": "..."}

// API Gateway proxy
{"body": "{\"query\": \"...\"}"}

// SQS event source
{"Records": [{"eventSource": "aws:sqs", "body": "{\"query\": \"...\"}"}]}
```

Optional per-request overrides:

```json
{"query": "...", "config_overrides": {"provider": "anthropic", "model": "...", "flavor": "my_agent"}}
```

Response body: `{"answer", "agent", "provider", "model", "tokens"}`.

## Local install

```bash
pip install -e .          # core
pip install -e ".[aws]"   # + boto3 if your tools call AWS
pip install -e ".[dev]"   # + pytest
```
