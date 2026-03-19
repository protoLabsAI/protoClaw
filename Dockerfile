FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root sandbox user
RUN useradd -m -s /bin/bash sandbox

# Install OpenCode CLI
ARG OPENCODE_VERSION=v1.2.27
RUN curl -fsSL "https://github.com/anomalyco/opencode/releases/download/${OPENCODE_VERSION}/opencode-linux-x64.tar.gz" \
    | tar xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/opencode

# Install nanobot from submodule
COPY nanobot/ /opt/nanobot/
RUN pip install --no-cache-dir /opt/nanobot/ gradio

# Install protoClaw providers and server
COPY providers/ /opt/protoclaw/providers/
COPY scripts/install-providers.py /opt/protoclaw/
COPY chat_ui.py /opt/protoclaw/chat_ui.py
COPY server.py /opt/protoclaw/server.py
COPY entrypoint.sh /opt/protoclaw/entrypoint.sh
COPY config/ /opt/protoclaw/config/
RUN python /opt/protoclaw/install-providers.py

# Sandbox workspace
RUN mkdir -p /sandbox /tmp/sandbox \
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
