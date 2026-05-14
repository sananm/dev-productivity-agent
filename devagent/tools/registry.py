"""Tool registry — the single catalog the planner and executor bind to.

MCP-style: tools are declarative ToolSpecs (name, description, typed I/O,
handler, is_write). The planner sees the catalog text; the executor resolves
specs by name and validates arguments through each spec's Pydantic input model.
"""

from __future__ import annotations

import json
import time

from devagent.agents.state import ToolCallTrace
from devagent.tools.github_read import READ_TOOLS
from devagent.tools.github_write import WRITE_TOOLS
from devagent.tools.schemas import ToolResult, ToolSpec

ALL_TOOLS: list[ToolSpec] = [*READ_TOOLS, *WRITE_TOOLS]
_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in ALL_TOOLS}

READ_TOOL_NAMES = frozenset(spec.name for spec in READ_TOOLS)
WRITE_TOOL_NAMES = frozenset(spec.name for spec in WRITE_TOOLS)


def get_tool(name: str) -> ToolSpec:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown tool {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def is_write_tool(name: str) -> bool:
    return name in WRITE_TOOL_NAMES


def tool_catalog(*, writes: bool = True) -> str:
    """Human-readable catalog for the planner prompt."""
    specs = ALL_TOOLS if writes else READ_TOOLS
    lines = []
    for spec in specs:
        required = [
            f for f, info in spec.input_model.model_json_schema().get("properties", {}).items()
        ]
        kind = "WRITE" if spec.is_write else "read"
        lines.append(f"  - {spec.name} ({kind}): {spec.description} args: {required}")
    return "\n".join(lines)


def run_tool(name: str, args: dict, *, step_index: int) -> tuple[ToolResult, ToolCallTrace]:
    """Validate args against the spec, invoke the handler, and build a trace record."""
    spec = get_tool(name)
    start = time.perf_counter()
    try:
        validated = spec.input_model(**args)
        result = spec.handler(validated)
    except Exception as exc:  # noqa: BLE001 — surface any tool failure as a result
        result = ToolResult(ok=False, summary=f"{name} failed: {exc}")
    latency_ms = (time.perf_counter() - start) * 1000
    trace = ToolCallTrace(
        step_index=step_index,
        tool_name=name,
        input=args,
        output_summary=result.summary,
        ok=result.ok,
        latency_ms=round(latency_ms, 2),
        citation=result.citation,
    )
    return result, trace


def tool_schema_json(name: str) -> str:
    return json.dumps(get_tool(name).input_model.model_json_schema())
