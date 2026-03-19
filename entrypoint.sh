#!/bin/bash
# Start both protoClaw Gradio UI and OpenCode web UI

# Create dirs inside tmpfs home (tmpfs wipes everything)
mkdir -p /home/sandbox/.nanobot /home/sandbox/.config/opencode /home/sandbox/.local

# Copy host Claude credentials if mounted (for CLI OAuth fallback)
# Can't symlink because tmpfs at /home/sandbox is created after bind mounts
if [ -f /opt/claude-creds/.credentials.json ]; then
    mkdir -p /home/sandbox/.claude
    cp /opt/claude-creds/.credentials.json /home/sandbox/.claude/.credentials.json
    chmod 600 /home/sandbox/.claude/.credentials.json

    # Export OAuth token as ANTHROPIC_API_KEY if not already set
    # This lets summarize CLI, claude CLI, and other tools use it
    if [ -z "$ANTHROPIC_API_KEY" ]; then
        TOKEN=$(python3 -c "import json; d=json.load(open('/home/sandbox/.claude/.credentials.json')); print(d.get('claudeAiOauth',{}).get('accessToken',''))" 2>/dev/null)
        if [ -n "$TOKEN" ]; then
            export ANTHROPIC_API_KEY="$TOKEN"
        fi
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

# Initialize beads issue tracker if not already present
if [ ! -d /sandbox/.beads ]; then
    cd /sandbox && br init 2>/dev/null || true
fi

# Configure summarize CLI to use Anthropic by default
mkdir -p /home/sandbox/.summarize
echo '{"model": "anthropic/claude-sonnet-4-5-20250514"}' > /home/sandbox/.summarize/config.json

# Start OpenCode web UI in background on port 7866
opencode web --port 7866 --hostname 0.0.0.0 &

# Start protoClaw Gradio UI in foreground on port 7865
exec python /opt/protoclaw/server.py --config /home/sandbox/.nanobot/config.json
