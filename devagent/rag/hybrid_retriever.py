"""Hybrid retriever: BM25 + dense vector retrieval fused with Reciprocal Rank Fusion.

Pipeline per query:
  1. route   — pick which of the 4 source types (code/doc/issue/commit) to search
  2. dense   — cosine similarity over the embedding column
  3. sparse  — Okapi BM25 over chunk text
  4. fuse    — RRF merges the two ranked lists (rank-based, score-scale agnostic)
  5. fresh   — for freshness-sensitive issue queries, merge in live GitHub state

Every returned chunk carries a citation (file:line / #issue / commit SHA).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from devagent.config import get_settings
from devagent.embeddings import get_embedder
from devagent.rag.corpus import Chunk, bm25_search, dense_search

ALL_SOURCES = ("code", "doc", "issue", "commit")

# RRF constant. Lower k weights top ranks more heavily; 60 is the canonical
# default and works well for this portfolio-scale corpus.
RRF_K = 60

_FRESHNESS_SIGNALS = re.compile(
    r"\b(open|current|currently|latest|recent|recently|now|today|still)\b", re.I
)
# Prefix matches (leading \b, no trailing \b) so inflections route too:
# "class" matches "classes", "defin" matches "define"/"defined".
_ROUTING_SIGNALS = {
    "issue": re.compile(
        r"\b(issue|pr\b|prs\b|pull request|triage|label|bug report|good first)", re.I
    ),
    "commit": re.compile(
        r"\b(commit|changed|change log|changelog|history|last modified|"
        r"who modified|who changed)",
        re.I,
    ),
    "doc": re.compile(r"\b(documentation|readme|guide|quickstart|tutorial)", re.I),
    "code": re.compile(
        r"\b(function|class|method|implement|defin|where is|module|handler|"
        r"logic|exception|header|parameter|attribute|variable)",
        re.I,
    ),
}


@dataclass
class RetrievedChunk:
    text: str
    score: float
    source_type: str
    citation: str
    metadata: dict

    @classmethod
    def from_chunk(cls, chunk: Chunk, score: float) -> "RetrievedChunk":
        return cls(
            text=chunk.text,
            score=score,
            source_type=chunk.source_type,
            citation=chunk.citation(),
            metadata=chunk.metadata,
        )


def route_sources(query: str) -> tuple[str, ...]:
    """Heuristically pick source types to search. Deterministic — eval-friendly."""
    matched = tuple(st for st, pat in _ROUTING_SIGNALS.items() if pat.search(query))
    # A query that hits multiple signals (cross-source) or none falls back to all.
    if len(matched) == 1:
        # still include code as a baseline unless the query is clearly issue/commit-only
        if matched[0] in ("issue", "commit"):
            return matched
        return matched
    return ALL_SOURCES


def _rrf_fuse(
    ranked_lists: list[list[tuple[Chunk, float]]], top_k: int
) -> list[tuple[Chunk, float]]:
    """Reciprocal Rank Fusion over multiple ranked lists, keyed by node_id."""
    fused: dict[str, float] = {}
    chunks: dict[str, Chunk] = {}
    for ranked in ranked_lists:
        for rank, (chunk, _score) in enumerate(ranked):
            fused[chunk.node_id] = fused.get(chunk.node_id, 0.0) + 1.0 / (RRF_K + rank)
            chunks[chunk.node_id] = chunk
    ordered = sorted(fused.items(), key=lambda kv: kv[1], reverse=True)
    return [(chunks[nid], score) for nid, score in ordered[:top_k]]


def _fresh_issue_chunks(repo: str, limit: int) -> list[tuple[Chunk, float]]:
    """Pull live issue/PR state and adapt it to Chunks (freshness fallback)."""
    from devagent.ingestion.github_client import get_github_client

    out: list[tuple[Chunk, float]] = []
    with get_github_client() as gh:
        items = list(
            gh.paginate(
                f"/repos/{repo}/issues", params={"state": "open", "sort": "updated"},
                max_items=limit,
            )
        )
    for item in items:
        number = item["number"]
        is_pr = "pull_request" in item
        text = (
            f"{'PR' if is_pr else 'Issue'} #{number}: {item['title']}\n"
            f"State: {item['state']}\n\n{item.get('body') or ''}"
        )
        meta = {
            "repo": repo,
            "source_type": "issue",
            "issue_number": number,
            "is_pr": is_pr,
            "state": item["state"],
            "fresh": True,
        }
        out.append((Chunk(node_id=f"fresh-issue-{number}", text=text, metadata=meta), 1.0))
    return out


class HybridRetriever:
    """BM25 + dense retrieval with RRF fusion. The retriever agent's context source."""

    def __init__(self, *, candidate_multiplier: int = 4) -> None:
        self._embedder = get_embedder()
        self._candidate_multiplier = candidate_multiplier

    def retrieve(
        self,
        query: str,
        *,
        top_k: int = 5,
        source_types: tuple[str, ...] | None = None,
        repo: str | None = None,
        allow_fresh: bool = True,
    ) -> list[RetrievedChunk]:
        sources = source_types or route_sources(query)
        n_candidates = top_k * self._candidate_multiplier

        query_embedding = self._embedder.get_query_embedding(query)
        dense = dense_search(query_embedding, n_candidates, sources)
        sparse = bm25_search(query, n_candidates, sources)

        ranked_lists = [dense, sparse]

        if (
            allow_fresh
            and "issue" in sources
            and _FRESHNESS_SIGNALS.search(query)
        ):
            repo = repo or get_settings().default_repo
            # Only inject issues missing from the index — i.e. opened/updated
            # since the last ingest. Re-surfacing already-indexed issues would
            # just duplicate candidates.
            indexed_issue_numbers = {
                c.metadata.get("issue_number")
                for c, _ in (*dense, *sparse)
                if c.source_type == "issue"
            }
            fresh = [
                (c, s)
                for c, s in _fresh_issue_chunks(repo, n_candidates)
                if c.metadata.get("issue_number") not in indexed_issue_numbers
            ]
            if fresh:
                ranked_lists.append(fresh)

        fused = _rrf_fuse(ranked_lists, top_k)
        return [RetrievedChunk.from_chunk(c, s) for c, s in fused]
