"""Claude Code CLI tool for protoClaw.

Gives the agent access to Claude (Anthropic) for complex reasoning,
code review, self-improvement, and tasks beyond the local LLM's capability.

Rate-limited: daily call budget enforced with pre-execution warnings so the
agent understands the scarcity of this resource.

Auth chain (mirrors protoAgent-starter pattern):
  1. ANTHROPIC_API_KEY env var
  2. ANTHROPIC_AUTH_TOKEN env var (OAuth bearer token)
  3. Claude CLI credentials (~/.claude/.credentials.json or ~/.claude/credentials.json)

Uses headless mode: claude -p "prompt" --output-format json
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

_DEFAULT_DAILY_LIMIT = 10
_DEFAULT_WINDOW_HOURS = 24


class _RateLimiter:
    """Sliding-window rate limiter tracking call timestamps."""

    def __init__(self, limit: int = _DEFAULT_DAILY_LIMIT, window_hours: int = _DEFAULT_WINDOW_HOURS):
        self.limit = limit
        self.window_seconds = window_hours * 3600
        self._timestamps: list[float] = []

    def _prune(self) -> None:
        cutoff = time.monotonic() - self.window_seconds
        self._timestamps = [t for t in self._timestamps if t > cutoff]

    @property
    def remaining(self) -> int:
        self._prune()
        return max(0, self.limit - len(self._timestamps))

    @property
    def is_allowed(self) -> bool:
        return self.remaining > 0

    def record(self) -> None:
        self._timestamps.append(time.monotonic())

    def next_available_in(self) -> int:
        """Seconds until the oldest call expires and a slot opens. 0 if available now."""
        if self.is_allowed:
            return 0
        self._prune()
        if not self._timestamps:
            return 0
        oldest = self._timestamps[0]
        return max(0, int((oldest + self.window_seconds) - time.monotonic()))


_rate_limiter = _RateLimiter()


def configure_rate_limit(daily_limit: int = _DEFAULT_DAILY_LIMIT, window_hours: int = _DEFAULT_WINDOW_HOURS) -> None:
    """Reconfigure the global rate limiter (called from server.py if needed)."""
    global _rate_limiter
    _rate_limiter = _RateLimiter(limit=daily_limit, window_hours=window_hours)


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------

def _read_cli_oauth_token() -> str | None:
    """Read OAuth token from Claude CLI credential files."""
    home = Path.home()
    for path, extract in [
        (home / ".claude" / ".credentials.json", lambda d: (d.get("claudeAiOauth") or {}).get("accessToken")),
        (home / ".claude" / "credentials.json", lambda d: d.get("oauth_token") or d.get("access_token")),
    ]:
        if path.exists():
            try:
                data = json.loads(path.read_text())
                token = extract(data)
                if token:
                    return token
            except (json.JSONDecodeError, OSError):
                pass
    return None


def _resolve_auth() -> dict[str, str]:
    """Resolve auth credentials. Returns env dict to merge into subprocess."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return {}
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return {}
    token = _read_cli_oauth_token()
    if token:
        return {"ANTHROPIC_API_KEY": token}
    return {}


def is_claude_available() -> bool:
    """Check if Claude auth is available via any method."""
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or _read_cli_oauth_token()
    )


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class ClaudeTool(Tool):
    """Invoke Claude Code CLI for complex tasks. Rate-limited."""

    _TIMEOUT = 300
    _MAX_OUTPUT = 12000

    @property
    def name(self) -> str:
        return "claude"

    @property
    def description(self) -> str:
        remaining = _rate_limiter.remaining
        limit = _rate_limiter.limit
        return (
            f"Run Claude (Anthropic) for tasks beyond the local LLM — complex reasoning, "
            f"code review, architectural analysis, self-improvement. "
            f"BUDGET: {remaining}/{limit} calls remaining today. "
            f"This is a SCARCE resource — only use when the local model genuinely cannot "
            f"handle the task. Exhaust local tools first."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task or question for Claude. Be specific and detailed to maximize value from this limited resource.",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Max agentic iterations (default 5, max 20).",
                },
                "allowed_tools": {
                    "type": "string",
                    "description": "Comma-separated tools to allow (default: Read,Glob,Grep,Bash). Use 'all' for full access.",
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        # --- Auth check ---
        auth_env = _resolve_auth()
        if not auth_env and not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return (
                "Error: No Claude credentials found. Set ANTHROPIC_API_KEY, "
                "ANTHROPIC_AUTH_TOKEN, or run `claude login` to authenticate."
            )

        # --- Rate limit check ---
        remaining = _rate_limiter.remaining
        if not _rate_limiter.is_allowed:
            wait = _rate_limiter.next_available_in()
            minutes = wait // 60
            return (
                f"RATE LIMIT: You have used all {_rate_limiter.limit} Claude calls "
                f"in the current window. Next call available in ~{minutes} minutes. "
                f"Use your local tools and reasoning to proceed."
            )

        # --- Pre-execution budget warning (returned as prefix to result) ---
        after_this = remaining - 1
        if after_this <= 2:
            budget_warning = (
                f"⚠️ BUDGET CRITICAL: After this call you have {after_this} Claude call(s) "
                f"remaining today. Make every call count.\n\n"
            )
        elif after_this <= 5:
            budget_warning = (
                f"Budget note: {after_this} Claude call(s) will remain after this one.\n\n"
            )
        else:
            budget_warning = ""

        # --- Record usage before execution ---
        _rate_limiter.record()

        prompt = kwargs["prompt"]
        max_turns = min(kwargs.get("max_turns", 5), 20)
        allowed_tools = kwargs.get("allowed_tools", "Read,Glob,Grep,Bash")

        cmd = [
            "claude",
            "-p", prompt,
            "--output-format", "json",
            "--max-turns", str(max_turns),
            "--dangerously-skip-permissions",
        ]

        if allowed_tools and allowed_tools != "all":
            cmd.extend(["--allowedTools", allowed_tools])

        env = {**os.environ, **auth_env}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/sandbox",
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            return budget_warning + f"Error: Claude timed out after {self._TIMEOUT}s."
        except FileNotFoundError:
            return "Error: Claude Code CLI not installed."

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            return budget_warning + f"Error: Claude exited {proc.returncode}: {err[:500]}"

        raw = stdout.decode(errors="replace").strip()
        try:
            data = json.loads(raw)
            result = data.get("result", raw)
        except json.JSONDecodeError:
            result = raw

        if len(result) > self._MAX_OUTPUT:
            result = result[:self._MAX_OUTPUT] + "\n\n[... truncated]"

        return budget_warning + result
