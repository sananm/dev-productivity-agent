"""Write-tool mocking for eval runs.

The eval harness must make zero real GitHub mutations. This context manager
swaps the registry's write ToolSpecs for deterministic no-op handlers, so even
in GITHUB_MODE=live an eval run cannot create issues or post comments.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace

from devagent.tools import registry
from devagent.tools.schemas import CommentOnPRInput, CreateIssueInput, ToolResult


def _mock_create_issue(inp: CreateIssueInput) -> ToolResult:
    return ToolResult(
        ok=True,
        summary=f"[mock] would create issue: {inp.title}",
        data={"number": 99999, "url": f"https://example.invalid/{inp.repo}/issues/99999"},
        citation="#99999",
    )


def _mock_comment_on_pr(inp: CommentOnPRInput) -> ToolResult:
    return ToolResult(
        ok=True,
        summary=f"[mock] would comment on #{inp.number}",
        data={"url": f"https://example.invalid/{inp.repo}/issues/{inp.number}#mock"},
        citation=f"#{inp.number}",
    )


_MOCKS = {"create_issue": _mock_create_issue, "comment_on_pr": _mock_comment_on_pr}


@contextmanager
def mock_write_tools():
    original = {name: registry._REGISTRY[name] for name in _MOCKS}
    try:
        for name, handler in _MOCKS.items():
            registry._REGISTRY[name] = replace(original[name], handler=handler)
        yield
    finally:
        for name, spec in original.items():
            registry._REGISTRY[name] = spec
