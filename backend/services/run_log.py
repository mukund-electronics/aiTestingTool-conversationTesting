"""In-memory WebSocket traffic log for active test runs.

Entries are stored per run_id and capped at _MAX_ENTRIES to avoid unbounded
growth.  Logs are intentionally ephemeral: they reset on server restart, which
is acceptable for a real-time debugging aid.

Usage (from ws_caller.py):
    from backend.services.run_log import ws_log
    ws_log(run_id, "event", "connect", f"Connected to {url}")
    ws_log(run_id, "out",   "message", json.dumps(payload)[:400])
    ws_log(run_id, "in",    "message", raw[:400])
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

_MAX_ENTRIES = 500

# run_id → ordered list of log entry dicts
_LOGS: dict[int, list[dict]] = {}

LogDir  = Literal["out", "in", "event"]
LogKind = Literal[
    "connect", "disconnect", "reconnect",
    "message", "ping", "pong", "error", "discard",
]

_BODY_LIMIT = 400   # max chars stored per message body


def ws_log(run_id: int, dir: LogDir, kind: LogKind, body: str) -> None:
    """Append one entry to the log for *run_id*. No-op when run_id == 0."""
    if not run_id:
        return
    entries = _LOGS.setdefault(run_id, [])
    entries.append({
        "ts":   datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3],
        "dir":  dir,
        "kind": kind,
        "body": body[:_BODY_LIMIT] if body else "",
    })
    if len(entries) > _MAX_ENTRIES:
        del entries[: len(entries) - _MAX_ENTRIES]


def get_ws_logs(run_id: int) -> list[dict]:
    return list(_LOGS.get(run_id, []))


def clear_ws_logs(run_id: int) -> None:
    _LOGS.pop(run_id, None)
