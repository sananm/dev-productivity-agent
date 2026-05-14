"""LangGraph StateGraph wiring the planner/retriever/executor/synthesizer agents.

    START -> plan -> retrieve -> execute --+--(pending_write)--> confirm_gate
                                           |                         |
                                           |                    write_executor
                                           |                         |
                                           +--(no write)----------> synthesize -> END

Every edge passes the typed AgentState. The confirmation gate uses interrupt(),
so PostgresSaver checkpointing must be live for the HITL flow to suspend/resume.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from devagent.agents.executor import execute_node
from devagent.agents.planner import plan_node
from devagent.agents.retriever_node import retrieve_node
from devagent.agents.state import AgentState
from devagent.agents.synthesizer import synthesize_node
from devagent.agents.write_gate import confirm_gate_node, write_executor_node


def _route_after_execute(state: AgentState) -> str:
    return "confirm_gate" if state.pending_write else "synthesize"


def build_graph(checkpointer=None):
    """Build and compile the agent graph.

    A checkpointer (PostgresSaver) is required for the write-confirmation
    interrupt to suspend and resume across requests; pass None only for
    read-only flows that never hit a write step.
    """
    graph = StateGraph(AgentState)

    graph.add_node("plan", plan_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("execute", execute_node)
    graph.add_node("confirm_gate", confirm_gate_node)
    graph.add_node("write_executor", write_executor_node)
    graph.add_node("synthesize", synthesize_node)

    graph.add_edge(START, "plan")
    graph.add_edge("plan", "retrieve")
    graph.add_edge("retrieve", "execute")
    graph.add_conditional_edges(
        "execute",
        _route_after_execute,
        {"confirm_gate": "confirm_gate", "synthesize": "synthesize"},
    )
    graph.add_edge("confirm_gate", "write_executor")
    graph.add_edge("write_executor", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile(checkpointer=checkpointer)
