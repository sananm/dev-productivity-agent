"""Planner node — decomposes the query into an ordered multi-step plan.

Uses chain-of-thought scaffolding and the LLM's structured-output mode to emit a
typed Plan. A circuit breaker retries malformed output up to MAX_PLANNER_ITERATIONS
times, then degrades to a minimal retrieve->answer plan rather than crashing.
"""

from __future__ import annotations

from devagent.agents.state import AgentState, Plan, PlanStep
from devagent.llm import get_llm
from devagent.prompts.loader import load_prompt
from devagent.tools.registry import ALL_TOOLS, get_tool, tool_catalog

MAX_PLANNER_ITERATIONS = 3


def _infer_tool_name(step: PlanStep) -> str | None:
    """Recover a missing tool_name — small models often fill args but not the name.

    First look for an exact tool name in the description, then match the provided
    tool_args against each tool's distinct argument signature.
    """
    desc = step.description.lower()
    for spec in ALL_TOOLS:
        if spec.name in desc or spec.name.replace("_", " ") in desc:
            return spec.name

    arg_keys = {k for k in step.tool_args if k != "repo"}
    if not arg_keys:
        return None
    best, best_score = None, 0.0
    for spec in ALL_TOOLS:
        fields = set(spec.input_model.model_fields) - {"repo"}
        if not arg_keys <= fields:
            continue  # provided args must be valid for this tool
        score = len(arg_keys & fields) / max(len(fields), 1)
        if score > best_score:
            best, best_score = spec.name, score
    return best


def _normalize(steps: list[PlanStep]) -> list[PlanStep]:
    """Re-index steps, recover missing tool names, and guarantee a final 'answer' step."""
    clean = [s for s in steps if s.action in ("retrieve", "tool")]
    for step in clean:
        if step.action == "tool" and not step.tool_name:
            step.tool_name = _infer_tool_name(step)
        # drop tool steps we still cannot resolve to a real tool
    clean = [
        s for s in clean
        if s.action == "retrieve" or (s.tool_name and _is_known(s.tool_name))
    ]
    for i, step in enumerate(clean):
        step.index = i
    clean.append(
        PlanStep(index=len(clean), action="answer", description="Synthesize the final answer.")
    )
    return clean


def _is_known(name: str) -> bool:
    try:
        get_tool(name)
        return True
    except KeyError:
        return False


def _fallback_plan() -> list[PlanStep]:
    return [
        PlanStep(index=0, action="retrieve", description="Gather context for the query."),
        PlanStep(index=1, action="answer", description="Synthesize the final answer."),
    ]


def plan_node(state: AgentState) -> dict:
    prompt = load_prompt(
        "planner",
        version=state.prompt_version,
        repo=state.repo,
        query=state.query,
        tools=tool_catalog(),
    )
    structured = get_llm().with_structured_output(Plan)

    last_error: Exception | None = None
    for _attempt in range(MAX_PLANNER_ITERATIONS):
        try:
            plan: Plan = structured.invoke(prompt)
            steps = _normalize(plan.steps)
            if any(s.action in ("retrieve", "tool") for s in steps):
                return {"plan": steps, "planner_reasoning": plan.reasoning}
        except Exception as exc:  # noqa: BLE001 — retry malformed structured output
            last_error = exc

    return {
        "plan": _fallback_plan(),
        "planner_reasoning": "planner fell back to a minimal retrieve->answer plan",
        "error": f"planner degraded after {MAX_PLANNER_ITERATIONS} attempts: {last_error}"
        if last_error
        else None,
    }
