"""Claude Code CLI tool for protoClaw.

Gives the agent access to Claude (Anthropic) for complex reasoning,
code review, self-improvement, and tasks beyond the local LLM's capability.

Auth chain (mirrors protoAgent-starter pattern):
  1. ANTHROPIC_API_KEY env var
  2. ANTHROPIC_AUTH_TOKEN env var (OAuth bearer token)
  3. Claude CLI credentials (~/.claude/.credentials.json or ~/.claude/credentials.json)

Uses headless mode: claude -p "prompt" --output-format json
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


def _read_cli_oauth_token() -> str | None:
    """Read OAuth token from Claude CLI credential files.

    Checks (in order):
      ~/.claude/.credentials.json  → claudeAiOauth.accessToken
      ~/.claude/credentials.json   → oauth_token or access_token
    """
    home = Path.home()
    # Modern format
    modern = home / ".claude" / ".credentials.json"
    if modern.exists():
        try:
            data = json.loads(modern.read_text())
            token = (data.get("claudeAiOauth") or {}).get("accessToken")
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    # Legacy format
    legacy = home / ".claude" / "credentials.json"
    if legacy.exists():
        try:
            data = json.loads(legacy.read_text())
            token = data.get("oauth_token") or data.get("access_token")
            if token:
                return token
        except (json.JSONDecodeError, OSError):
            pass

    return None


def _resolve_auth() -> dict[str, str]:
    """Resolve auth credentials. Returns env dict to merge into subprocess.

    Priority:
      1. ANTHROPIC_API_KEY already in env
      2. ANTHROPIC_AUTH_TOKEN already in env
      3. CLI OAuth token from credentials files → set as ANTHROPIC_API_KEY
    """
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
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return True
    if _read_cli_oauth_token():
        return True
    return False


class ClaudeTool(Tool):
    """Invoke Claude Code CLI for complex tasks."""

    _TIMEOUT = 300  # 5 minutes max per invocation
    _MAX_OUTPUT = 12000  # chars

    @property
    def name(self) -> str:
        return "claude"

    @property
    def description(self) -> str:
        return (
            "Run Claude (Anthropic) for complex reasoning, code review, analysis, "
            "or tasks that need a more capable model. Provide a clear prompt describing "
            "the task. Claude can read/write files in the sandbox workspace. "
            "Use sparingly — each call costs API credits."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task or question for Claude.",
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
        auth_env = _resolve_auth()
        if not auth_env and not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return (
                "Error: No Claude credentials found. Set ANTHROPIC_API_KEY, "
                "ANTHROPIC_AUTH_TOKEN, or run `claude login` to authenticate."
            )

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

        # Merge auth env into subprocess environment
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
            return f"Error: Claude timed out after {self._TIMEOUT}s."
        except FileNotFoundError:
            return "Error: Claude Code CLI not installed."

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            return f"Error: Claude exited {proc.returncode}: {err[:500]}"

        raw = stdout.decode(errors="replace").strip()
        try:
            data = json.loads(raw)
            result = data.get("result", raw)
        except json.JSONDecodeError:
            result = raw

        if len(result) > self._MAX_OUTPUT:
            result = result[:self._MAX_OUTPUT] + "\n\n[... truncated]"

        return result
