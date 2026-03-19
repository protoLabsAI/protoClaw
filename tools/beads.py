"""Beads issue tracker tool for protoClaw.

Wraps the `br` CLI for issue tracking with dependency-driven work queues.
All output is JSON for structured consumption by the agent.
"""

import asyncio
import json
import os
from typing import Any

from nanobot.agent.tools.base import Tool


class BeadsTool(Tool):
    """Issue tracking via beads (br) CLI."""

    _TIMEOUT = 15
    _WORKSPACE = "/sandbox"

    @property
    def name(self) -> str:
        return "beads"

    @property
    def description(self) -> str:
        return (
            "Local issue tracker for managing tasks, bugs, and features across sessions. "
            "Supports priorities (P0-P4), dependency graphs, and a ready queue that shows "
            "only unblocked work. Use this to track all multi-step or cross-session work."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "The br subcommand to run. Common commands:\n"
                        "- ready: list actionable (unblocked) issues\n"
                        "- list: list all issues (add --status open to filter)\n"
                        "- show <id>: show issue details with deps/comments\n"
                        "- create <title>: create issue (use --type, -p, -d flags)\n"
                        "- update <id>: update issue (--status, --priority, --assignee)\n"
                        "- close <id>: close issue (--reason 'why')\n"
                        "- dep add <child> <parent>: add blocking dependency\n"
                        "- dep remove <child> <parent>: remove dependency\n"
                        "- comment add <id> <text>: add comment\n"
                        "- search <query>: full-text search\n"
                        "- stats: project statistics\n"
                        "- blocked: show blocked issues\n"
                        "- label add <id> <labels...>: add labels"
                    ),
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> str:
        command = kwargs["command"].strip()
        if not command:
            return "Error: command is required."

        # Split command into args, always append --json for structured output
        import shlex
        try:
            args = shlex.split(command)
        except ValueError as e:
            return f"Error: invalid command syntax: {e}"

        cmd = ["br", *args, "--json"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._WORKSPACE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._TIMEOUT
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"Error: beads command timed out after {self._TIMEOUT}s."
        except FileNotFoundError:
            return "Error: br CLI not installed."

        if proc.returncode != 0:
            err = stderr.decode(errors="replace").strip()
            # Some br commands write useful output to stdout even on non-zero exit
            out = stdout.decode(errors="replace").strip()
            return f"Error (exit {proc.returncode}): {err or out}"[:1000]

        output = stdout.decode(errors="replace").strip()
        if not output:
            return "(no output)"

        # Truncate very long outputs
        if len(output) > 8000:
            output = output[:8000] + "\n\n[... truncated]"

        return output
