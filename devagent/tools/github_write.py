"""GitHub write tools — confirmation-gated, audit-logged at the graph layer.

These handlers are pure GitHub calls. The agent graph never invokes them
directly: a write step is suspended at the confirmation gate (LangGraph
interrupt()), and only the write_executor node — after explicit user approval —
calls the handler. The audit trail and dry-run handling live in that node.
"""

from __future__ import annotations

from devagent.ingestion.github_client import GitHubError, get_github_client
from devagent.tools.schemas import (
    CommentOnPRInput,
    CreateIssueInput,
    ToolResult,
    ToolSpec,
)


def create_issue(inp: CreateIssueInput) -> ToolResult:
    """Create a new issue in a GitHub repo."""
    try:
        with get_github_client() as gh:
            data = gh.post(
                f"/repos/{inp.repo}/issues",
                json_body={"title": inp.title, "body": inp.body, "labels": inp.labels},
            )
    except GitHubError as exc:
        return ToolResult(ok=False, summary=str(exc))
    return ToolResult(
        ok=True,
        summary=f"Created issue #{data['number']}: {data['title']}",
        data={"number": data["number"], "url": data["html_url"]},
        citation=f"#{data['number']}",
    )


def comment_on_pr(inp: CommentOnPRInput) -> ToolResult:
    """Post a comment on a pull request (or issue) in a GitHub repo."""
    try:
        with get_github_client() as gh:
            data = gh.post(
                f"/repos/{inp.repo}/issues/{inp.number}/comments",
                json_body={"body": inp.body},
            )
    except GitHubError as exc:
        return ToolResult(ok=False, summary=str(exc))
    return ToolResult(
        ok=True,
        summary=f"Commented on #{inp.number}",
        data={"url": data["html_url"]},
        citation=f"#{inp.number}",
    )


WRITE_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="create_issue",
        description="Create a new issue in the repo. WRITE action — requires user confirmation.",
        input_model=CreateIssueInput,
        handler=create_issue,
        is_write=True,
    ),
    ToolSpec(
        name="comment_on_pr",
        description="Post a comment on a pull request or issue. WRITE action — requires user confirmation.",
        input_model=CommentOnPRInput,
        handler=comment_on_pr,
        is_write=True,
    ),
]
