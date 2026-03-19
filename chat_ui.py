"""
Reusable Gradio chat UI for protoLabs experiments.

Provides a clean, minimal chat interface that can wrap any async
chat function. Hides Gradio branding, action buttons, and badges.

Usage:
    from chat_ui import create_chat_app

    async def my_chat(message: str, session_id: str) -> list[dict]:
        return [{"role": "assistant", "content": f"Echo: {message}"}]

    app = create_chat_app(
        chat_fn=my_chat,
        title="My Agent",
        subtitle="powered by local LLM",
    )
    app.launch(server_name="0.0.0.0", server_port=7865)
"""

import asyncio
import secrets
from typing import Callable, Awaitable

import gradio as gr

# CSS to strip Gradio chrome
CLEAN_CSS = """
    footer { display: none !important; }
    .prose { overflow: hidden !important; max-height: 3em !important; }
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
"""

# Type for chat functions: (message, session_id) -> list of message dicts
ChatFn = Callable[[str, str], Awaitable[list[dict]]]


def create_chat_app(
    chat_fn: ChatFn,
    title: str = "Chat",
    subtitle: str = "",
    placeholder: str = "Type a message...",
    chat_height: str = "80vh",
    footer_html: str = '<div style="text-align:center; padding:8px 0; opacity:0.5; font-size:12px;">built with <a href="https://protolabs.studio" target="_blank" rel="noopener" style="color:inherit;">protolabs.studio</a></div>',
    extra_css: str = "",
) -> gr.Blocks:
    """Create a clean Gradio chat app wrapping an async chat function.

    Args:
        chat_fn: Async function (message, session_id) -> list of message dicts.
                 Each dict has "role" and "content", optionally "metadata".
        title: Display title (supports markdown/emoji).
        subtitle: Shown next to title in smaller text.
        placeholder: Input textbox placeholder.
        chat_height: CSS height for the chatbot component.
        footer_html: HTML for the footer. Set to "" to hide.
        extra_css: Additional CSS to inject.
    """

    def _build() -> gr.Blocks:
        with gr.Blocks(title=title.replace("*", "").strip()) as app:
            session_id = gr.State("default")

            header = f"**{title}**"
            if subtitle:
                header += f" &nbsp; {subtitle}"
            gr.Markdown(header)

            chatbot = gr.Chatbot(
                height=chat_height,
                show_label=False,
            )

            with gr.Row():
                txt = gr.Textbox(
                    placeholder=placeholder,
                    show_label=False,
                    scale=9,
                    container=False,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1, min_width=80)

            with gr.Row():
                clear_btn = gr.Button("Clear", size="sm", variant="secondary")
                new_btn = gr.Button("New Session", size="sm", variant="secondary")

            if footer_html:
                gr.HTML(footer_html)

            # --- Callbacks ---

            def respond(message: str, history: list[dict], sid: str):
                if not message.strip():
                    return "", history, sid
                history.append({"role": "user", "content": message})
                result = asyncio.run(chat_fn(message, sid))
                # Handle command sentinels
                for msg in result:
                    meta = msg.get("metadata", {})
                    if meta.get("_clear"):
                        return "", [], sid
                    if meta.get("_new"):
                        return "", [], secrets.token_hex(4)
                history.extend(result)
                return "", history, sid

            submit_args = dict(
                fn=respond,
                inputs=[txt, chatbot, session_id],
                outputs=[txt, chatbot, session_id],
            )
            txt.submit(**submit_args)
            send_btn.click(**submit_args)

            clear_btn.click(
                fn=lambda: ([], "default"),
                outputs=[chatbot, session_id],
            )
            new_btn.click(
                fn=lambda: ([], secrets.token_hex(4)),
                outputs=[chatbot, session_id],
            )

        return app

    app = _build()

    # Stash launch defaults so callers can just do app.launch()
    _original_launch = app.launch

    def _launch(**kwargs):
        kwargs.setdefault("theme", gr.themes.Soft(primary_hue="blue", neutral_hue="slate"))
        kwargs.setdefault("css", CLEAN_CSS + extra_css)
        return _original_launch(**kwargs)

    app.launch = _launch
    return app
