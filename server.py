"""
protoClaw Gradio UI — chat interface for nanobot agent with tool-use visualization.

Usage:
    python server.py                          # default port 7865
    python server.py --port 7870              # custom port
    python server.py --config path/to/config  # custom config
"""

import argparse
import asyncio
import re
from pathlib import Path
from typing import Any

import gradio as gr

# ---------------------------------------------------------------------------
# Agent setup
# ---------------------------------------------------------------------------

_agent = None
_config = None


def _init_agent(config_path: str | None = None):
    """Initialize nanobot agent loop (called once at startup)."""
    global _agent, _config

    from nanobot.config.loader import load_config, set_config_path
    from nanobot.config.paths import get_cron_dir
    from nanobot.agent.loop import AgentLoop
    from nanobot.bus.queue import MessageBus
    from nanobot.cron.service import CronService
    from nanobot.utils.helpers import sync_workspace_templates

    if config_path:
        p = Path(config_path).expanduser().resolve()
        set_config_path(p)

    _config = load_config(Path(config_path) if config_path else None)
    sync_workspace_templates(_config.workspace_path)

    bus = MessageBus()
    provider = _make_provider(_config)

    cron = CronService(get_cron_dir() / "jobs.json")

    _agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=_config.workspace_path,
        model=_config.agents.defaults.model,
        max_iterations=_config.agents.defaults.max_tool_iterations,
        context_window_tokens=_config.agents.defaults.context_window_tokens,
        web_search_config=_config.tools.web.search,
        web_proxy=_config.tools.web.proxy or None,
        exec_config=_config.tools.exec,
        cron_service=cron,
        restrict_to_workspace=_config.tools.restrict_to_workspace,
        mcp_servers=_config.tools.mcp_servers,
        channels_config=_config.channels,
    )


def _make_provider(config):
    """Create provider — mirrors nanobot CLI logic with OmniCoder support."""
    from nanobot.providers.base import GenerationSettings
    from nanobot.providers.litellm_provider import LiteLLMProvider

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    provider_cls = LiteLLMProvider
    if "omnicoder" in model.lower():
        from nanobot.providers.omnicoder_provider import OmniCoderProvider
        provider_cls = OmniCoderProvider

    provider = provider_cls(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )

    defaults = config.agents.defaults
    provider.generation = GenerationSettings(
        temperature=defaults.temperature,
        max_tokens=defaults.max_tokens,
        reasoning_effort=defaults.reasoning_effort,
    )
    return provider


# ---------------------------------------------------------------------------
# Chat logic
# ---------------------------------------------------------------------------

def _strip_think(text: str) -> str:
    """Remove <think> blocks and orphaned </think> tags."""
    text = re.sub(r"<think>[\s\S]*?</think>", "", text)
    text = re.sub(r"</think>\s*", "", text)
    return text.strip()


async def _chat(message: str, history: list[dict[str, str]], session_id: str) -> Any:
    """Process a message through nanobot and yield incremental updates."""
    progress_messages: list[dict] = []

    async def on_progress(content: str, *, tool_hint: bool = False) -> None:
        content = _strip_think(content)
        if not content:
            return
        if tool_hint:
            progress_messages.append({
                "role": "assistant",
                "metadata": {"title": f"🔧 {content}"},
                "content": "",
            })
        else:
            progress_messages.append({
                "role": "assistant",
                "metadata": {"title": "💭 Thinking"},
                "content": content,
            })

    response = await _agent.process_direct(
        content=message,
        session_key=f"gradio:{session_id}",
        channel="gradio",
        chat_id=session_id,
        on_progress=on_progress,
    )

    response = _strip_think(response or "")

    messages = list(progress_messages)
    messages.append({"role": "assistant", "content": response})
    return messages


def _sync_chat(message: str, history: list[dict], session_id: str):
    """Sync wrapper — Gradio calls this, we run the async agent."""
    return asyncio.run(_chat(message, history, session_id))


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

def create_app() -> gr.Blocks:
    model_name = _config.agents.defaults.model if _config else "unknown"

    with gr.Blocks(title="protoClaw") as app:
        session_id = gr.State("default")

        gr.Markdown(f"### 🦀 protoClaw\n<sub>`{model_name}` · sandboxed agent</sub>")

        chatbot = gr.Chatbot(
            height="80vh",
            label="protoClaw",
            show_label=False,
        )

        with gr.Row():
            txt = gr.Textbox(
                placeholder="Ask protoClaw anything...",
                show_label=False,
                scale=9,
                container=False,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1, min_width=80)

        with gr.Row():
            clear_btn = gr.Button("Clear", size="sm", variant="secondary")
            new_session_btn = gr.Button("New Session", size="sm", variant="secondary")

        # --- Callbacks ---

        def respond(message: str, history: list[dict], sid: str):
            if not message.strip():
                return "", history
            history.append({"role": "user", "content": message})
            agent_messages = _sync_chat(message, history, sid)
            history.extend(agent_messages)
            return "", history

        def clear_chat():
            return [], "default"

        def new_session():
            import secrets
            return [], secrets.token_hex(4)

        submit_args = dict(
            fn=respond,
            inputs=[txt, chatbot, session_id],
            outputs=[txt, chatbot],
        )

        txt.submit(**submit_args)
        send_btn.click(**submit_args)
        clear_btn.click(fn=clear_chat, outputs=[chatbot, session_id])
        new_session_btn.click(fn=new_session, outputs=[chatbot, session_id])

    return app


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="protoClaw Gradio UI")
    parser.add_argument("--port", type=int, default=7865)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    _init_agent(args.config)
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="slate"),
        css="""
            footer { display: none !important; }
            .built-with { display: none !important; }
            button.copy-btn, button.like, button.dislike,
            .message-buttons-left, .message-buttons-right,
            .bot .message-buttons, .user .message-buttons,
            .copy-button, .action-button,
            [data-testid="copy-button"], [data-testid="like"], [data-testid="dislike"],
            .message-wrap .icon-button, .message-wrap .icon-buttons,
            .chatbot .icon-button, .chatbot .icon-buttons,
            .chatbot .action-buttons,
            .chatbot button[aria-label="Copy"], .chatbot button[aria-label="Like"],
            .chatbot button[aria-label="Dislike"], .chatbot button[aria-label="Retry"],
            .badge-wrap, .chatbot .badge-wrap,
            span.chatbot-badge, .chatbot-badge,
            .built-with-gradio, a[href*="gradio.app"] {
                display: none !important;
            }
        """,
    )
