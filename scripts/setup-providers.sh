#!/bin/bash
# Setup provider credentials for protoClawX container
# Extracts OAuth tokens from host machine and seeds them into the running container
#
# Supports: Claude, Codex, Cursor, OpenCode
# Works on: macOS (Keychain) and Linux (config files)
#
# Usage:
#   ./scripts/setup-providers.sh           # setup all available providers
#   ./scripts/setup-providers.sh claude     # setup Claude only
#   ./scripts/setup-providers.sh codex      # setup Codex only
#   ./scripts/setup-providers.sh cursor     # setup Cursor only
#   ./scripts/setup-providers.sh opencode   # setup OpenCode only

set -e

CONTAINER="protoclaw"
CLIPROXY_CONFIG="/opt/.cliproxy/config.yaml"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}[ok]${NC} $1"; }
warn() { echo -e "${YELLOW}[skip]${NC} $1"; }
fail() { echo -e "${RED}[fail]${NC} $1"; }

# Check container is running
if ! docker inspect "$CONTAINER" &>/dev/null; then
    fail "Container '$CONTAINER' not running. Start with: docker compose up -d"
    exit 1
fi

# ─── Claude ────────────────────────────────────────────────────────────────────

setup_claude() {
    echo ""
    echo "=== Claude Code ==="

    # Try CLIProxyAPI OAuth login first (interactive, persists in volume)
    if docker exec "$CONTAINER" test -f /usr/local/bin/cli-proxy-api 2>/dev/null; then
        echo "Running Claude OAuth login via CLIProxyAPI..."
        echo "A browser window will open. Authenticate with your Claude account."
        echo ""
        docker exec -it "$CONTAINER" cli-proxy-api -config "$CLIPROXY_CONFIG" -claude-login
        if [ $? -eq 0 ]; then
            ok "Claude authenticated via CLIProxyAPI OAuth"
            return 0
        fi
        warn "CLIProxyAPI OAuth failed, trying fallback methods..."
    fi

    # Fallback: extract from macOS Keychain
    if [[ "$OSTYPE" == "darwin"* ]]; then
        CREDS=$(security find-generic-password -s "Claude Code-credentials" -a "$(whoami)" -w 2>/dev/null || true)
        if [ -n "$CREDS" ]; then
            # Write credentials JSON into container
            docker exec "$CONTAINER" sh -c "mkdir -p /home/sandbox/.claude && echo '$CREDS' > /home/sandbox/.claude/.credentials.json && chmod 600 /home/sandbox/.claude/.credentials.json"
            ok "Claude credentials extracted from macOS Keychain"
            return 0
        fi
    fi

    # Fallback: Linux ~/.claude/.credentials.json
    if [ -f "$HOME/.claude/.credentials.json" ]; then
        docker cp "$HOME/.claude/.credentials.json" "$CONTAINER:/home/sandbox/.claude/.credentials.json"
        docker exec "$CONTAINER" chmod 600 /home/sandbox/.claude/.credentials.json
        ok "Claude credentials copied from ~/.claude/.credentials.json"
        return 0
    fi

    # Fallback: ANTHROPIC_API_KEY env var
    if [ -n "$ANTHROPIC_API_KEY" ]; then
        ok "Claude available via ANTHROPIC_API_KEY env var (already set)"
        return 0
    fi

    warn "No Claude credentials found. Run 'claude login' on host first, then re-run this script."
}

# ─── Codex ─────────────────────────────────────────────────────────────────────

setup_codex() {
    echo ""
    echo "=== OpenAI Codex ==="

    # Try CLIProxyAPI OAuth login
    if docker exec "$CONTAINER" test -f /usr/local/bin/cli-proxy-api 2>/dev/null; then
        echo "Running Codex OAuth login via CLIProxyAPI..."
        docker exec -it "$CONTAINER" cli-proxy-api -config "$CLIPROXY_CONFIG" -codex-login
        if [ $? -eq 0 ]; then
            ok "Codex authenticated via CLIProxyAPI OAuth"
            return 0
        fi
        warn "CLIProxyAPI OAuth failed, trying fallback..."
    fi

    # Fallback: ~/.codex/auth.json
    if [ -f "$HOME/.codex/auth.json" ]; then
        docker exec "$CONTAINER" mkdir -p /home/sandbox/.codex
        docker cp "$HOME/.codex/auth.json" "$CONTAINER:/home/sandbox/.codex/auth.json"
        docker exec "$CONTAINER" chmod 600 /home/sandbox/.codex/auth.json
        ok "Codex credentials copied from ~/.codex/auth.json"
        return 0
    fi

    warn "No Codex credentials found. Run 'codex login' on host first, or authenticate via CLIProxyAPI."
}

# ─── Cursor ────────────────────────────────────────────────────────────────────

setup_cursor() {
    echo ""
    echo "=== Cursor ==="

    TOKEN=""

    # macOS: extract from Keychain
    if [[ "$OSTYPE" == "darwin"* ]]; then
        TOKEN=$(security find-generic-password -a "cursor-user" -s "cursor-access-token" -w 2>/dev/null || true)
        if [ -n "$TOKEN" ]; then
            ok "Cursor token extracted from macOS Keychain"
        fi
    fi

    # Linux: extract from config
    if [ -z "$TOKEN" ] && [ -f "$HOME/.config/cursor/auth.json" ]; then
        TOKEN=$(python3 -c "import json; print(json.load(open('$HOME/.config/cursor/auth.json')).get('accessToken',''))" 2>/dev/null || true)
        if [ -n "$TOKEN" ]; then
            ok "Cursor token extracted from ~/.config/cursor/auth.json"
        fi
    fi

    if [ -n "$TOKEN" ]; then
        docker exec "$CONTAINER" sh -c "mkdir -p /home/sandbox/.cursor && echo '{\"accessToken\":\"$TOKEN\"}' > /home/sandbox/.cursor/credentials.json && chmod 600 /home/sandbox/.cursor/credentials.json"
        ok "Cursor credentials written to container"
        return 0
    fi

    warn "No Cursor credentials found. Run 'cursor auth' on host first."
}

# ─── OpenCode ──────────────────────────────────────────────────────────────────

setup_opencode() {
    echo ""
    echo "=== OpenCode ==="

    # macOS and Linux: check standard path
    OPENCODE_AUTH="$HOME/.local/share/opencode/auth.json"
    if [ -f "$OPENCODE_AUTH" ]; then
        docker exec "$CONTAINER" mkdir -p /home/sandbox/.local/share/opencode
        docker cp "$OPENCODE_AUTH" "$CONTAINER:/home/sandbox/.local/share/opencode/auth.json"
        docker exec "$CONTAINER" chmod 600 /home/sandbox/.local/share/opencode/auth.json
        ok "OpenCode credentials copied from $OPENCODE_AUTH"
        return 0
    fi

    # Check config dir alternative
    OPENCODE_ALT="$HOME/.config/opencode/auth.json"
    if [ -f "$OPENCODE_ALT" ]; then
        docker exec "$CONTAINER" mkdir -p /home/sandbox/.config/opencode
        docker cp "$OPENCODE_ALT" "$CONTAINER:/home/sandbox/.config/opencode/auth.json"
        docker exec "$CONTAINER" chmod 600 /home/sandbox/.config/opencode/auth.json
        ok "OpenCode credentials copied from $OPENCODE_ALT"
        return 0
    fi

    warn "No OpenCode credentials found. Run 'opencode auth' on host first."
}

# ─── Main ──────────────────────────────────────────────────────────────────────

echo "╔══════════════════════════════════════════╗"
echo "║  protoClawX Provider Setup               ║"
echo "║  Extracting credentials from host machine ║"
echo "╚══════════════════════════════════════════╝"

TARGET="${1:-all}"

case "$TARGET" in
    claude)   setup_claude ;;
    codex)    setup_codex ;;
    cursor)   setup_cursor ;;
    opencode) setup_opencode ;;
    all)
        setup_claude
        setup_codex
        setup_cursor
        setup_opencode
        ;;
    *)
        echo "Usage: $0 [claude|codex|cursor|opencode|all]"
        exit 1
        ;;
esac

echo ""
echo "─────────────────────────────────────────────"
echo "Done. Restart the container to pick up new credentials:"
echo "  docker compose restart"
echo ""
echo "Or test Claude directly:"
echo "  curl http://localhost:8317/v1/models"
