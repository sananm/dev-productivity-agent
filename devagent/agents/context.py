"""Shared formatting helpers — turn structured state into prompt-ready text."""

from __future__ import annotations

from devagent.agents.state import AgentState, ToolCallTrace

MAX_CHUNK_CHARS = 800


def format_retrieved(state: AgentState) -> str:
    if not state.retrieved:
        return "(no retrieved context)"
    lines = []
    for item in state.retrieved:
        body = item["text"].strip()
        if len(body) > MAX_CHUNK_CHARS:
            body = body[:MAX_CHUNK_CHARS] + " ..."
        lines.append(f"[{item['source_type']} | {item['citation']}]\n{body}")
    return "\n\n".join(lines)


def format_tool_results(traces: list[ToolCallTrace]) -> str:
    if not traces:
        return "(no tool calls)"
    lines = []
    for t in traces:
        status = "ok" if t.ok else "FAILED"
        cite = f" ({t.citation})" if t.citation else ""
        lines.append(f"- {t.tool_name} [{status}]{cite}: {t.output_summary}")
    return "\n".join(lines)
