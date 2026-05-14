"""MCP-style declarative tool definitions.

Every GitHub capability is exposed as a ``ToolSpec``: a name, a description, a
typed Pydantic input model, an output model, whether it mutates state, and the
callable that runs it. The agent executor binds the registry; the planner sees
only names + descriptions + input schemas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field

# --- read inputs ---------------------------------------------------------


class FetchFileInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    path: str = Field(description="file path within the repo")
    ref: str | None = Field(default=None, description="branch, tag, or commit SHA")


class SearchCodeInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    query: str = Field(description="keyword or symbol to search for in code")
    max_results: int = Field(default=10, ge=1, le=50)


class ListIssuesInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    state: str = Field(default="open", description="open | closed | all")
    labels: str | None = Field(default=None, description="comma-separated label filter")
    max_results: int = Field(default=20, ge=1, le=100)


class GetPRDiffInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    number: int = Field(description="pull request number")


class ListCommitsInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    path: str | None = Field(default=None, description="restrict history to this file path")
    max_results: int = Field(default=20, ge=1, le=100)


# --- write inputs --------------------------------------------------------


class CreateIssueInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    title: str = Field(description="issue title")
    body: str = Field(description="issue body (markdown)")
    labels: list[str] = Field(default_factory=list)


class CommentOnPRInput(BaseModel):
    repo: str = Field(description="owner/name of the repository")
    number: int = Field(description="pull request (or issue) number")
    body: str = Field(description="comment body (markdown)")


# --- generic output ------------------------------------------------------


class ToolResult(BaseModel):
    """Uniform typed envelope returned by every tool."""

    ok: bool
    summary: str = Field(description="short human-readable description of the result")
    data: dict = Field(default_factory=dict, description="structured payload")
    citation: str | None = Field(
        default=None, description="file:line / issue# / commit SHA for traceability"
    )


# --- tool spec -----------------------------------------------------------


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    handler: Callable[[BaseModel], ToolResult]
    is_write: bool = False

    def json_schema(self) -> dict:
        """Schema the planner/executor LLM sees for this tool."""
        return {
            "name": self.name,
            "description": self.description,
            "is_write": self.is_write,
            "input_schema": self.input_model.model_json_schema(),
        }
