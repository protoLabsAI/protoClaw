"""Phone a Friend — multi-provider LLM fallback tool for protoClaw.

Gives the agent access to multiple LLM providers when tasks get difficult,
the local model is struggling, or Claude is rate-limited. Each "friend"
has different capabilities, intelligence levels, and costs.

Providers:
  - Claude (Anthropic) — via claude CLI, rate-limited, highest capability
  - OpenCode free models — via opencode CLI, free, no auth needed
  - Ollama local models — via API, free, runs on host GPU
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from nanobot.agent.tools.base import Tool

# ---------------------------------------------------------------------------
# Friend registry
# ---------------------------------------------------------------------------

@dataclass
class Friend:
    name: str
    provider: str       # "claude", "opencode", "ollama"
    model: str          # model identifier for the provider
    intelligence: str   # "expert", "strong", "capable", "basic"
    cost: str           # "paid", "free"
    skills: str         # what this friend is good at
    speed: str          # "slow", "medium", "fast"


# Friends are checked for availability at call time
_FRIENDS: list[Friend] = [
    # Claude (highest capability, paid, rate-limited)
    Friend(
        name="claude-opus",
        provider="claude",
        model="claude-opus-4-5-20250514",
        intelligence="expert",
        cost="paid (rate-limited)",
        skills="Deep reasoning, architecture, complex code review, planning",
        speed="slow",
    ),
    Friend(
        name="claude-sonnet",
        provider="claude",
        model="claude-sonnet-4-5-20250514",
        intelligence="expert",
        cost="paid (rate-limited)",
        skills="Strong all-rounder, code generation, analysis, fast for its tier",
        speed="medium",
    ),
    # OpenCode free models (no auth, good for quick reasoning)
    Friend(
        name="nemotron",
        provider="opencode",
        model="opencode/nemotron-3-super-free",
        intelligence="strong",
        cost="free",
        skills="General reasoning, code, math, instruction following",
        speed="medium",
    ),
    Friend(
        name="big-pickle",
        provider="opencode",
        model="opencode/big-pickle",
        intelligence="strong",
        cost="free",
        skills="General purpose, good reasoning, code generation",
        speed="medium",
    ),
    Friend(
        name="mimo-pro",
        provider="opencode",
        model="opencode/mimo-v2-pro-free",
        intelligence="capable",
        cost="free",
        skills="Code generation, programming tasks, debugging",
        speed="fast",
    ),
    Friend(
        name="minimax",
        provider="opencode",
        model="opencode/minimax-m2.5-free",
        intelligence="capable",
        cost="free",
        skills="General reasoning, writing, summarization",
        speed="fast",
    ),
]

_OLLAMA_URL = "http://host.docker.internal:11434"

def _get_ollama_friends() -> list[Friend]:
    """Discover models available via Ollama on the host."""
    try:
        resp = httpx.get(f"{_OLLAMA_URL}/api/tags", timeout=3)
        models = resp.json().get("models", [])
        friends = []
        for m in models:
            name = m["name"]
            # Skip embedding models
            if "embed" in name.lower():
                continue
            size = m.get("size", 0) / 1e9
            friends.append(Friend(
                name=f"ollama-{name.split(':')[0]}",
                provider="ollama",
                model=name,
                intelligence="capable" if size < 10 else "strong",
                cost="free (local)",
                skills=f"Local model ({size:.1f}GB), fast inference on host GPU",
                speed="fast",
            ))
        return friends
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Calling friends
# ---------------------------------------------------------------------------

_TIMEOUT = 120  # seconds


async def _call_claude(model: str, prompt: str) -> str:
    """Call Claude via CLI."""
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "json",
        "--max-turns", "3",
        "--model", model.replace("claude-", ""),
        "--dangerously-skip-permissions",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/sandbox",
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        return f"Error: Claude exited {proc.returncode}: {err[:300]}"
    raw = stdout.decode(errors="replace").strip()
    try:
        return json.loads(raw).get("result", raw)
    except json.JSONDecodeError:
        return raw


async def _call_opencode(model: str, prompt: str) -> str:
    """Call an OpenCode free model via CLI."""
    cmd = ["opencode", "run", "--model", model, prompt]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd="/sandbox",
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        return f"Error: OpenCode exited {proc.returncode}: {err[:300]}"
    # OpenCode output has ANSI codes, strip them
    import re
    raw = stdout.decode(errors="replace").strip()
    raw = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    # Remove the "> build · model" header line
    lines = raw.split("\n")
    lines = [l for l in lines if not l.strip().startswith("> build")]
    return "\n".join(lines).strip()


async def _call_ollama(model: str, prompt: str) -> str:
    """Call an Ollama model via API."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{_OLLAMA_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class PhoneAFriendTool(Tool):
    """Call another LLM for help when things get difficult."""

    @property
    def name(self) -> str:
        return "phone_a_friend"

    @property
    def description(self) -> str:
        # Build dynamic friend list so agent sees what's available
        all_friends = _FRIENDS + _get_ollama_friends()
        # Filter claude friends by availability
        has_claude = bool(os.environ.get("ANTHROPIC_API_KEY"))
        available = [
            f for f in all_friends
            if f.provider != "claude" or has_claude
        ]
        friend_lines = []
        for f in available:
            friend_lines.append(
                f"  {f.name} [{f.intelligence}] ({f.cost}, {f.speed}) — {f.skills}"
            )
        roster = "\n".join(friend_lines) if friend_lines else "  (none available)"
        return (
            f"Call another AI model for help when you're stuck, need deeper reasoning, "
            f"or want a second opinion. Pick the right friend for the task.\n"
            f"Available friends:\n{roster}"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "friend": {
                    "type": "string",
                    "description": "Name of the friend to call (e.g. 'nemotron', 'claude-sonnet', 'big-pickle').",
                },
                "prompt": {
                    "type": "string",
                    "description": "The question or task for your friend. Be specific and include context.",
                },
            },
            "required": ["friend", "prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        friend_name = kwargs["friend"]
        prompt = kwargs["prompt"]

        # Find the friend
        all_friends = _FRIENDS + _get_ollama_friends()
        friend = next((f for f in all_friends if f.name == friend_name), None)
        if not friend:
            available = ", ".join(f.name for f in all_friends)
            return f"Error: Unknown friend '{friend_name}'. Available: {available}"

        # Check auth for paid providers
        if friend.provider == "claude" and not os.environ.get("ANTHROPIC_API_KEY"):
            return "Error: Claude is not available (no credentials). Try a free friend instead."

        # Call the friend
        t0 = time.monotonic()
        try:
            if friend.provider == "claude":
                result = await _call_claude(friend.model, prompt)
            elif friend.provider == "opencode":
                result = await _call_opencode(friend.model, prompt)
            elif friend.provider == "ollama":
                result = await _call_ollama(friend.model, prompt)
            else:
                return f"Error: Unknown provider '{friend.provider}'."
        except asyncio.TimeoutError:
            return f"Error: {friend.name} timed out after {_TIMEOUT}s."
        except Exception as exc:
            return f"Error calling {friend.name}: {exc}"

        duration = time.monotonic() - t0

        # Truncate long responses
        if len(result) > 10000:
            result = result[:10000] + "\n\n[... truncated]"

        return f"[{friend.name} responded in {duration:.1f}s]\n\n{result}"
