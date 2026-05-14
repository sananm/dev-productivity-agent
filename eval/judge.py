"""DeepEval judge model — the LLM-as-judge for task-completion / faithfulness.

DeepEval's LLM-judged metrics default to the OpenAI API. This wrapper points
them at a local/offline model instead. The judge model is configurable
independently of the agent LLM (EVAL_JUDGE_MODEL) because judging needs a
capable model — a small agent model makes a poor judge. When EVAL_JUDGE_MODEL
is unset, the agent's own LLM is used.
"""

from __future__ import annotations

from deepeval.models import DeepEvalBaseLLM
from pydantic import BaseModel

from devagent.config import get_settings
from devagent.llm import get_llm


def _build_judge_llm():
    settings = get_settings()
    if settings.eval_judge_model and settings.llm_backend == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.eval_judge_model,
            base_url=settings.ollama_host,
            temperature=0.0,
        )
    # fall back to the agent's configured LLM
    return get_llm(temperature=0.0)


def judge_label() -> str:
    settings = get_settings()
    if settings.eval_judge_model and settings.llm_backend == "ollama":
        return f"ollama:{settings.eval_judge_model}"
    from devagent.llm import llm_label

    return llm_label()


class LocalJudge(DeepEvalBaseLLM):
    def __init__(self) -> None:
        self._llm = _build_judge_llm()
        self._label = judge_label()

    def load_model(self):
        return self._llm

    def generate(self, prompt: str, schema: type[BaseModel] | None = None):
        if schema is not None:
            return self._llm.with_structured_output(schema).invoke(prompt)
        resp = self._llm.invoke(prompt)
        return resp.content if hasattr(resp, "content") else str(resp)

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None):
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return f"local-judge ({self._label})"
