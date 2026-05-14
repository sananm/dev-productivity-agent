"""Central configuration loaded from environment / .env.

The platform runs fully offline by default: a local Ollama LLM, local
sentence-transformer embeddings, and bundled GitHub fixtures. Each of these is a
pluggable backend — set the corresponding *_BACKEND / GITHUB_MODE to switch to
the OpenAI API or the live GitHub API without code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".github_cache"
TRACE_DIR = PROJECT_ROOT / "traces"
FIXTURES_DIR = PROJECT_ROOT / "fixtures"

LLMBackend = Literal["ollama", "openai", "mock"]
EmbeddingBackend = Literal["local", "openai"]
GitHubMode = Literal["fixtures", "live"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- backends (offline-first defaults) -------------------------------
    llm_backend: LLMBackend = Field(default="ollama", alias="LLM_BACKEND")
    embedding_backend: EmbeddingBackend = Field(default="local", alias="EMBEDDING_BACKEND")
    github_mode: GitHubMode = Field(default="fixtures", alias="GITHUB_MODE")

    # --- Ollama (default LLM) --------------------------------------------
    ollama_model: str = Field(default="qwen2.5:7b-instruct", alias="OLLAMA_MODEL")
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")

    # --- eval judge (LLM-as-judge for the eval harness) ------------------
    # LLM-judged metrics need a capable model. Defaults to the agent's own LLM,
    # but a stronger judge (e.g. a larger Ollama model, or OpenAI) gives more
    # reliable task-completion / faithfulness scores. Empty = use the main LLM.
    eval_judge_model: str = Field(default="", alias="EVAL_JUDGE_MODEL")

    # --- OpenAI (optional LLM + embedding backend) -----------------------
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_llm_model: str = Field(default="gpt-4o", alias="OPENAI_LLM_MODEL")
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", alias="OPENAI_EMBEDDING_MODEL"
    )

    # --- local embeddings (default) --------------------------------------
    local_embedding_model: str = Field(
        default="BAAI/bge-small-en-v1.5", alias="LOCAL_EMBEDDING_MODEL"
    )
    # Vector dim must match the active embedding backend. 384 = bge-small;
    # set to 1536 when EMBEDDING_BACKEND=openai (text-embedding-3-small).
    embedding_dim: int = Field(default=384, alias="EMBEDDING_DIM")

    # --- GitHub (live mode only) -----------------------------------------
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    # --- infra -----------------------------------------------------------
    database_url: str = Field(
        default="postgresql://devagent:devagent@localhost:5432/devagent",
        alias="DATABASE_URL",
    )
    default_repo: str = Field(default="psf/requests", alias="DEFAULT_REPO")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")

    # --- observability (optional) ----------------------------------------
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def require_openai(self) -> str:
        if not self.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set but an OpenAI backend is selected — "
                "set it in .env or switch back to the offline defaults."
            )
        return self.openai_api_key

    def require_github(self) -> str:
        if not self.github_token:
            raise RuntimeError(
                "GITHUB_TOKEN is not set but GITHUB_MODE=live — set it in .env "
                "or use GITHUB_MODE=fixtures (the default)."
            )
        return self.github_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
