"""GitHub read tools — callable, Pydantic-schemed, returning typed ToolResults."""

from __future__ import annotations

import base64

from devagent.ingestion.github_client import GitHubError, get_github_client
from devagent.tools.schemas import (
    FetchFileInput,
    GetPRDiffInput,
    ListCommitsInput,
    ListIssuesInput,
    SearchCodeInput,
    ToolResult,
    ToolSpec,
)


def _err(summary: str) -> ToolResult:
    return ToolResult(ok=False, summary=summary)


def fetch_file(inp: FetchFileInput) -> ToolResult:
    """Fetch the full contents of a single file from a repo."""
    params = {"ref": inp.ref} if inp.ref else None
    try:
        with get_github_client() as gh:
            data = gh.get(f"/repos/{inp.repo}/contents/{inp.path}", params=params)
    except GitHubError as exc:
        return _err(str(exc))
    if isinstance(data, list):
        return _err(f"{inp.path} is a directory, not a file")
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return ToolResult(
        ok=True,
        summary=f"Fetched {inp.path} ({len(content)} chars)",
        data={"path": inp.path, "content": content, "sha": data["sha"]},
        citation=f"{inp.path}",
    )


def search_code(inp: SearchCodeInput) -> ToolResult:
    """Search code in a repo for a keyword or symbol."""
    try:
        with get_github_client() as gh:
            data = gh.get(
                "/search/code",
                params={"q": f"{inp.query} repo:{inp.repo}", "per_page": inp.max_results},
            )
    except GitHubError as exc:
        return _err(str(exc))
    hits = [
        {"path": item["path"], "url": item["html_url"]}
        for item in data.get("items", [])[: inp.max_results]
    ]
    return ToolResult(
        ok=True,
        summary=f"{len(hits)} code matches for '{inp.query}'",
        data={"matches": hits, "total": data.get("total_count", 0)},
        citation=hits[0]["path"] if hits else None,
    )


def list_issues(inp: ListIssuesInput) -> ToolResult:
    """List issues (and PRs) in a repo, optionally filtered by label/state."""
    params = {"state": inp.state}
    if inp.labels:
        params["labels"] = inp.labels
    try:
        with get_github_client() as gh:
            items = list(
                gh.paginate(f"/repos/{inp.repo}/issues", params=params, max_items=inp.max_results)
            )
    except GitHubError as exc:
        return _err(str(exc))
    issues = [
        {
            "number": it["number"],
            "title": it["title"],
            "state": it["state"],
            "is_pr": "pull_request" in it,
            "labels": [l["name"] for l in it.get("labels", [])],
        }
        for it in items
    ]
    return ToolResult(
        ok=True,
        summary=f"{len(issues)} items in {inp.repo} (state={inp.state})",
        data={"issues": issues},
        citation=f"#{issues[0]['number']}" if issues else None,
    )


def get_pr_diff(inp: GetPRDiffInput) -> ToolResult:
    """Fetch the file-level diff summary for a pull request."""
    try:
        with get_github_client() as gh:
            pr = gh.get(f"/repos/{inp.repo}/pulls/{inp.number}")
            files = list(
                gh.paginate(f"/repos/{inp.repo}/pulls/{inp.number}/files", max_items=100)
            )
    except GitHubError as exc:
        return _err(str(exc))
    changed = [
        {
            "filename": f["filename"],
            "status": f["status"],
            "additions": f["additions"],
            "deletions": f["deletions"],
            "patch": f.get("patch", "")[:2000],
        }
        for f in files
    ]
    return ToolResult(
        ok=True,
        summary=f"PR #{inp.number} '{pr['title']}' — {len(changed)} files changed",
        data={"title": pr["title"], "state": pr["state"], "files": changed},
        citation=f"#{inp.number}",
    )


def list_commits(inp: ListCommitsInput) -> ToolResult:
    """List recent commits in a repo, optionally scoped to a file path."""
    params = {"path": inp.path} if inp.path else None
    try:
        with get_github_client() as gh:
            items = list(
                gh.paginate(f"/repos/{inp.repo}/commits", params=params, max_items=inp.max_results)
            )
    except GitHubError as exc:
        return _err(str(exc))
    commits = [
        {
            "sha": c["sha"],
            "message": c["commit"]["message"].splitlines()[0],
            "author": c["commit"]["author"].get("name"),
            "date": c["commit"]["author"].get("date"),
        }
        for c in items
    ]
    return ToolResult(
        ok=True,
        summary=f"{len(commits)} commits"
        + (f" touching {inp.path}" if inp.path else f" in {inp.repo}"),
        data={"commits": commits},
        citation=commits[0]["sha"][:10] if commits else None,
    )


READ_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="fetch_file",
        description="Fetch the full contents of a single file from a GitHub repo.",
        input_model=FetchFileInput,
        handler=fetch_file,
    ),
    ToolSpec(
        name="search_code",
        description="Search a GitHub repo's code for a keyword or symbol.",
        input_model=SearchCodeInput,
        handler=search_code,
    ),
    ToolSpec(
        name="list_issues",
        description="List issues and pull requests in a repo, filterable by state and label.",
        input_model=ListIssuesInput,
        handler=list_issues,
    ),
    ToolSpec(
        name="get_pr_diff",
        description="Fetch the file-level diff summary for a pull request.",
        input_model=GetPRDiffInput,
        handler=get_pr_diff,
    ),
    ToolSpec(
        name="list_commits",
        description="List recent commits in a repo, optionally scoped to a file path.",
        input_model=ListCommitsInput,
        handler=list_commits,
    ),
]
