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
# Clone with submodule
git clone --recurse-submodules https://github.com/protoLabsAI/protoClaw.git
cd protoClaw

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

## Configuration

Edit `config/nanobot-config.json` to change the model, provider, or tools. Edit `config/opencode.json` for OpenCode settings. Both point to `host.docker.internal:8000` by default.

## Custom providers

The `providers/` directory contains custom LLM provider modules that are patched into nanobot at build time. Currently includes `omnicoder_provider.py` which handles OmniCoder's XML-style tool call format.

## License

MIT
