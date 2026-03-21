# protoClaw — Status & Roadmap

## Current State

protoClaw is a sandboxed AI agent running nanobot + Gradio in a hardened Docker container. Connected to local vLLM and cloud models via the AI gateway.

**Running at:** `:7865` on ava-ai (Blackwell node)

## Completed Work

### Core Agent
- [x] Nanobot agent loop with LiteLLM provider
- [x] OmniCoder custom provider (XML tool-call parsing)
- [x] Gradio chat UI with PWA support
- [x] CLIProxyAPI for Claude OAuth model switching
- [x] Crab emoji branding, custom favicon, removed Gradio branding
- [x] Phone-a-Friend tool (cloud model escalation)
- [x] Beads issue tracker tool
- [x] Browser automation tool (agent-browser)
- [x] Vector memory tool (sqlite-vec + Ollama embeddings)
- [x] Session commands (/new, /clear, /think, /audit, /tools, /help, /mcp, /beads)

### Observability (2026-03-21)
- [x] **Langfuse tracing** — all LLM calls + tool executions traced with session grouping
- [x] **Enhanced audit logging** — JSONL with trace_id, session stats
- [x] **Prometheus metrics** — 6 collectors, `/metrics` endpoint for Grafana
  - `protoclaw_llm_calls_total` (counter by model, finish_reason)
  - `protoclaw_llm_latency_seconds` (histogram by model)
  - `protoclaw_llm_tokens_total` (counter by model, direction)
  - `protoclaw_tool_calls_total` (counter by tool_name, success)
  - `protoclaw_tool_latency_seconds` (histogram by tool_name)
  - `protoclaw_active_sessions` (gauge)

### Infrastructure
- [x] Docker container with seccomp profile
- [x] Persistent volumes: audit logs, vectors, beads, cliproxy
- [x] Connected to gateway (:4000) and vLLM (:8000) via host.docker.internal
- [x] Langfuse env vars in docker-compose (LANGFUSE_PUBLIC_KEY, SECRET_KEY, HOST)

## In Progress

### Eval Integration
- [ ] Connect protoClaw traces to eval pipeline (Langfuse → datasets → eval suite)
- [ ] Add eval hooks to tool execution (async scoring, don't block agent loop)
- [ ] Score tool calls against function-call eval suite

### pve01 Prometheus Integration
- [ ] Add `ava-ai:7865/metrics` to pve01 Prometheus scrape targets
- [ ] Create Grafana dashboard for protoClaw metrics
- [ ] Alert rules: high error rate, latency spikes

## Roadmap

### Near-term
- [ ] Fine-tune OmniCoder 9B on protoClaw traces (LoRA, targeting tool-use gaps)
- [ ] Expand browser tool capabilities
- [ ] Add file upload/download to Gradio UI
- [ ] MCP server integration for external tool discovery

### Medium-term
- [ ] Multi-agent mode (coordinator + specialist subagents)
- [ ] Persistent conversation memory across container restarts
- [ ] Integration with protoMaker agent system
- [ ] Cost tracking per session (cloud model usage)

### Long-term
- [ ] Self-improving agent loop (eval scores → automatic prompt refinement)
- [ ] Deploy as service for team access via Cloudflare tunnel
- [ ] A/B testing different models per session (controlled by eval scores)

## Architecture

```
User → Gradio UI (:7865)
         │
         ├─→ Nanobot Agent Loop
         │     ├─→ LiteLLM Provider → vLLM (:8000) or Gateway (:4000)
         │     │     └─→ Langfuse trace (generation span)
         │     │     └─→ Prometheus metric (llm_calls, latency, tokens)
         │     │
         │     └─→ Tool Registry → execute()
         │           ├─→ Audit JSONL (/sandbox/audit/)
         │           ├─→ Langfuse trace (tool span)
         │           └─→ Prometheus metric (tool_calls, latency)
         │
         └─→ /metrics → Prometheus (pve01) → Grafana
```

## Key Files

| File | Purpose |
|------|---------|
| `server.py` | Main server, chat function, audit wrapper, metrics endpoint |
| `tracing.py` | Langfuse SDK integration (traces, spans, scores) |
| `metrics.py` | Prometheus collectors and /metrics endpoint |
| `audit.py` | JSONL audit logging with session stats |
| `chat_ui.py` | Gradio blocks UI definition |
| `nanobot/providers/base.py` | LLM call tracing + metrics hook |
| `docker-compose.yml` | Container config with o11y env vars |
| `Dockerfile` | Build with langfuse + prometheus-client deps |
