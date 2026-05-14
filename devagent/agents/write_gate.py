"""Confirmation gate + write executor — the human-in-the-loop boundary.

confirm_gate_node calls LangGraph's interrupt(): the graph suspends, PostgresSaver
checkpoints the full state, and the FastAPI layer returns the pending write to
the user. A later POST /confirm resumes the graph with the decision.

write_executor_node runs only after a decision exists. It honours --dry-run
(prints the exact call, executes nothing) and records every transition to the
append-only audit log.
"""

from __future__ import annotations

from langgraph.types import interrupt

from devagent.agents.executor import _append_jsonl
from devagent.agents.state import AgentState
from devagent.audit import log_action
from devagent.tools.registry import run_tool


def confirm_gate_node(state: AgentState) -> dict:
    """Suspend the graph until the user approves or rejects the pending write.

    This node has no side effects before interrupt() — it re-executes on resume,
    and side effects there would run twice. ('proposed' is logged by the executor.)
    """
    pw = state.pending_write
    decision = interrupt(
        {
            "tool_name": pw.tool_name,
            "args": pw.args,
            "description": pw.description,
        }
    )
    normalized = "approved" if str(decision).lower() in ("approved", "approve", "y", "yes") else "rejected"
    return {"write_decision": normalized}


def write_executor_node(state: AgentState) -> dict:
    pw = state.pending_write
    common = dict(thread_id=state.thread_id, repo=state.repo, action=pw.tool_name, params=pw.args)

    if state.write_decision != "approved":
        log_action(**common, status="rejected")
        return {
            "write_result": {
                "status": "rejected",
                "summary": f"Write action '{pw.tool_name}' was rejected — no changes made.",
            }
        }

    log_action(**common, status="confirmed")

    if state.dry_run:
        result = {
            "status": "dry_run",
            "summary": f"[dry-run] would call {pw.tool_name}({pw.args})",
            "args": pw.args,
        }
        log_action(**common, status="dry_run", result=result)
        return {"write_result": result}

    tool_result, trace = run_tool(pw.tool_name, pw.args, step_index=-1)
    _append_jsonl(state.thread_id, trace)
    log_action(
        **common,
        status="executed" if tool_result.ok else "error",
        result=tool_result.data or {"summary": tool_result.summary},
    )
    return {
        "write_result": {
            "status": "executed" if tool_result.ok else "error",
            "summary": tool_result.summary,
            "data": tool_result.data,
            "citation": tool_result.citation,
        },
        "tool_calls": [*state.tool_calls, trace],
    }
