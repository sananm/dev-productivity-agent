"""Shared FastAPI dependencies — the checkpointer pool and the compiled graph.

The graph is compiled once per process with a PostgresSaver over a long-lived
connection pool, so write-confirmation interrupts persist across requests.
"""

from __future__ import annotations

from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from devagent.config import get_settings


@lru_cache(maxsize=1)
def get_checkpointer_pool() -> ConnectionPool:
    # PostgresSaver requires autocommit connections with dict_row.
    return ConnectionPool(
        conninfo=get_settings().database_url,
        min_size=1,
        max_size=8,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )


# The agent state nests our own Pydantic models; the checkpoint serializer must
# be told they are safe to (de)serialize across process restarts.
_ALLOWED_STATE_TYPES = [
    ("devagent.agents.state", "AgentState"),
    ("devagent.agents.state", "Plan"),
    ("devagent.agents.state", "PlanStep"),
    ("devagent.agents.state", "ToolCallTrace"),
    ("devagent.agents.state", "PendingWrite"),
]


@lru_cache(maxsize=1)
def get_graph():
    from langgraph.checkpoint.postgres import PostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    from devagent.agents.graph import build_graph

    serde = JsonPlusSerializer(allowed_msgpack_modules=_ALLOWED_STATE_TYPES)
    saver = PostgresSaver(get_checkpointer_pool(), serde=serde)
    return build_graph(checkpointer=saver)
