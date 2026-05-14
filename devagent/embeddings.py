"""Pluggable embedding provider.

Default backend is a local sentence-transformer (BAAI/bge-small-en-v1.5, 384-dim)
— offline, no API keys. Set EMBEDDING_BACKEND=openai (and EMBEDDING_DIM=1536) to
use the OpenAI embedding API instead. The vector table dim must match whatever
backend was active at ingest time.
"""

from __future__ import annotations

from functools import lru_cache

from llama_index.core.base.embeddings.base import BaseEmbedding

from devagent.config import get_settings


@lru_cache
def get_embedder() -> BaseEmbedding:
    """Return the embedding model for the configured backend (cached — models are heavy)."""
    settings = get_settings()
    backend = settings.embedding_backend

    if backend == "local":
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding

        return HuggingFaceEmbedding(model_name=settings.local_embedding_model)

    if backend == "openai":
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model=settings.openai_embedding_model,
            api_key=settings.require_openai(),
            embed_batch_size=100,
        )

    raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend!r}")


def embedding_label() -> str:
    settings = get_settings()
    if settings.embedding_backend == "local":
        return f"local:{settings.local_embedding_model}"
    return f"openai:{settings.openai_embedding_model}"
