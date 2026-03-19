"""
Reusable Gradio chat UI for protoLabs experiments.

Provides a clean, minimal chat interface that can wrap any async
chat function. Hides Gradio branding, action buttons, and badges.
Includes an optional settings sidebar with collapsible sections.

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
from typing import Callable, Awaitable, Any

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

# Type for settings callbacks
SettingsCallbacks = dict[str, Any]


def create_chat_app(
    chat_fn: ChatFn,
    title: str = "Chat",
    subtitle: str = "",
    placeholder: str = "Type a message...",
    chat_height: str = "80vh",
    footer_html: str = '<div style="text-align:center; padding:8px 0; opacity:0.5; font-size:12px;">built with <a href="https://protolabs.studio" target="_blank" rel="noopener" style="color:inherit;">protolabs.studio</a></div>',
    extra_css: str = "",
    settings: SettingsCallbacks | None = None,
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
        settings: Optional dict with callbacks for the settings panel:
            - get_mcp_config() -> str: return current MCP JSON
            - save_mcp_config(json_str) -> str: save MCP config, return status
            - get_mcp_status() -> str: return MCP connection status markdown
            - get_tools_list() -> str: return registered tools markdown
            - get_model_info() -> str: return model info markdown
    """

    def _build() -> gr.Blocks:
        with gr.Blocks(title=title.replace("*", "").strip()) as app:
            session_id = gr.State("default")

            header = f"**{title}**"
            if subtitle:
                header += f" &nbsp; {subtitle}"

            with gr.Row():
                with gr.Column(scale=4 if settings else 1):
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

                # --- Settings sidebar ---
                if settings:
                    with gr.Column(scale=1, min_width=320):
                        gr.Markdown("**Settings**")

                        with gr.Accordion("MCP Servers", open=False):
                            mcp_status = gr.Markdown("Loading...")
                            refresh_mcp_btn = gr.Button("Refresh Status", size="sm")
                            mcp_editor = gr.Code(
                                label="MCP Config (JSON)",
                                language="json",
                                lines=10,
                            )
                            save_mcp_btn = gr.Button("Save & Connect", size="sm", variant="primary")
                            mcp_save_status = gr.Markdown("")

                        with gr.Accordion("Tools", open=False):
                            tools_display = gr.Markdown("Loading...")
                            refresh_tools_btn = gr.Button("Refresh", size="sm")

                        with gr.Accordion("Model", open=False):
                            model_display = gr.Markdown("Loading...")
                            refresh_model_btn = gr.Button("Refresh", size="sm")

                        # --- Settings callbacks ---

                        def load_mcp_config():
                            return settings["get_mcp_config"]()

                        def load_mcp_status():
                            return settings["get_mcp_status"]()

                        def save_mcp_config(json_str):
                            return settings["save_mcp_config"](json_str)

                        def load_tools():
                            return settings["get_tools_list"]()

                        def load_model():
                            return settings["get_model_info"]()

                        # Load initial state
                        app.load(fn=load_mcp_config, outputs=[mcp_editor])
                        app.load(fn=load_mcp_status, outputs=[mcp_status])
                        app.load(fn=load_tools, outputs=[tools_display])
                        app.load(fn=load_model, outputs=[model_display])

                        # Refresh buttons
                        refresh_mcp_btn.click(fn=load_mcp_status, outputs=[mcp_status])
                        refresh_tools_btn.click(fn=load_tools, outputs=[tools_display])
                        refresh_model_btn.click(fn=load_model, outputs=[model_display])

                        # Save MCP config
                        save_mcp_btn.click(
                            fn=save_mcp_config,
                            inputs=[mcp_editor],
                            outputs=[mcp_save_status],
                        ).then(
                            fn=load_mcp_status,
                            outputs=[mcp_status],
                        ).then(
                            fn=load_tools,
                            outputs=[tools_display],
                        )

            # --- Chat callbacks ---

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
