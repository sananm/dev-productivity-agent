"""Corpus access for hybrid retrieval.

Two retrieval primitives over the pgvector table:
  - dense_search: cosine similarity on the embedding column (HNSW-indexed)
  - the BM25 index: true Okapi BM25 over chunk text, built in-memory and cached

The corpus is portfolio-scale (hundreds–low-thousands of chunks), so an
in-memory BM25 index is the simplest honest implementation. At larger scale the
sparse side would move to Postgres full-text search; the HybridRetriever
interface would not change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from rank_bm25 import BM25Okapi

from devagent.db.migrate import VECTOR_TABLE
from devagent.db.session import fetch_all

# Underscores are token boundaries: this splits snake_case identifiers
# (default_headers -> default, headers) so natural-language queries match code.
_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class Chunk:
    node_id: str
    text: str
    metadata: dict

    @property
    def source_type(self) -> str:
        return self.metadata.get("source_type", "unknown")

    def citation(self) -> str:
        """file:line / #issue / commit SHA for this chunk's origin."""
        m = self.metadata
        st = self.source_type
        if st == "code":
            path = m.get("file_path", "?")
            start, end = m.get("line_start"), m.get("line_end")
            return f"{path}:{start}-{end}" if start else path
        if st == "doc":
            return m.get("file_path", "?")
        if st == "issue":
            return f"#{m['issue_number']}" if m.get("issue_number") else "issue"
        if st == "commit":
            sha = m.get("commit_sha", "")
            return sha[:10] if sha else "commit"
        return st


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


@lru_cache(maxsize=1)
def load_corpus() -> tuple[Chunk, ...]:
    """All chunks in the vector table (cached for the process lifetime)."""
    rows = fetch_all(
        f"SELECT node_id, text, metadata_ FROM {VECTOR_TABLE} ORDER BY node_id"
    )
    return tuple(Chunk(r["node_id"], r["text"], r["metadata_"]) for r in rows)


@lru_cache(maxsize=1)
def _bm25_index() -> tuple[BM25Okapi, tuple[Chunk, ...]]:
    corpus = load_corpus()
    tokenized = [_tokenize(c.text) for c in corpus]
    return BM25Okapi(tokenized), corpus


def bm25_search(
    query: str, k: int, source_types: tuple[str, ...] | None = None
) -> list[tuple[Chunk, float]]:
    """Top-k chunks by Okapi BM25 score, optionally restricted by source type."""
    bm25, corpus = _bm25_index()
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(corpus, scores), key=lambda cs: cs[1], reverse=True)
    if source_types:
        ranked = [cs for cs in ranked if cs[0].source_type in source_types]
    return ranked[:k]


def _vector_literal(embedding: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in embedding) + "]"


def dense_search(
    query_embedding: list[float], k: int, source_types: tuple[str, ...] | None = None
) -> list[tuple[Chunk, float]]:
    """Top-k chunks by cosine similarity on the HNSW-indexed embedding column."""
    vec = _vector_literal(query_embedding)
    sql = (
        f"SELECT node_id, text, metadata_, "
        f"1 - (embedding <=> %s::vector) AS score "
        f"FROM {VECTOR_TABLE} "
    )
    params: list = [vec]
    if source_types:
        sql += "WHERE metadata_->>'source_type' = ANY(%s) "
        params.append(list(source_types))
    sql += "ORDER BY embedding <=> %s::vector LIMIT %s"
    params += [vec, k]
    rows = fetch_all(sql, tuple(params))
    return [
        (Chunk(r["node_id"], r["text"], r["metadata_"]), float(r["score"]))
        for r in rows
    ]


def reset_caches() -> None:
    """Drop cached corpus/BM25 index — call after re-ingestion."""
    load_corpus.cache_clear()
    _bm25_index.cache_clear()
