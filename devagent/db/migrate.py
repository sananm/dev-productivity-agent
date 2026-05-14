"""Apply the core schema and manage the deferred HNSW vector index.

Run directly:  python -m devagent.db.migrate
"""

from __future__ import annotations

from pathlib import Path

from devagent.db.session import execute, fetch_one, get_conn

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# LlamaIndex PGVectorStore prefixes the configured table name with "data_".
VECTOR_TABLE = "data_vector_nodes"


def apply_schema() -> None:
    """Create the pgvector extension, eval tables, and audit log."""
    sql = SCHEMA_PATH.read_text()
    with get_conn() as conn:
        conn.execute(sql)
        conn.commit()
    print("[migrate] schema applied (extension, eval_cases, eval_results, audit_log)")


def setup_checkpointer() -> None:
    """Create LangGraph PostgresSaver checkpoint tables if not present."""
    from langgraph.checkpoint.postgres import PostgresSaver

    from devagent.config import get_settings

    with PostgresSaver.from_conn_string(get_settings().database_url) as saver:
        saver.setup()
    print("[migrate] langgraph checkpoint tables ready")


def vector_table_exists() -> bool:
    row = fetch_one(
        "SELECT to_regclass(%s) AS t",
        (f"public.{VECTOR_TABLE}",),
    )
    return bool(row and row["t"])


def create_vector_index() -> None:
    """Create the HNSW index on the embedding column.

    Called AFTER initial data load (end of the ingestion pipeline), never at
    schema-init time — building HNSW on an empty/loading table risks OOM.
    """
    if not vector_table_exists():
        print(f"[migrate] {VECTOR_TABLE} does not exist yet — run `devagent index` first")
        return
    execute(
        f"CREATE INDEX IF NOT EXISTS idx_{VECTOR_TABLE}_embedding "
        f"ON {VECTOR_TABLE} USING hnsw (embedding vector_cosine_ops) "
        f"WITH (m = 16, ef_construction = 64)"
    )
    print(f"[migrate] HNSW index ready on {VECTOR_TABLE}.embedding")


def main() -> None:
    apply_schema()
    setup_checkpointer()
    if vector_table_exists():
        create_vector_index()
    print("[migrate] done")


if __name__ == "__main__":
    main()
