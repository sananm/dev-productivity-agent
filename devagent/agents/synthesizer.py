"""Synthesizer node — writes the final, source-cited answer.

Grounds the answer in retrieved context + tool results only. Token streaming is
handled by the graph layer (LangGraph 'messages' stream mode captures tokens
from this node's LLM call); the node itself just invokes the model.
"""

from __future__ import annotations

from devagent.agents.context import format_retrieved, format_tool_results
from devagent.agents.state import AgentState
from devagent.llm import get_llm
from devagent.prompts.loader import load_prompt


def _collect_citations(state: AgentState) -> list[str]:
    seen: list[str] = []
    for item in state.retrieved:
        c = item.get("citation")
        if c and c not in seen:
            seen.append(c)
    for trace in state.tool_calls:
        if trace.citation and trace.citation not in seen:
            seen.append(trace.citation)
    if state.write_result and state.write_result.get("citation"):
        c = state.write_result["citation"]
        if c not in seen:
            seen.append(c)
    return seen


def synthesize_node(state: AgentState) -> dict:
    tool_results = format_tool_results(state.tool_calls)
    if state.write_result:
        tool_results += f"\n\nWrite action: [{state.write_result['status']}] {state.write_result['summary']}"

    prompt = load_prompt(
        "synthesizer",
        version=state.prompt_version,
        repo=state.repo,
        query=state.query,
        retrieved=format_retrieved(state),
        tool_results=tool_results,
    )
    response = get_llm().invoke(prompt)
    answer = response.content if hasattr(response, "content") else str(response)
    return {"answer": answer.strip(), "citations": _collect_citations(state)}
