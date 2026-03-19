<p align="center">
  <img src="https://i.ibb.co/chYFB702/proto-Claw.jpg" alt="protoClaw" width="600" />
</p>

# protoClaw

Sandboxed AI agent powered by local LLMs. Built on [nanobot](https://github.com/HKUDS/nanobot) with [NemoClaw](https://github.com/NVIDIA/NemoClaw)-inspired container security.

## What it does

Runs nanobot + OpenCode inside a hardened Docker container, connected to a local vLLM instance. The agent can execute code, search the web, read/write files — all confined to a sandbox with multi-layer security.

## Architecture

```
┌─────────────────── Sandbox Container ───────────────────┐
│                                                          │
│  ┌─────────┐     ┌──────────┐     ┌─────────────────┐  │
│  │ nanobot  │     │ OpenCode │     │  /sandbox       │  │
│  │ (agent)  │     │ (coding) │     │  (workspace)    │  │
│  └────┬─────┘     └────┬─────┘     └─────────────────┘  │
│       │                │                                  │
│  Read-only rootfs · seccomp · no-new-privileges          │
│  Dropped capabilities · non-root user · tmpfs workspace  │
└───────┼────────────────┼────────────────────────────────┘
        │                │
        ▼                ▼
   ┌─────────────────────────────┐
   │  vLLM (host) :8000          │
   │  OmniCoder-9B (262K ctx)    │
   └─────────────────────────────┘
```

## Security layers

| Layer | Mechanism | Source |
|-------|-----------|--------|
| Syscall filtering | seccomp whitelist | NemoClaw |
| Privilege escalation | `no-new-privileges`, all caps dropped | NemoClaw |
| Filesystem | Read-only root, tmpfs workspace | NemoClaw |
| Process isolation | Non-root `sandbox` user (uid 1000) | NemoClaw |
| Shell commands | Deny patterns (rm -rf, dd, etc.) | nanobot |
| Network (SSRF) | Blocks private/internal IPs | nanobot |
| Path traversal | `restrictToWorkspace` blocks escape | nanobot |
| Resource limits | 4 CPU, 4GB RAM | Docker |

## Quick start

**Prerequisites:** Docker, vLLM serving OmniCoder-9B on port 8000.

```bash
# Clone with submodule (required — nanobot is a git submodule)
git clone --recurse-submodules https://github.com/protoLabsAI/protoClaw.git
cd protoClaw

# If you already cloned without --recurse-submodules:
git submodule update --init --recursive

# Build
docker build -t protoclaw .

# Run interactive agent
docker run --rm -it \
  --security-opt no-new-privileges:true \
  --security-opt seccomp=seccomp-profile.json \
  --cap-drop ALL --cap-add NET_RAW \
  --read-only \
  --tmpfs /tmp:size=512M,uid=1000,gid=1000 \
  --tmpfs /run:size=64M \
  --tmpfs /sandbox:size=256M,uid=1000,gid=1000 \
  --tmpfs /home/sandbox/.nanobot:size=64M,uid=1000,gid=1000 \
  -v ./config/nanobot-config.json:/home/sandbox/.nanobot/config.json:ro \
  --add-host host.docker.internal:host-gateway \
  protoclaw

# Or use docker-compose
docker compose up
```

## Tools

Tools are registered at startup in `server.py`. Each loads conditionally based on available dependencies.

| Tool | Source | Condition | Description |
|------|--------|-----------|-------------|
| **Shell, Files, Web** | nanobot built-in | Always | exec, read/write/edit files, web search/fetch |
| **Browser** | `tools/browser.py` | Always | Web automation via agent-browser CLI — open, snapshot, click, fill, find. Chrome profile uses `/tmp` (512MB) |
| **Memory** | `tools/vector_memory.py` | Always (graceful fallback) | Semantic vector search via Ollama `nomic-embed-text` + `sqlite-vec`. Silent if Ollama unreachable |
| **Beads** | `tools/beads.py` | Always | Issue tracking via [beads](https://github.com/Dicklesworthstone/beads_rust) `br` CLI — create, query, close issues with dependency-driven ready queue |
| **Phone a Friend** | `tools/phone_a_friend.py` | Always | Call other AI models: Claude (paid), OpenCode free models, Ollama local. Agent sees roster with intelligence/cost/speed |
| **Audit** | `audit.py` | Always | JSONL logging of all tool executions (not a tool itself, wraps `ToolRegistry.execute`) |

### Phone a Friend auth

The `phone_a_friend` tool always loads. Provider availability:

- **OpenCode free models** — always available, no auth needed
- **Ollama** — available if Ollama is running on the host (auto-discovered)
- **Claude** — available if `ANTHROPIC_API_KEY` is set (via env var or CLI OAuth credentials mounted from host `~/.claude/`)

### Adding MCP servers at runtime

```
/mcp                                          # list connected servers + tools
/mcp add myserver {"command": "npx", "args": ["@org/mcp-server"]}
/mcp remove myserver
```

Changes persist to `nanobot-config.json`. MCP tools appear as `mcp_<server>_<tool>`.

### Slash commands

| Command | Description |
|---------|-------------|
| `/new` | Clear chat + nanobot session |
| `/clear` | Clear chat display (session preserved) |
| `/think <level>` | Set reasoning effort (low/medium/high/off) |
| `/compact` | Force memory consolidation |
| `/model` | Show current model |
| `/tools` | List registered tools |
| `/audit [n]` | Show recent audit log |
| `/mcp` | Manage MCP servers |
| `/beads [cmd]` | Quick issue queries (ready/list/stats/blocked) |
| `/help` | Show command list |

## Configuration

Edit `config/nanobot-config.json` to change the model, provider, MCP servers, or tools. Edit `config/opencode.json` for OpenCode settings. Both point to `host.docker.internal:8000` by default.

## Custom providers

The `providers/` directory contains custom LLM provider modules that are patched into nanobot at build time. Currently includes `omnicoder_provider.py` which handles OmniCoder's XML-style tool call format.

## License

MIT
