"""Claude Code CLI tool for protoClaw.

Gives the agent access to Claude (Anthropic) for complex reasoning,
code review, self-improvement, and tasks beyond the local LLM's capability.

Requires ANTHROPIC_API_KEY environment variable in the container.
Uses headless mode: claude -p "prompt" --output-format json
"""

import asyncio
import json
import os
from typing import Any

from nanobot.agent.tools.base import Tool


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
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return "Error: ANTHROPIC_API_KEY not set. Claude tool unavailable."

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

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/sandbox",
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
