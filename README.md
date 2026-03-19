<p align="center">
  <img src="https://i.ibb.co/chYFB702/proto-Claw.jpg" alt="protoClaw" width="600" />
</p>

# protoClaw

Sandboxed AI agent powered by local LLMs. Built on [nanobot](https://github.com/HKUDS/nanobot) with [NemoClaw](https://github.com/NVIDIA/NemoClaw)-inspired container security.

## What it does

Runs nanobot + OpenCode inside a hardened Docker container, connected to a local vLLM instance. The agent can execute code, search the web, read/write files — all confined to a sandbox with multi-layer security. Optionally switch to Claude models at runtime via [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI) OAuth proxy.

## Architecture

```
┌──────────────────── Sandbox Container ────────────────────┐
│                                                            │
│  ┌─────────┐  ┌──────────┐  ┌─────────────┐              │
│  │ nanobot  │  │ OpenCode │  │ CLIProxyAPI  │              │
│  │ (agent)  │  │ (coding) │  │ (Claude OAuth│              │
│  └────┬─────┘  └────┬─────┘  │  proxy :8317)│              │
│       │              │        └──────┬───────┘              │
│       │              │               │                      │
│  Read-only rootfs · seccomp · no-new-privileges            │
│  Dropped capabilities · non-root user · tmpfs workspace    │
└───────┼──────────────┼───────────────┼─────────────────────┘
        │              │               │
        ▼              ▼               ▼
   ┌────────────────┐          ┌─────────────────┐
   │ vLLM (host)    │          │ api.anthropic.com│
   │ :8000          │          │ (via OAuth)      │
   └────────────────┘          └─────────────────┘
```

## Security layers

| Layer | Mechanism | Source |
|-------|-----------|--------|
| Syscall filtering | seccomp whitelist | NemoClaw |
| Privilege escalation | `no-new-privileges`, all caps dropped | NemoClaw |
| Filesystem | Read-only root, tmpfs workspace | NemoClaw |
| Process isolation | Non-root `sandbox` user (uid 1001) | NemoClaw |
| Shell commands | Deny patterns (rm -rf, dd, etc.) | nanobot |
| Network (SSRF) | Blocks private/internal IPs | nanobot |
| Path traversal | `restrictToWorkspace` blocks escape | nanobot |
| Resource limits | 4 CPU, 4GB RAM | Docker |

## Quick start

**Prerequisites:** Docker, vLLM serving a model with tool-call support on port 8000.

```bash
# Clone with submodule (required — nanobot is a git submodule)
git clone --recurse-submodules https://github.com/protoLabsAI/protoClaw.git
cd protoClaw

# If you already cloned without --recurse-submodules:
git submodule update --init --recursive

# Build and run
docker compose up -d --build

# UI available at http://localhost:7865
```

### vLLM tool-call parser

protoClaw uses vLLM's tool-calling interface. You must start vLLM with the correct parser for your model:

| Model | Parser flag |
|-------|------------|
| Qwen 3.5 (all sizes) | `--enable-auto-tool-choice --tool-call-parser qwen3_xml` |
| OmniCoder | None (uses custom `OmniCoderProvider` with XML format) |

Example for Qwen 3.5-35B:
```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 --port 8000 \
  --enable-auto-tool-choice --tool-call-parser qwen3_xml \
  --max-model-len 65536
```

### Claude model switching (optional)

The Gradio settings sidebar lets you switch between local vLLM and Claude models at runtime. Claude access requires [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI), which proxies your Claude Code OAuth subscription into an OpenAI-compatible API.

**One-time setup:**

```bash
# 1. Authenticate (opens browser for OAuth)
docker exec -it protoclaw bash /opt/protoclaw/scripts/claude-login.sh

# 2. If browsing remotely (e.g. via Tailscale), set the callback host:
#    Add to .env or docker-compose environment:
#    CLIPROXY_CALLBACK_HOST=<your-reachable-ip>
#
# 3. If the callback URL hits the wrong host, paste it into the container:
docker exec protoclaw curl -s "http://127.0.0.1:54545/callback?code=<CODE>&state=<STATE>"
```

Auth persists in the `protoclaw-cliproxy` Docker volume across restarts. No API key needed — uses your existing Claude subscription.

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
- **Claude** — available if `ANTHROPIC_API_KEY` is set (via env var or CLI OAuth credentials mounted from host `~/.claude/`). Uses Claude Code CLI in headless mode.

### PWA support

protoClaw is installable as a Progressive Web App. Open `http://<host>:7865` in Chrome/Edge and click "Install" in the address bar. Includes offline fallback page and dark theme with indigo accents.

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

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | _(empty)_ | Anthropic API key. Auto-extracted from mounted `~/.claude/` OAuth credentials if not set. |
| `CLAUDE_OAUTH_CREDENTIALS` | _(empty)_ | macOS: raw JSON from Keychain (via `scripts/get-claude-token.sh`) |
| `CLIPROXY_CALLBACK_HOST` | `localhost` | Hostname/IP for CLIProxyAPI OAuth callback URL. Set to your machine's reachable address for remote access. |
| `PROTOCLAW_ENV` | _(empty)_ | Set to `production` for production mode logging |

## License

MIT
