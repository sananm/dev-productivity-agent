"""Append-only audit log for GitHub write actions.

Every write moves through states — proposed -> confirmed|rejected ->
executed|dry_run|error — and each transition is recorded. The write_executor
node calls this; nothing ever deletes or updates a row.
"""

from __future__ import annotations

import json
from typing import Literal

from devagent.db.session import execute, fetch_all

AuditStatus = Literal["proposed", "confirmed", "rejected", "executed", "dry_run", "error"]


def log_action(
    *,
    thread_id: str,
    repo: str,
    action: str,
    params: dict,
    status: AuditStatus,
    result: dict | None = None,
) -> None:
    execute(
        "INSERT INTO audit_log (thread_id, repo, action, params, status, result) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (thread_id, repo, action, json.dumps(params), status, json.dumps(result) if result else None),
    )


def history(thread_id: str | None = None) -> list[dict]:
    if thread_id:
        return fetch_all(
            "SELECT * FROM audit_log WHERE thread_id = %s ORDER BY id", (thread_id,)
        )
    return fetch_all("SELECT * FROM audit_log ORDER BY id DESC LIMIT 100")
