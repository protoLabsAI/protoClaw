#!/bin/bash
# Start both protoClaw Gradio UI and OpenCode web UI

# --- Production mode detection ---
PROD_MODE=0
if [ "${PROTOCLAW_ENV}" = "production" ]; then
    PROD_MODE=1
    echo "[entrypoint] Running in PRODUCTION mode"
    # Validate required MCP env vars in prod
    if [ -z "${AUTOMAKER_API_URL}" ]; then
        echo "[entrypoint] WARNING: AUTOMAKER_API_URL is not set"
    fi
    if [ -z "${AUTOMAKER_API_KEY}" ]; then
        echo "[entrypoint] WARNING: AUTOMAKER_API_KEY is not set"
    fi
else
    echo "[entrypoint] Running in DEVELOPMENT mode"
fi

# Create dirs inside tmpfs home (tmpfs wipes everything)
mkdir -p /home/sandbox/.nanobot /home/sandbox/.config/opencode /home/sandbox/.local

# Claude credentials — two paths:
# 1. macOS: CLAUDE_OAUTH_CREDENTIALS env var (extracted from Keychain via scripts/get-claude-token.sh)
# 2. Linux: mounted ~/.claude/.credentials.json at /opt/claude-creds/
mkdir -p /home/sandbox/.claude

if [ -n "$CLAUDE_OAUTH_CREDENTIALS" ]; then
    # macOS path: write Keychain-extracted credentials to file
    echo "$CLAUDE_OAUTH_CREDENTIALS" > /home/sandbox/.claude/.credentials.json
    chmod 600 /home/sandbox/.claude/.credentials.json
    echo "[entrypoint] Claude credentials loaded from CLAUDE_OAUTH_CREDENTIALS env"
elif [ -f /opt/claude-creds/.credentials.json ]; then
    # Linux path: copy from mounted volume
    cp /opt/claude-creds/.credentials.json /home/sandbox/.claude/.credentials.json
    chmod 600 /home/sandbox/.claude/.credentials.json
    echo "[entrypoint] Claude credentials loaded from mounted volume"
fi

# Export OAuth token as ANTHROPIC_API_KEY if not already set
if [ -z "$ANTHROPIC_API_KEY" ] && [ -f /home/sandbox/.claude/.credentials.json ]; then
    TOKEN=$(python3 -c "import json; d=json.load(open('/home/sandbox/.claude/.credentials.json')); print(d.get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null)
    if [ -n "$TOKEN" ]; then
        export ANTHROPIC_API_KEY="$TOKEN"
        echo "[entrypoint] Exported OAuth token as ANTHROPIC_API_KEY"
    fi
fi

# Ensure persistent volume dirs exist with correct ownership
mkdir -p /sandbox/audit /sandbox/memory

# Copy configs from mounted read-only location
cp /opt/protoclaw/config/nanobot-config.json /home/sandbox/.nanobot/config.json
cp /opt/protoclaw/config/opencode.json /home/sandbox/.config/opencode/opencode.json

# Copy persona into workspace (nanobot reads SOUL.md from workspace)
mkdir -p /sandbox
cp /opt/protoclaw/config/SOUL.md /sandbox/SOUL.md

# Copy skills into workspace (nanobot reads skills/ from workspace)
cp -r /opt/protoclaw/skills /sandbox/skills

# Initialize beads issue tracker (persistent via /opt/.beads volume)
ln -sf /opt/.beads /sandbox/.beads
if [ ! -f /opt/.beads/beads.db ]; then
    cd /sandbox && br init 2>/dev/null || true
fi

# Start CLIProxyAPI in background (OpenAI-compatible proxy for Claude OAuth)
# OAuth tokens persist in /opt/.cliproxy volume
# First run: visit http://localhost:8317 to authenticate via browser
mkdir -p /opt/.cliproxy
cp /opt/protoclaw/config/cliproxy-config.yaml /opt/.cliproxy/config.yaml
cli-proxy-api --config /opt/.cliproxy/config.yaml &
echo "[entrypoint] CLIProxyAPI started on port 8317"

# Configure summarize CLI to use Anthropic by default
mkdir -p /home/sandbox/.summarize
echo '{"model": "anthropic/claude-sonnet-4-5-20250514"}' > /home/sandbox/.summarize/config.json

# Start OpenCode web UI in background on port 7866
opencode web --port 7866 --hostname 0.0.0.0 &

# Start protoClaw Gradio UI in foreground on port 7865
exec python /opt/protoclaw/server.py --config /home/sandbox/.nanobot/config.json
