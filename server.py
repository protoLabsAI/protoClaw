"""
protoClaw Gradio UI — chat interface for nanobot agent with tool-use visualization.

Usage:
    python server.py                          # default port 7865
    python server.py --port 7870              # custom port
    python server.py --config path/to/config  # custom config
"""

import argparse
import asyncio
import contextvars
import json
import re
import time
from pathlib import Path
from typing import Any

from chat_ui import create_chat_app

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

_agent = None
_config = None


def _init_agent(config_path: str | None = None):
    """Initialize nanobot agent loop (called once at startup)."""
    global _agent, _config

    from nanobot.config.loader import load_config, set_config_path
    from nanobot.config.paths import get_cron_dir
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.cron.service import CronService
    from nanobot.utils.helpers import sync_workspace_templates

    if config_path:
        p = Path(config_path).expanduser().resolve()
        set_config_path(p)

    _config = load_config(Path(config_path) if config_path else None)
    sync_workspace_templates(_config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(_config)

    cron = CronService(get_cron_dir() / "jobs.json")

    _agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=_config.workspace_path,
        model=None,  # auto-detected from provider
        max_iterations=_config.agents.defaults.max_tool_iterations,
        context_window_tokens=_config.agents.defaults.context_window_tokens,
        web_search_config=_config.tools.web.search,
        web_proxy=_config.tools.web.proxy or None,
        exec_config=_config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=_config.tools.restrict_to_workspace,
        mcp_servers=_config.tools.mcp_servers,
        channels_config=_config.channels,
    )


def _detect_vllm_model(api_base: str) -> str | None:
    """Query vLLM /v1/models to get the currently loaded model."""
    import httpx
    try:
        resp = httpx.get(f"{api_base}/models", timeout=5)
        data = resp.json().get("data", [])
        if data:
            return data[0]["id"]
    except Exception:
        pass
    return None


def _make_provider(config):
    """Create provider — auto-detects vLLM model, uses OmniCoder provider when needed."""
    from nanobot.providers.base import GenerationSettings
    from nanobot.providers.litellm_provider import LiteLLMProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)
    api_base = config.get_api_base(model)

    # Auto-detect model from vLLM if configured as "auto" or if we can reach the endpoint
    if api_base and (model == "auto" or provider_name in ("vllm", "ollama")):
        detected = _detect_vllm_model(api_base)
        if detected:
            model = detected

    provider_cls = LiteLLMProvider
    if "omnicoder" in model.lower():
        from nanobot.providers.omnicoder_provider import OmniCoderProvider
        provider_cls = OmniCoderProvider

    provider = provider_cls(
        api_key=p.api_key if p else None,
        api_base=api_base,
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


# ---------------------------------------------------------------------------
# Session commands
# ---------------------------------------------------------------------------

_HELP_TEXT = """\
**protoClaw commands:**
| Command | Description |
|---------|-------------|
| `/new` | Clear chat history + nanobot session |
| `/clear` | Clear chat display (session preserved) |
| `/think <level>` | Set reasoning effort (low/medium/high/off) |
| `/compact` | Force memory consolidation |
| `/model` | Show current model |
| `/tools` | List registered tools |
| `/audit [n]` | Show recent audit log entries |
| `/mcp` | List connected MCP servers |
| `/mcp add <name> <json>` | Add an MCP server at runtime |
| `/mcp remove <name>` | Remove an MCP server |
| `/beads [cmd]` | Quick beads issue tracker (list/ready/stats) |
| `/help` | Show this help |
"""

_THINK_LEVELS = {"low", "medium", "high", "off"}


def _msg(content: str) -> list[dict[str, Any]]:
    """Wrap a string as a single assistant message list."""
    return [{"role": "assistant", "content": content}]


async def _handle_command(cmd: str, args: str, session_id: str) -> list[dict[str, Any]] | None:
    """Handle a slash command. Returns message list, or None if not a command."""
    if cmd == "help":
        return _msg(_HELP_TEXT)

    if cmd == "clear":
        return [{"role": "assistant", "content": "", "metadata": {"_clear": True}}]

    if cmd == "new":
        session_key = f"gradio:{session_id}"
        session = _agent.sessions.get_or_create(session_key)
        session.clear()
        _agent.sessions.save(session)
        return [{"role": "assistant", "content": "", "metadata": {"_new": True}}]

    if cmd == "model":
        return _msg(f"**Model:** `{_agent.model}`")

    if cmd == "tools":
        names = _agent.tools.tool_names
        listing = "\n".join(f"- `{n}`" for n in sorted(names))
        return _msg(f"**Registered tools ({len(names)}):**\n{listing}")

    if cmd == "think":
        level = args.strip().lower()
        if level not in _THINK_LEVELS:
            return _msg(f"Invalid level. Use one of: {', '.join(sorted(_THINK_LEVELS))}")
        val = None if level == "off" else level
        _agent.provider.generation.reasoning_effort = val
        return _msg(f"Reasoning effort set to **{level}**.")

    if cmd == "compact":
        session_key = f"gradio:{session_id}"
        session = _agent.sessions.get_or_create(session_key)
        await _agent.memory_consolidator.maybe_consolidate_by_tokens(session)
        return _msg("Memory consolidation complete.")

    if cmd == "audit":
        from audit import audit_logger
        n = 20
        if args.strip().isdigit():
            n = int(args.strip())
        entries = audit_logger.get_recent(n, session_id=session_id)
        if not entries:
            return _msg("No audit entries found.")
        lines = []
        for e in entries:
            status = "ok" if e.get("success") else "FAIL"
            lines.append(
                f"- `{e['ts'][:19]}` **{e['tool']}** ({e['duration_ms']}ms) [{status}] — {e.get('result_summary', '')[:80]}"
            )
        return _msg(f"**Recent audit log ({len(entries)} entries):**\n" + "\n".join(lines))

    if cmd == "mcp":
        return await _handle_mcp_command(args)

    if cmd == "beads":
        return await _handle_beads_command(args)

    return None


# ---------------------------------------------------------------------------
# /mcp subcommands — runtime MCP server management
# ---------------------------------------------------------------------------

_config_path = None  # Path | None, set in main


async def _handle_mcp_command(args: str) -> list[dict[str, Any]]:
    """Handle /mcp list|add|remove subcommands."""
    parts = args.strip().split(None, 1)
    subcmd = parts[0] if parts else ""
    rest = parts[1] if len(parts) > 1 else ""

    if not subcmd or subcmd == "list":
        # List connected MCP servers and their tools
        mcp_servers = _agent._mcp_servers or {}
        if not mcp_servers:
            return _msg("No MCP servers configured.")
        lines = []
        for name, cfg in mcp_servers.items():
            stype = getattr(cfg, "type", None) or "auto"
            # Find tools registered from this server
            prefix = f"mcp_{name}_"
            tools = [t for t in _agent.tools.tool_names if t.startswith(prefix)]
            tool_list = ", ".join(f"`{t}`" for t in tools) if tools else "(no tools connected)"
            lines.append(f"**{name}** ({stype}): {tool_list}")
        return _msg("**MCP Servers:**\n" + "\n".join(lines))

    if subcmd == "add":
        # /mcp add <name> {"command": "...", "args": [...]}
        add_parts = rest.split(None, 1)
        if len(add_parts) < 2:
            return _msg("Usage: `/mcp add <name> <json-config>`\n\nExample: `/mcp add myserver {\"command\": \"npx\", \"args\": [\"@org/mcp-server\"]}`")
        name, config_json = add_parts
        try:
            raw = json.loads(config_json)
        except json.JSONDecodeError as e:
            return _msg(f"Invalid JSON: {e}")

        # Build MCPServerConfig from raw dict
        from nanobot.config.schema import MCPServerConfig
        try:
            mcp_cfg = MCPServerConfig(**raw)
        except Exception as e:
            return _msg(f"Invalid MCP config: {e}")

        # Add to agent's MCP servers and connect
        if _agent._mcp_servers is None:
            _agent._mcp_servers = {}
        _agent._mcp_servers[name] = mcp_cfg

        # Connect the new server
        from nanobot.agent.tools.mcp import connect_mcp_servers
        try:
            await connect_mcp_servers({name: mcp_cfg}, _agent.tools, _agent._mcp_stack)
        except Exception as e:
            _agent._mcp_servers.pop(name, None)
            return _msg(f"Failed to connect `{name}`: {e}")

        # Persist to config file
        _persist_mcp_config()

        new_tools = [t for t in _agent.tools.tool_names if t.startswith(f"mcp_{name}_")]
        tool_list = ", ".join(f"`{t}`" for t in new_tools) if new_tools else "(no tools)"
        return _msg(f"Added MCP server **{name}**. Tools: {tool_list}")

    if subcmd == "remove":
        name = rest.strip()
        if not name:
            return _msg("Usage: `/mcp remove <name>`")

        if not _agent._mcp_servers or name not in _agent._mcp_servers:
            return _msg(f"MCP server `{name}` not found.")

        # Unregister tools from this server
        prefix = f"mcp_{name}_"
        to_remove = [t for t in _agent.tools.tool_names if t.startswith(prefix)]
        for t in to_remove:
            _agent.tools.unregister(t)

        _agent._mcp_servers.pop(name)
        _persist_mcp_config()

        removed = ", ".join(f"`{t}`" for t in to_remove) if to_remove else "(none)"
        return _msg(f"Removed MCP server **{name}**. Unregistered tools: {removed}")

    return _msg("Unknown subcommand. Use `/mcp`, `/mcp add <name> <json>`, or `/mcp remove <name>`.")


def _persist_mcp_config():
    """Write current MCP server config back to the config JSON file."""
    if not _config_path:
        return
    try:
        config_data = json.loads(_config_path.read_text())
        serialized = {}
        for name, cfg in (_agent._mcp_servers or {}).items():
            entry = {}
            if cfg.type:
                entry["type"] = cfg.type
            if cfg.command:
                entry["command"] = cfg.command
            if cfg.args:
                entry["args"] = cfg.args
            if cfg.env:
                entry["env"] = cfg.env
            if cfg.url:
                entry["url"] = cfg.url
            if cfg.headers:
                entry["headers"] = cfg.headers
            if cfg.tool_timeout != 30:
                entry["toolTimeout"] = cfg.tool_timeout
            if cfg.enabled_tools != ["*"]:
                entry["enabledTools"] = cfg.enabled_tools
            serialized[name] = entry
        config_data["tools"]["mcpServers"] = serialized
        _config_path.write_text(json.dumps(config_data, indent=2) + "\n")
    except Exception:
        pass  # Non-critical — runtime state is authoritative


# ---------------------------------------------------------------------------
# /beads — quick access to beads issue tracker
# ---------------------------------------------------------------------------

async def _handle_beads_command(args: str) -> list[dict[str, Any]]:
    """Run a beads CLI command and return formatted output."""
    subcmd = args.strip() or "ready"

    # Whitelist safe read-only commands for quick access
    safe_cmds = {"list", "ready", "blocked", "stats", "stale"}
    cmd_parts = subcmd.split()
    if cmd_parts[0] not in safe_cmds:
        return _msg(
            f"Quick commands: {', '.join(sorted(safe_cmds))}.\n"
            "For mutations (create/update/close), use the beads MCP tools directly."
        )

    try:
        proc = await asyncio.create_subprocess_exec(
            "br", *cmd_parts, "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/sandbox",
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
    except asyncio.TimeoutError:
        return _msg("Beads command timed out.")
    except FileNotFoundError:
        return _msg("Error: `br` not installed.")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace").strip()
        return _msg(f"Beads error: {err[:300]}")

    raw = stdout.decode(errors="replace").strip()
    if not raw:
        return _msg("No results.")

    # Format JSON output into readable markdown
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            if not data:
                return _msg("No issues found.")
            lines = []
            for issue in data[:20]:
                status = issue.get("status", "?")
                priority = issue.get("priority", "?")
                title = issue.get("title", "untitled")
                iid = issue.get("id", "?")
                lines.append(f"- `{iid}` [{status}] P{priority} — {title}")
            return _msg(f"**Beads ({len(data)} issues):**\n" + "\n".join(lines))
        else:
            # Stats or single object
            return _msg(f"```json\n{json.dumps(data, indent=2)}\n```")
    except json.JSONDecodeError:
        return _msg(f"```\n{raw[:2000]}\n```")


# ---------------------------------------------------------------------------
# Audit logging — wraps ToolRegistry.execute
# ---------------------------------------------------------------------------

_current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "_current_session_id", default=""
)


def _install_audit_wrapper():
    """Monkey-patch _agent.tools.execute to log tool calls."""
    from audit import audit_logger

    original_execute = _agent.tools.execute

    async def _audited_execute(name: str, params: dict[str, Any]) -> str:
        session_id = _current_session_id.get("")
        t0 = time.monotonic()
        try:
            result = await original_execute(name, params)
            duration_ms = int((time.monotonic() - t0) * 1000)
            success = not (isinstance(result, str) and result.startswith("Error"))
            audit_logger.log(
                session_id=session_id,
                tool=name,
                args=params,
                result_summary=result[:200] if isinstance(result, str) else str(result)[:200],
                duration_ms=duration_ms,
                success=success,
            )
            return result
        except Exception as exc:
            duration_ms = int((time.monotonic() - t0) * 1000)
            audit_logger.log(
                session_id=session_id,
                tool=name,
                args=params,
                result_summary=str(exc)[:200],
                duration_ms=duration_ms,
                success=False,
            )
            raise

    _agent.tools.execute = _audited_execute


# ---------------------------------------------------------------------------
# Chat function
# ---------------------------------------------------------------------------

def _strip_think(text: str) -> str:
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    text = re.sub(r"</think>\s*", "", text)
    return text.strip()


async def chat(message: str, session_id: str) -> list[dict[str, Any]]:
    """Process a message through nanobot's agent loop."""
    # Handle slash commands before hitting the agent
    stripped = message.strip()
    if stripped.startswith("/"):
        parts = stripped.split(None, 1)
        cmd = parts[0][1:].lower()
        args = parts[1] if len(parts) > 1 else ""
        result = await _handle_command(cmd, args, session_id)
        if result is not None:
            return result

    # Set session context for audit logging
    token = _current_session_id.set(session_id)
    try:
        progress_messages: list[dict] = []

        async def on_progress(content: str, *, tool_hint: bool = False) -> None:
            content = _strip_think(content)
            if not content:
                return
            if tool_hint:
                progress_messages.append({
                    "role": "assistant",
                    "metadata": {"title": f"🔧 {content}"},
                    "content": "",
                })
            else:
                progress_messages.append({
                    "role": "assistant",
                    "metadata": {"title": "💭 Thinking"},
                    "content": content,
                })

        response = await _agent.process_direct(
            content=message,
            session_key=f"gradio:{session_id}",
            channel="gradio",
            chat_id=session_id,
            on_progress=on_progress,
        )

        response = _strip_think(response or "")
        return [*progress_messages, {"role": "assistant", "content": response}]
    finally:
        _current_session_id.reset(token)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def _main():
    global _config_path

    parser = argparse.ArgumentParser(description="protoClaw Gradio UI")
    parser.add_argument("--port", type=int, default=7865)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    _init_agent(args.config)

    # Track config path for /mcp persistence
    if args.config:
        _config_path = Path(args.config).expanduser().resolve()

    # Install audit logging wrapper
    _install_audit_wrapper()

    # Register vector memory (silent if Ollama unavailable)
    from tools.vector_memory import VectorMemory
    _vector_memory = VectorMemory()
    _agent.tools.register(_vector_memory.as_tool())

    # Register Claude Code tool only if credentials exist
    from tools.claude import ClaudeTool, is_claude_available
    if is_claude_available():
        _agent.tools.register(ClaudeTool())
    else:
        print("Claude tool: skipped (no credentials found)")

    model_name = _agent.model

    app = create_chat_app(
        chat_fn=chat,
        title="🦀 protoClaw",
        subtitle=f"`{model_name}` · sandboxed agent",
        placeholder="Ask protoClaw anything...",
    )

    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    _main()
