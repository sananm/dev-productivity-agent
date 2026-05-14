"""Central configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = PROJECT_ROOT / ".github_cache"
TRACE_DIR = PROJECT_ROOT / "traces"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    database_url: str = Field(
        default="postgresql://devagent:devagent@localhost:5432/devagent",
        alias="DATABASE_URL",
    )

    llm_model: str = Field(default="gpt-4o", alias="LLM_MODEL")
    embedding_model: str = Field(default="text-embedding-3-small", alias="EMBEDDING_MODEL")
    embedding_dim: int = Field(default=1536, alias="EMBEDDING_DIM")

    default_repo: str = Field(default="psf/requests", alias="DEFAULT_REPO")
    api_base_url: str = Field(default="http://localhost:8000", alias="API_BASE_URL")

    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="http://localhost:3000", alias="LANGFUSE_HOST")

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    def require_openai(self) -> str:
        if not self.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set — copy .env.example to .env and fill it in.")
        return self.openai_api_key

    def require_github(self) -> str:
        if not self.github_token:
            raise RuntimeError("GITHUB_TOKEN is not set — copy .env.example to .env and fill it in.")
        return self.github_token


@lru_cache
def get_settings() -> Settings:
    return Settings()
