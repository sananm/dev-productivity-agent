"""Deterministic mock LLM for wiring tests and CI.

Selected via LLM_BACKEND=mock. It constructs without any server or API key and
returns a canned response — enough to exercise import paths and non-agent code
without a real model. It is not intended to drive the full agent graph (which
needs genuine structured-output reasoning).
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel


def build_mock_llm() -> BaseChatModel:
    return FakeListChatModel(responses=["mock-llm response"])
