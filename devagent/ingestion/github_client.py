"""Thin GitHub REST client: retry-on-rate-limit + raw-response disk cache.

Shared by the ingestion pipeline (bulk fetch) and the GitHub read/write tools
(targeted calls). Caching is keyed on the request and keeps ingestion cheap to
re-run; write requests and explicitly fresh reads bypass the cache.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Iterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from devagent.config import CACHE_DIR, get_settings

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    """Raised for non-recoverable GitHub API failures, with a root-cause message."""


class _RateLimited(Exception):
    """Internal signal that a request should be retried after a backoff."""


class GitHubClient:
    def __init__(self, *, use_cache: bool = True) -> None:
        settings = get_settings()
        self._token = settings.require_github()
        self._use_cache = use_cache
        self._cache_dir = CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._client = httpx.Client(
            base_url=API_ROOT,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    # -- cache -------------------------------------------------------------
    def _cache_path(self, method: str, path: str, params: dict | None) -> Path:
        key = f"{method}:{path}:{json.dumps(params or {}, sort_keys=True)}"
        digest = hashlib.sha256(key.encode()).hexdigest()[:24]
        return self._cache_dir / f"{digest}.json"

    # -- core request ------------------------------------------------------
    @retry(
        retry=retry_if_exception_type(_RateLimited),
        wait=wait_exponential(multiplier=2, min=2, max=120),
        stop=stop_after_attempt(6),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        bypass_cache: bool = False,
    ) -> Any:
        cacheable = method == "GET" and self._use_cache and not bypass_cache
        cache_path = self._cache_path(method, path, params) if cacheable else None
        if cache_path and cache_path.exists():
            return json.loads(cache_path.read_text())

        try:
            resp = self._client.request(method, path, params=params, json=json_body)
        except httpx.HTTPError as exc:  # network-level failure
            raise GitHubError(f"GitHub request failed ({method} {path}): {exc}") from exc

        # Rate limit: GitHub returns 403/429 with x-ratelimit-remaining: 0.
        if resp.status_code in (403, 429) and resp.headers.get("x-ratelimit-remaining") == "0":
            reset = resp.headers.get("x-ratelimit-reset")
            if reset:
                wait_for = max(0, int(reset) - int(time.time())) + 1
                # cap explicit sleeps so tenacity's backoff stays in charge of long waits
                time.sleep(min(wait_for, 30))
            raise _RateLimited()

        if resp.status_code >= 400:
            detail = resp.json().get("message", resp.text) if resp.content else resp.reason_phrase
            raise GitHubError(f"GitHub {resp.status_code} on {method} {path}: {detail}")

        data = resp.json() if resp.content else None
        if cache_path is not None:
            cache_path.write_text(json.dumps(data))
        return data

    # -- public GET helpers ------------------------------------------------
    def get(self, path: str, *, params: dict | None = None, bypass_cache: bool = False) -> Any:
        return self._request("GET", path, params=params, bypass_cache=bypass_cache)

    def paginate(
        self, path: str, *, params: dict | None = None, max_items: int | None = None
    ) -> Iterator[dict]:
        """Iterate a paginated list endpoint, page size 100."""
        page = 1
        seen = 0
        params = dict(params or {})
        params["per_page"] = 100
        while True:
            params["page"] = page
            batch = self.get(path, params=params)
            if not batch:
                return
            for item in batch:
                yield item
                seen += 1
                if max_items is not None and seen >= max_items:
                    return
            if len(batch) < 100:
                return
            page += 1

    # -- write -------------------------------------------------------------
    def post(self, path: str, *, json_body: dict) -> Any:
        return self._request("POST", path, json_body=json_body, bypass_cache=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def get_github_client(*, use_cache: bool = True):
    """Return the GitHub client for the configured mode.

    GITHUB_MODE=fixtures (default) -> offline FakeGitHubClient.
    GITHUB_MODE=live -> real GitHubClient (requires GITHUB_TOKEN).
    Both expose the same get / paginate / post interface.
    """
    if get_settings().github_mode == "fixtures":
        from devagent.ingestion.fake_github import FakeGitHubClient

        return FakeGitHubClient(use_cache=use_cache)
    return GitHubClient(use_cache=use_cache)
