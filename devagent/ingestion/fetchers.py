"""Pull raw SDLC documents from a GitHub repo: code, issues/PRs, docs, commits.

Each fetcher yields ``RawDoc`` records. The pipeline chunks + embeds them.
Volumes are bounded (portfolio-scale corpus), configurable per call.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Iterator, Literal

from devagent.ingestion.github_client import GitHubClient

SourceType = Literal["code", "issue", "doc", "commit"]

# Extensions we treat as source code (AST-chunked downstream).
CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".rb", ".c", ".h", ".cpp", ".cc", ".sh",
}
DOC_EXTENSIONS = {".md", ".rst", ".txt"}
# Skip vendored / generated trees.
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", ".git", "__pycache__"}


@dataclass
class RawDoc:
    text: str
    source_type: SourceType
    metadata: dict = field(default_factory=dict)


def _decode_blob(node: dict, client: GitHubClient, repo: str) -> str | None:
    blob = client.get(f"/repos/{repo}/git/blobs/{node['sha']}")
    if blob.get("encoding") != "base64":
        return None
    try:
        raw = base64.b64decode(blob["content"])
        return raw.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None  # binary file


def _repo_tree(client: GitHubClient, repo: str) -> list[dict]:
    info = client.get(f"/repos/{repo}")
    default_branch = info["default_branch"]
    tree = client.get(
        f"/repos/{repo}/git/trees/{default_branch}", params={"recursive": "1"}
    )
    return [
        n for n in tree.get("tree", [])
        if n["type"] == "blob"
        and not any(part in SKIP_DIRS for part in n["path"].split("/"))
    ]


def fetch_code(client: GitHubClient, repo: str, *, max_files: int = 300) -> Iterator[RawDoc]:
    count = 0
    for node in _repo_tree(client, repo):
        path = node["path"]
        if not any(path.endswith(ext) for ext in CODE_EXTENSIONS):
            continue
        if node.get("size", 0) > 200_000:  # skip huge files
            continue
        content = _decode_blob(node, client, repo)
        if not content:
            continue
        yield RawDoc(
            text=content,
            source_type="code",
            metadata={"repo": repo, "file_path": path},
        )
        count += 1
        if count >= max_files:
            return


def fetch_docs(client: GitHubClient, repo: str, *, max_files: int = 100) -> Iterator[RawDoc]:
    count = 0
    for node in _repo_tree(client, repo):
        path = node["path"]
        if not any(path.endswith(ext) for ext in DOC_EXTENSIONS):
            continue
        content = _decode_blob(node, client, repo)
        if not content:
            continue
        yield RawDoc(
            text=content,
            source_type="doc",
            metadata={"repo": repo, "file_path": path},
        )
        count += 1
        if count >= max_files:
            return


def fetch_issues(
    client: GitHubClient, repo: str, *, max_items: int = 200, bypass_cache: bool = False
) -> Iterator[RawDoc]:
    """Fetch issues AND pull requests (GitHub's issues endpoint returns both)."""
    items = client.paginate(
        f"/repos/{repo}/issues",
        params={"state": "all", "sort": "updated"},
        max_items=max_items,
    )
    for item in items:
        is_pr = "pull_request" in item
        number = item["number"]
        body = item.get("body") or ""
        comments_text = ""
        if item.get("comments", 0):
            comments = client.get(
                f"/repos/{repo}/issues/{number}/comments", bypass_cache=bypass_cache
            )
            comments_text = "\n\n".join(
                f"@{c['user']['login']}: {c.get('body', '')}" for c in comments
            )
        text = (
            f"{'PR' if is_pr else 'Issue'} #{number}: {item['title']}\n"
            f"State: {item['state']}\n\n{body}\n\n{comments_text}"
        )
        yield RawDoc(
            text=text,
            source_type="issue",
            metadata={
                "repo": repo,
                "issue_number": number,
                "is_pr": is_pr,
                "state": item["state"],
                "title": item["title"],
                "updated_at": item.get("updated_at"),
            },
        )


def fetch_commits(client: GitHubClient, repo: str, *, max_items: int = 300) -> Iterator[RawDoc]:
    for commit in client.paginate(f"/repos/{repo}/commits", max_items=max_items):
        sha = commit["sha"]
        message = commit["commit"]["message"]
        author = commit["commit"]["author"]
        text = f"Commit {sha[:10]} by {author.get('name')} on {author.get('date')}\n\n{message}"
        yield RawDoc(
            text=text,
            source_type="commit",
            metadata={"repo": repo, "commit_sha": sha, "date": author.get("date")},
        )
