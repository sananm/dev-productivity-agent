"""Executor node — dispatches GitHub tools for the plan's 'tool' steps.

Read tools run immediately and every call is appended to a JSONL trace
(tool name, input, output, latency, step index). A WRITE tool is never executed
here: its arguments are drafted from context, stored as state.pending_write, and
the graph routes to the confirmation gate. One write per plan; a circuit breaker
caps total tool steps at MAX_EXECUTOR_ITERATIONS.
"""

from __future__ import annotations

import json

from devagent.agents.context import format_retrieved
from devagent.agents.state import AgentState, PendingWrite, ToolCallTrace
from devagent.config import TRACE_DIR
from devagent.llm import get_llm
from devagent.prompts.loader import load_prompt
from devagent.tools.registry import (
    get_tool,
    is_write_tool,
    run_tool,
    tool_schema_json,
)

MAX_EXECUTOR_ITERATIONS = 5


def _append_jsonl(thread_id: str, trace: ToolCallTrace) -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    with (TRACE_DIR / f"{thread_id}.jsonl").open("a") as fh:
        fh.write(json.dumps(trace.model_dump()) + "\n")


def _resolve_write_args(state: AgentState, step) -> dict:
    """Draft concrete write-tool arguments from gathered context via the LLM."""
    spec = get_tool(step.tool_name)
    prompt = load_prompt(
        "executor",
        version=state.prompt_version,
        repo=state.repo,
        step_description=step.description,
        tool_name=step.tool_name,
        tool_schema=tool_schema_json(step.tool_name),
        context=format_retrieved(state),
    )
    try:
        drafted = get_llm().with_structured_output(spec.input_model).invoke(prompt)
        args = drafted.model_dump()
    except Exception:  # noqa: BLE001 — fall back to the planner's raw args
        args = dict(step.tool_args)
    args["repo"] = state.repo
    return args


def execute_node(state: AgentState) -> dict:
    tool_steps = [s for s in state.plan if s.action == "tool"][:MAX_EXECUTOR_ITERATIONS]
    traces: list[ToolCallTrace] = list(state.tool_calls)
    pending_write: PendingWrite | None = None

    for step in tool_steps:
        name = step.tool_name or ""
        try:
            get_tool(name)
        except KeyError:
            traces.append(
                ToolCallTrace(
                    step_index=step.index,
                    tool_name=name or "(unknown)",
                    input=step.tool_args,
                    output_summary=f"unknown tool {name!r} — skipped",
                    ok=False,
                    latency_ms=0.0,
                )
            )
            continue

        if is_write_tool(name):
            # Suspend: draft args, hand to the confirmation gate. One write per plan.
            # 'proposed' is logged here (not in the gate node) because the gate
            # re-executes on interrupt-resume and would double-log.
            from devagent.audit import log_action

            args = _resolve_write_args(state, step)
            pending_write = PendingWrite(
                tool_name=name, args=args, description=step.description
            )
            log_action(
                thread_id=state.thread_id,
                repo=state.repo,
                action=name,
                params=args,
                status="proposed",
            )
            break

        args = {**step.tool_args, "repo": state.repo}
        _result, trace = run_tool(name, args, step_index=step.index)
        traces.append(trace)
        _append_jsonl(state.thread_id, trace)

    return {"tool_calls": traces, "pending_write": pending_write}
