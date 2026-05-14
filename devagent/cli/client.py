"""Thin SSE HTTP client for the devagent FastAPI service.

The CLI contains zero agent logic — it only speaks HTTP. This module turns the
/query and /confirm SSE streams into an iterator of (event, data) pairs and
raises a friendly CliError for connection problems.
"""

from __future__ import annotations

import json
from typing import Iterator

import httpx


class CliError(RuntimeError):
    """A user-facing error — printed as a root-cause message, never a traceback."""


def _stream(url: str, payload: dict) -> Iterator[tuple[str, dict]]:
    try:
        with httpx.Client(timeout=httpx.Timeout(300.0, connect=5.0)) as client:
            with client.stream("POST", url, json=payload) as resp:
                if resp.status_code != 200:
                    resp.read()
                    raise CliError(f"API returned {resp.status_code}: {resp.text[:200]}")
                event: str | None = None
                data_lines: list[str] = []
                for line in resp.iter_lines():
                    if line.startswith("event:"):
                        event = line[len("event:"):].strip()
                    elif line.startswith("data:"):
                        data_lines.append(line[len("data:"):].strip())
                    elif line == "" and event is not None:
                        raw = "\n".join(data_lines)
                        yield event, json.loads(raw) if raw else {}
                        event, data_lines = None, []
    except httpx.ConnectError as exc:
        raise CliError(
            f"Cannot reach the devagent API at {url}. Is the server running?\n"
            f"  Start it with:  uvicorn devagent.api.main:app"
        ) from exc
    except httpx.HTTPError as exc:
        raise CliError(f"HTTP error talking to the API: {exc}") from exc


def stream_query(
    api_base_url: str,
    *,
    query: str,
    repo: str,
    dry_run: bool,
    prompt_version: str,
) -> Iterator[tuple[str, dict]]:
    yield from _stream(
        f"{api_base_url}/query",
        {"query": query, "repo": repo, "dry_run": dry_run, "prompt_version": prompt_version},
    )


def stream_confirm(
    api_base_url: str, *, thread_id: str, decision: str
) -> Iterator[tuple[str, dict]]:
    yield from _stream(
        f"{api_base_url}/confirm",
        {"thread_id": thread_id, "decision": decision},
    )


def health(api_base_url: str) -> dict:
    try:
        resp = httpx.get(f"{api_base_url}/health", timeout=5.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise CliError(
            f"Cannot reach the devagent API at {api_base_url}. Is the server running?"
        ) from exc
