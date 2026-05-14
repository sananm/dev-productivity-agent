"""Offline GitHub client backed by bundled JSON fixtures.

Serves the same interface as GitHubClient (get / paginate / post) by routing
request paths against fixtures/<repo>/{meta,files,commits,issues}.json. This is
the default backend (GITHUB_MODE=fixtures) so the whole platform runs with no
network and no token. Writes are appended in-memory for session consistency but
never leave the process.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Iterator

from devagent.config import FIXTURES_DIR
from devagent.ingestion.github_client import GitHubError


def _fixture_dir(repo: str):
    path = FIXTURES_DIR / repo.replace("/", "__")
    if not path.exists():
        raise GitHubError(
            f"No fixtures for {repo!r} at {path}. Build them with "
            f"scripts/build_fixtures.py, or set GITHUB_MODE=live."
        )
    return path


class FakeGitHubClient:
    def __init__(self, *, use_cache: bool = True) -> None:  # signature mirrors GitHubClient
        self._repos: dict[str, dict] = {}

    # -- fixture loading ---------------------------------------------------
    def _repo(self, repo: str) -> dict:
        if repo not in self._repos:
            d = _fixture_dir(repo)
            data = {
                "meta": json.loads((d / "meta.json").read_text()),
                "files": json.loads((d / "files.json").read_text()),
                "commits": json.loads((d / "commits.json").read_text()),
                "issues": json.loads((d / "issues.json").read_text())
                if (d / "issues.json").exists()
                else [],
            }
            data["_next_number"] = max((i["number"] for i in data["issues"]), default=9000) + 1
            self._repos[repo] = data
        return self._repos[repo]

    # -- API-shaping helpers ----------------------------------------------
    @staticmethod
    def _issue_payload(issue: dict) -> dict:
        out = {k: v for k, v in issue.items() if not k.startswith("_")}
        out["labels"] = [{"name": name} for name in issue.get("labels", [])]
        out["user"] = {"login": issue.get("user", "unknown")}
        out["comments"] = len(issue.get("_comments", []))
        if issue.get("pull_request"):
            out["pull_request"] = {"url": f"#{issue['number']}"}
        else:
            out.pop("pull_request", None)
        return out

    @staticmethod
    def _commit_payload(commit: dict) -> dict:
        return {
            "sha": commit["sha"],
            "commit": {
                "message": commit["message"],
                "author": {"name": commit["author_name"], "date": commit["date"]},
            },
        }

    # -- routing -----------------------------------------------------------
    def get(self, path: str, *, params: dict | None = None, bypass_cache: bool = False) -> Any:
        params = params or {}
        path = path.split("?")[0]

        # /search/code
        if path == "/search/code":
            return self._search_code(params)

        m = re.match(r"^/repos/([^/]+/[^/]+)(/.*)?$", path)
        if not m:
            raise GitHubError(f"FakeGitHubClient: unrouteable path {path!r}")
        repo, rest = m.group(1), m.group(2) or ""
        data = self._repo(repo)

        if rest == "":
            meta = data["meta"]
            return {"full_name": repo, "name": repo.split("/")[1],
                    "default_branch": meta["default_branch"]}

        if re.match(r"^/git/trees/", rest):
            tree = [
                {"path": p, "sha": f["sha"], "size": f["size"], "type": "blob"}
                for p, f in data["files"].items()
            ]
            return {"tree": tree}

        m2 = re.match(r"^/git/blobs/(.+)$", rest)
        if m2:
            sha = m2.group(1)
            for f in data["files"].values():
                if f["sha"] == sha:
                    encoded = base64.b64encode(f["content"].encode()).decode()
                    return {"sha": sha, "encoding": "base64", "content": encoded}
            raise GitHubError(f"blob {sha} not found in {repo}")

        m3 = re.match(r"^/contents/(.+)$", rest)
        if m3:
            file_path = m3.group(1)
            f = data["files"].get(file_path)
            if f is None:
                raise GitHubError(f"GitHub 404 on contents/{file_path}: Not Found")
            encoded = base64.b64encode(f["content"].encode()).decode()
            return {"path": file_path, "sha": f["sha"], "encoding": "base64", "content": encoded}

        if rest == "/issues":
            return self._list_issues(data, params)

        m4 = re.match(r"^/issues/(\d+)/comments$", rest)
        if m4:
            issue = self._find_issue(data, int(m4.group(1)))
            return [
                {"user": {"login": c["user"]}, "body": c["body"]}
                for c in issue.get("_comments", [])
            ]

        if rest == "/commits":
            return self._list_commits(data, params)

        m5 = re.match(r"^/pulls/(\d+)$", rest)
        if m5:
            issue = self._find_issue(data, int(m5.group(1)))
            return self._issue_payload(issue)

        m6 = re.match(r"^/pulls/(\d+)/files$", rest)
        if m6:
            issue = self._find_issue(data, int(m6.group(1)))
            return list(issue.get("_files", []))

        raise GitHubError(f"FakeGitHubClient: unrouteable path /repos/{repo}{rest}")

    # -- list endpoints ----------------------------------------------------
    @staticmethod
    def _find_issue(data: dict, number: int) -> dict:
        for issue in data["issues"]:
            if issue["number"] == number:
                return issue
        raise GitHubError(f"issue/PR #{number} not found")

    def _list_issues(self, data: dict, params: dict) -> list[dict]:
        state = params.get("state", "open")
        items = data["issues"]
        if state != "all":
            items = [i for i in items if i.get("state") == state]
        if params.get("labels"):
            wanted = {l.strip() for l in params["labels"].split(",")}
            items = [i for i in items if wanted & set(i.get("labels", []))]
        if params.get("sort") == "updated":
            items = sorted(items, key=lambda i: i.get("updated_at", ""), reverse=True)
        return [self._issue_payload(i) for i in items]

    def _list_commits(self, data: dict, params: dict) -> list[dict]:
        commits = data["commits"]
        path = params.get("path")
        if path:
            commits = [c for c in commits if any(path in f for f in c.get("files", []))]
        return [self._commit_payload(c) for c in commits]

    def _search_code(self, params: dict) -> dict:
        q = params.get("q", "")
        term = re.sub(r"\brepo:\S+", "", q).strip().lower()
        repo_m = re.search(r"\brepo:(\S+)", q)
        if not repo_m:
            raise GitHubError("search_code requires a repo: qualifier")
        data = self._repo(repo_m.group(1))
        hits = []
        for p, f in data["files"].items():
            if term and term in f["content"].lower():
                hits.append({"path": p, "html_url": f"https://github.com/{repo_m.group(1)}/blob/main/{p}"})
        limit = int(params.get("per_page", 10))
        return {"items": hits[:limit], "total_count": len(hits)}

    # -- pagination --------------------------------------------------------
    def paginate(
        self, path: str, *, params: dict | None = None, max_items: int | None = None
    ) -> Iterator[dict]:
        items = self.get(path, params=params)
        if not isinstance(items, list):
            raise GitHubError(f"paginate() called on non-list endpoint {path!r}")
        for i, item in enumerate(items):
            if max_items is not None and i >= max_items:
                return
            yield item

    # -- writes (in-memory only) ------------------------------------------
    def post(self, path: str, *, json_body: dict) -> Any:
        m = re.match(r"^/repos/([^/]+/[^/]+)/issues$", path)
        if m:
            data = self._repo(m.group(1))
            number = data["_next_number"]
            data["_next_number"] += 1
            issue = {
                "number": number,
                "title": json_body["title"],
                "body": json_body.get("body", ""),
                "state": "open",
                "labels": json_body.get("labels", []),
                "user": "devagent",
                "_comments": [],
            }
            data["issues"].append(issue)
            return {
                "number": number,
                "title": issue["title"],
                "html_url": f"https://github.com/{m.group(1)}/issues/{number}",
            }
        m2 = re.match(r"^/repos/([^/]+/[^/]+)/issues/(\d+)/comments$", path)
        if m2:
            data = self._repo(m2.group(1))
            issue = self._find_issue(data, int(m2.group(2)))
            issue.setdefault("_comments", []).append(
                {"user": "devagent", "body": json_body["body"]}
            )
            cid = int(hashlib.sha1(json_body["body"].encode()).hexdigest()[:8], 16)
            return {
                "id": cid,
                "html_url": f"https://github.com/{m2.group(1)}/issues/{m2.group(2)}#issuecomment-{cid}",
            }
        raise GitHubError(f"FakeGitHubClient: unrouteable POST {path!r}")

    def close(self) -> None:  # interface parity
        pass

    def __enter__(self) -> "FakeGitHubClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
