"""FastAPI service exposing the agent graph.

  POST /query    submit a query — SSE stream of plan -> status -> answer tokens
                 -> done, OR -> needs_confirmation if a write action is proposed
  POST /confirm  resume a suspended graph with the user's approve/reject decision
  GET  /health   backend status

The CLI (Phase 4) is a pure HTTP client against these endpoints.
"""

from __future__ import annotations

import json
import uuid

from fastapi import FastAPI
from langgraph.types import Command
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from devagent.api.dependencies import get_graph
from devagent.config import get_settings
from devagent.embeddings import embedding_label
from devagent.llm import llm_label

app = FastAPI(title="Developer Productivity Agent", version="0.1.0")


class QueryRequest(BaseModel):
    query: str
    repo: str | None = None
    dry_run: bool = False
    prompt_version: str = "v1"


class ConfirmRequest(BaseModel):
    thread_id: str
    decision: str  # approved | rejected


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "llm": llm_label(),
        "embedding": embedding_label(),
        "github_mode": s.github_mode,
        "default_repo": s.default_repo,
    }


def _sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data)}


def _dump(obj):
    return obj.model_dump() if hasattr(obj, "model_dump") else obj


def _state_values(state) -> dict:
    vals = state.values
    return vals.model_dump() if hasattr(vals, "model_dump") else dict(vals)


def _run_stream(stream_input, config):
    """Sync generator: drive the graph stream and yield SSE event dicts."""
    graph = get_graph()
    thread_id = config["configurable"]["thread_id"]
    try:
        for mode, chunk in graph.stream(
            stream_input, config, stream_mode=["updates", "messages"]
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    if node == "__interrupt__" or not isinstance(update, dict):
                        continue
                    if node == "plan" and update.get("plan"):
                        yield _sse(
                            "plan",
                            {
                                "reasoning": update.get("planner_reasoning", ""),
                                "steps": [_dump(s) for s in update["plan"]],
                            },
                        )
                    elif node == "retrieve":
                        yield _sse(
                            "status",
                            {"stage": "retrieving", "count": len(update.get("retrieved", []))},
                        )
                    elif node == "execute":
                        yield _sse(
                            "status",
                            {
                                "stage": "executing",
                                "tool_calls": [_dump(t) for t in update.get("tool_calls", [])],
                            },
                        )
                    elif node == "write_executor":
                        yield _sse(
                            "status",
                            {"stage": "write", "result": update.get("write_result")},
                        )
            elif mode == "messages":
                msg, meta = chunk
                if meta.get("langgraph_node") == "synthesize":
                    token = getattr(msg, "content", "") or ""
                    if token:
                        yield _sse("token", {"text": token})

        # Stream drained — either suspended at the gate or finished.
        state = graph.get_state(config)
        interrupts = [i for task in state.tasks for i in task.interrupts]
        if interrupts:
            yield _sse(
                "needs_confirmation",
                {"thread_id": thread_id, "pending_write": interrupts[0].value},
            )
        else:
            vals = _state_values(state)
            yield _sse(
                "done",
                {
                    "thread_id": thread_id,
                    "answer": vals.get("answer", ""),
                    "citations": vals.get("citations", []),
                    "tool_calls": [_dump(t) for t in vals.get("tool_calls", [])],
                    "write_result": vals.get("write_result"),
                    "error": vals.get("error"),
                },
            )
    except Exception as exc:  # noqa: BLE001 — surface failures to the client
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})


@app.post("/query")
def query(req: QueryRequest) -> EventSourceResponse:
    settings = get_settings()
    thread_id = uuid.uuid4().hex
    config = {"configurable": {"thread_id": thread_id}}
    stream_input = {
        "query": req.query,
        "repo": req.repo or settings.default_repo,
        "thread_id": thread_id,
        "dry_run": req.dry_run,
        "prompt_version": req.prompt_version,
    }

    def gen():
        yield _sse("thread", {"thread_id": thread_id})
        yield from _run_stream(stream_input, config)

    return EventSourceResponse(gen())


@app.post("/confirm")
def confirm(req: ConfirmRequest) -> EventSourceResponse:
    config = {"configurable": {"thread_id": req.thread_id}}
    decision = "approved" if req.decision.lower() in ("approved", "approve", "y", "yes") else "rejected"

    def gen():
        yield _sse("thread", {"thread_id": req.thread_id})
        yield from _run_stream(Command(resume=decision), config)

    return EventSourceResponse(gen())
