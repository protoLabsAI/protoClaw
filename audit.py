"""Audit logging for protoClaw tool executions.

Writes JSONL entries to /sandbox/audit/audit.jsonl with tool call metadata.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """Append-only JSONL audit log for tool executions."""

    def __init__(self, path: str | Path = "/sandbox/audit/audit.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        *,
        session_id: str,
        tool: str,
        args: dict[str, Any],
        result_summary: str,
        duration_ms: int,
        success: bool,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "tool": tool,
            "args": _sanitize_args(args),
            "result_summary": result_summary[:200],
            "duration_ms": duration_ms,
            "success": success,
        }
        try:
            with self.path.open("a") as f:
                f.write(json.dumps(entry, default=str) + "\n")
        except OSError:
            pass  # Don't crash the agent if audit dir is unavailable

    def get_recent(
        self, n: int = 20, session_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Read the last n entries, optionally filtered by session_id."""
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text().strip().splitlines()
        except OSError:
            return []

        entries = []
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if session_id and entry.get("session_id") != session_id:
                continue
            entries.append(entry)
            if len(entries) >= n:
                break
        entries.reverse()
        return entries


def _sanitize_args(args: dict[str, Any]) -> dict[str, Any]:
    """Truncate large argument values for storage."""
    sanitized = {}
    for k, v in args.items():
        s = str(v)
        sanitized[k] = s[:500] if len(s) > 500 else v
    return sanitized


# Module-level singleton
audit_logger = AuditLogger()
