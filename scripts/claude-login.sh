#!/bin/bash
# Claude OAuth login wrapper for CLIProxyAPI
# Rewrites the callback URL to use CLIPROXY_CALLBACK_HOST instead of localhost.
#
# Usage:
#   docker exec -it protoclaw bash /opt/protoclaw/scripts/claude-login.sh
#
# Set CLIPROXY_CALLBACK_HOST env var to your machine's reachable IP/hostname.
# Defaults to localhost.

CALLBACK_HOST="${CLIPROXY_CALLBACK_HOST:-localhost}"

if [ "$CALLBACK_HOST" = "localhost" ]; then
    exec cli-proxy-api -config /opt/.cliproxy/config.yaml -claude-login
fi

# Pipe through sed to rewrite localhost -> callback host in the auth URL
cli-proxy-api -config /opt/.cliproxy/config.yaml -claude-login -no-browser 2>&1 \
    | sed "s|localhost:54545|${CALLBACK_HOST}:54545|g; s|127\.0\.0\.1:54545|${CALLBACK_HOST}:54545|g"
