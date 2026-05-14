"""Langfuse tracing — optional, self-hosted observability for every agent run.

When LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY are set, the FastAPI layer attaches
a Langfuse callback handler to the graph invocation, so every node (planner,
retriever, executor, synthesizer) and LLM call shows up as a span in the
self-hosted Langfuse UI. When the keys are absent the handler is None and the
agent runs untraced — tracing is purely additive.
"""

from __future__ import annotations

from functools import lru_cache

from devagent.config import get_settings


@lru_cache(maxsize=1)
def get_langfuse_handler():
    """Return a Langfuse LangChain callback handler, or None if not configured."""
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    try:
        from langfuse.callback import CallbackHandler

        return CallbackHandler(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception as exc:  # noqa: BLE001 — tracing must never break the agent
        print(f"[langfuse] tracing disabled — handler init failed: {exc}")
        return None


def trace_callbacks() -> list:
    """Callback list to merge into a graph invocation config (empty if disabled)."""
    handler = get_langfuse_handler()
    return [handler] if handler is not None else []
