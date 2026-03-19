#!/bin/bash
# Start both protoClaw Gradio UI and OpenCode web UI

# Create dirs inside tmpfs home (tmpfs wipes everything)
mkdir -p /home/sandbox/.nanobot /home/sandbox/.config/opencode /home/sandbox/.local

# Copy configs from mounted read-only location
cp /opt/protoclaw/config/nanobot-config.json /home/sandbox/.nanobot/config.json
cp /opt/protoclaw/config/opencode.json /home/sandbox/.config/opencode/opencode.json

# Start OpenCode web UI in background on port 7866
opencode web --port 7866 --hostname 0.0.0.0 &

# Start protoClaw Gradio UI in foreground on port 7865
exec python /opt/protoclaw/server.py --config /home/sandbox/.nanobot/config.json
