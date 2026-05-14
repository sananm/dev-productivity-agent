"""End-to-end ingestion: fetch -> chunk -> embed -> load into pgvector.

The vector store is created with hybrid_search enabled so Phase 2's BM25 + dense
retrieval can run against the same table. The HNSW index is built only after the
load completes (devagent.db.migrate.create_vector_index).
"""

from __future__ import annotations

import datetime as dt
from urllib.parse import urlparse

from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.schema import TextNode
from llama_index.vector_stores.postgres import PGVectorStore

from devagent.config import get_settings
from devagent.db import migrate
from devagent.embeddings import get_embedder
from devagent.ingestion import fetchers
from devagent.ingestion.chunkers import chunk
from devagent.ingestion.github_client import get_github_client

VECTOR_TABLE = "vector_nodes"  # PGVectorStore stores it as data_vector_nodes

SOURCE_FETCHERS = {
    "code": fetchers.fetch_code,
    "doc": fetchers.fetch_docs,
    "issue": fetchers.fetch_issues,
    "commit": fetchers.fetch_commits,
}


def _vector_store() -> PGVectorStore:
    settings = get_settings()
    url = urlparse(settings.database_url)
    return PGVectorStore.from_params(
        database=url.path.lstrip("/"),
        host=url.hostname,
        password=url.password,
        port=url.port or 5432,
        user=url.username,
        table_name=VECTOR_TABLE,
        embed_dim=settings.embedding_dim,
        hybrid_search=True,
        text_search_config="english",
        hnsw_kwargs=None,  # index built post-load, not here
    )


def _clear_source(repo: str, source_type: str) -> None:
    """Drop existing rows for a repo+source so re-ingest is idempotent."""
    from devagent.db.migrate import VECTOR_TABLE, vector_table_exists
    from devagent.db.session import execute

    if not vector_table_exists():
        return
    execute(
        f"DELETE FROM {VECTOR_TABLE} "
        f"WHERE metadata_->>'repo' = %s AND metadata_->>'source_type' = %s",
        (repo, source_type),
    )


def _embed_nodes(nodes: list[TextNode], embedder: BaseEmbedding) -> list[TextNode]:
    texts = [n.get_content(metadata_mode="none") for n in nodes]
    embeddings = embedder.get_text_embedding_batch(texts, show_progress=False)
    for node, emb in zip(nodes, embeddings):
        node.embedding = emb
    return nodes


def ingest_repo(
    repo: str,
    *,
    source_types: list[str] | None = None,
    build_index: bool = True,
) -> dict[str, int]:
    """Ingest a repo (or a subset of source types) into pgvector.

    Returns a count of nodes loaded per source type.
    """
    source_types = source_types or list(SOURCE_FETCHERS)
    indexed_at = dt.datetime.now(dt.timezone.utc).isoformat()

    store = _vector_store()
    embedder = get_embedder()
    counts: dict[str, int] = {}

    with get_github_client() as client:
        for source_type in source_types:
            fetch_fn = SOURCE_FETCHERS[source_type]
            nodes: list[TextNode] = []
            for raw in fetch_fn(client, repo):
                for node in chunk(raw):
                    node.metadata["last_indexed_at"] = indexed_at
                    nodes.append(node)
            if not nodes:
                counts[source_type] = 0
                continue
            _embed_nodes(nodes, embedder)
            _clear_source(repo, source_type)
            store.add(nodes)
            counts[source_type] = len(nodes)
            print(f"[ingest] {source_type}: {len(nodes)} chunks loaded")

    if build_index:
        migrate.create_vector_index()

    total = sum(counts.values())
    print(f"[ingest] done — {total} chunks from {repo}")
    return counts
