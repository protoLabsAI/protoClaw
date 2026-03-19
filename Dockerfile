FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential tmux \
    && rm -rf /var/lib/apt/lists/*

# Create non-root sandbox user (uid matches host user for bind mount perms)
ARG SANDBOX_UID=1001
RUN useradd -m -s /bin/bash -u ${SANDBOX_UID} sandbox

# Install OpenCode CLI
ARG OPENCODE_VERSION=v1.2.27
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/opencode

# Node.js (needed for agent-browser + Claude Code CLI)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs npm \
    && rm -rf /var/lib/apt/lists/*

# Browser tool: agent-browser + Chromium
RUN npm install -g agent-browser && agent-browser install --with-deps

# Claude Code CLI (headless mode for AI-assisted tasks)
RUN npm install -g @anthropic-ai/claude-code

# Summarize CLI (URL/file/YouTube summarization — uses ANTHROPIC_API_KEY)
RUN npm install -g @steipete/summarize

# Beads issue tracker (pre-built binary)
ARG BEADS_VERSION=0.1.29
RUN curl -fsSL "https://github.com/Dicklesworthstone/beads_rust/releases/download/v${BEADS_VERSION}/br-${BEADS_VERSION}-linux_amd64.tar.gz" \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/br

# Install nanobot from submodule
COPY nanobot/ /opt/nanobot/
RUN pip install --no-cache-dir /opt/nanobot/ gradio sqlite-vec httpx

# Install protoClaw providers, tools, and server
COPY providers/ /opt/protoclaw/providers/
COPY tools/ /opt/protoclaw/tools/
COPY skills/ /opt/protoclaw/skills/
COPY scripts/install-providers.py /opt/protoclaw/
COPY audit.py /opt/protoclaw/audit.py
COPY chat_ui.py /opt/protoclaw/chat_ui.py
COPY server.py /opt/protoclaw/server.py
COPY entrypoint.sh /opt/protoclaw/entrypoint.sh
COPY config/ /opt/protoclaw/config/
RUN python /opt/protoclaw/install-providers.py

# Sandbox workspace + audit/memory dirs
RUN mkdir -p /sandbox /tmp/sandbox /sandbox/audit /sandbox/memory \
    && chown -R sandbox:sandbox /sandbox /tmp/sandbox

# Nanobot data dir
RUN mkdir -p /home/sandbox/.nanobot \
    && chown -R sandbox:sandbox /home/sandbox/.nanobot

# OpenCode config
RUN mkdir -p /home/sandbox/.config/opencode \
    && chown -R sandbox:sandbox /home/sandbox/.config

# Drop to sandbox user
USER sandbox
WORKDIR /sandbox

EXPOSE 7865 7866
CMD ["/opt/protoclaw/entrypoint.sh"]
