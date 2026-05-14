"""Retriever node — fills the state with context from the hybrid RAG layer.

Runs once per query: retrieves for the main query plus each 'retrieve' plan
step's description, de-duplicates by citation, and caps the context so the
synthesizer prompt stays bounded.
"""

from __future__ import annotations

from devagent.agents.state import AgentState
from devagent.rag.hybrid_retriever import HybridRetriever

PER_QUERY_TOP_K = 6
MAX_CONTEXT_CHUNKS = 12


def retrieve_node(state: AgentState) -> dict:
    retrieve_steps = [s for s in state.plan if s.action == "retrieve"]
    if not retrieve_steps:
        return {"retrieved": []}

    retriever = HybridRetriever()
    queries = [state.query] + [
        s.description for s in retrieve_steps if s.description.strip()
    ]

    seen: dict[str, dict] = {}
    for query in queries:
        for chunk in retriever.retrieve(query, top_k=PER_QUERY_TOP_K, repo=state.repo):
            key = chunk.citation + "|" + chunk.text[:80]
            if key in seen:
                continue
            seen[key] = {
                "text": chunk.text,
                "source_type": chunk.source_type,
                "citation": chunk.citation,
                "score": round(chunk.score, 5),
                "metadata": chunk.metadata,
            }

    ranked = sorted(seen.values(), key=lambda c: c["score"], reverse=True)
    return {"retrieved": ranked[:MAX_CONTEXT_CHUNKS]}
