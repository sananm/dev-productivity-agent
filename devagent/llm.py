"""Pluggable LLM provider.

Default backend is a local Ollama model — fully offline, no API keys. Set
LLM_BACKEND=openai to use the OpenAI API instead, or LLM_BACKEND=mock for
deterministic wiring tests. Every agent node calls get_llm(); nothing else in
the codebase knows which backend is active.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from devagent.config import get_settings


def get_llm(*, temperature: float = 0.0, **kwargs) -> BaseChatModel:
    """Return a chat model for the configured backend.

    temperature=0.0 by default — the agents and eval harness need determinism.
    """
    settings = get_settings()
    backend = settings.llm_backend

    if backend == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_host,
            temperature=temperature,
            **kwargs,
        )

    if backend == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.openai_llm_model,
            api_key=settings.require_openai(),
            temperature=temperature,
            **kwargs,
        )

    if backend == "mock":
        from devagent.testing.mock_llm import build_mock_llm

        return build_mock_llm()

    raise ValueError(f"Unknown LLM_BACKEND: {backend!r}")


@lru_cache
def llm_label() -> str:
    """Human-readable identifier of the active LLM, for traces and CLI output."""
    settings = get_settings()
    if settings.llm_backend == "ollama":
        return f"ollama:{settings.ollama_model}"
    if settings.llm_backend == "openai":
        return f"openai:{settings.openai_llm_model}"
    return "mock"
