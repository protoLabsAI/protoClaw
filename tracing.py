"""Langfuse tracing for protoClaw.

Provides trace/span context managers for LLM calls and tool executions.
All traces flow to the Langfuse instance at the configured host.

Falls back silently if Langfuse is not configured (no env vars = no-op).
"""

from __future__ import annotations

import contextvars
import os
import time
from contextlib import contextmanager
from typing import Any

# Langfuse trace context — shared across the request lifecycle
_trace_ctx: contextvars.ContextVar[Any] = contextvars.ContextVar("_trace_ctx", default=None)
_span_ctx: contextvars.ContextVar[Any] = contextvars.ContextVar("_span_ctx", default=None)

_langfuse = None
_enabled = False


def init():
    """Initialize Langfuse client from environment variables.

    Expected env vars (injected by Infisical or docker-compose):
      LANGFUSE_PUBLIC_KEY
      LANGFUSE_SECRET_KEY
      LANGFUSE_HOST (default: http://host.docker.internal:3001)
    """
    global _langfuse, _enabled

    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    host = os.environ.get("LANGFUSE_HOST") or os.environ.get("LANGFUSE_URL", "http://host.docker.internal:3001")

    if not public_key or not secret_key:
        print("[tracing] Langfuse not configured (no LANGFUSE_PUBLIC_KEY/SECRET_KEY). Tracing disabled.")
        return

    try:
        from langfuse import Langfuse
        _langfuse = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=host,
        )
        _enabled = True
        print(f"[tracing] Langfuse initialized → {host}")
    except ImportError:
        print("[tracing] langfuse package not installed. Tracing disabled.")
    except Exception as e:
        print(f"[tracing] Langfuse init failed: {e}. Tracing disabled.")


def is_enabled() -> bool:
    return _enabled


def start_trace(session_id: str, name: str = "protoclaw-chat", metadata: dict | None = None) -> Any:
    """Start a new Langfuse trace for a chat session."""
    if not _enabled:
        return None

    trace = _langfuse.trace(
        name=name,
        session_id=session_id,
        metadata=metadata or {},
        tags=["protoclaw"],
    )
    _trace_ctx.set(trace)
    return trace


def end_trace():
    """Flush the current trace."""
    if _enabled and _langfuse:
        _langfuse.flush()
    _trace_ctx.set(None)
    _span_ctx.set(None)


def trace_llm_call(
    model: str,
    messages: list[dict],
    response_content: str | None,
    response_tool_calls: list | None = None,
    tokens_input: int = 0,
    tokens_output: int = 0,
    duration_ms: int = 0,
    finish_reason: str = "",
    error: str | None = None,
    metadata: dict | None = None,
):
    """Log an LLM call as a Langfuse generation span."""
    trace = _trace_ctx.get(None)
    if not trace:
        return None

    generation = trace.generation(
        name="llm-call",
        model=model,
        input=messages,
        output=response_content or "",
        metadata={
            **(metadata or {}),
            "finish_reason": finish_reason,
            "tool_calls": len(response_tool_calls) if response_tool_calls else 0,
            **({"error": error} if error else {}),
        },
        usage={
            "input": tokens_input,
            "output": tokens_output,
            "total": tokens_input + tokens_output,
        },
        level="ERROR" if error else "DEFAULT",
    )
    _span_ctx.set(generation)
    return generation


def trace_tool_call(
    tool_name: str,
    args: dict,
    result: str,
    duration_ms: int,
    success: bool,
    session_id: str = "",
):
    """Log a tool execution as a Langfuse span."""
    trace = _trace_ctx.get(None)
    if not trace:
        return None

    # Sanitize args (remove large values)
    safe_args = {}
    for k, v in (args or {}).items():
        sv = str(v)
        safe_args[k] = sv[:500] if len(sv) > 500 else v

    span = trace.span(
        name=f"tool:{tool_name}",
        input=safe_args,
        output=result[:1000] if result else "",
        metadata={
            "duration_ms": duration_ms,
            "success": success,
            "session_id": session_id,
        },
        level="ERROR" if not success else "DEFAULT",
    )
    return span


def score_trace(name: str, value: float, comment: str = ""):
    """Attach a score to the current trace (for eval hooks)."""
    trace = _trace_ctx.get(None)
    if not trace:
        return

    trace.score(
        name=name,
        value=value,
        comment=comment,
    )


def flush():
    """Force flush any pending events."""
    if _enabled and _langfuse:
        _langfuse.flush()
