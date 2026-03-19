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
import queue
import secrets
import threading
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
# Type for streaming chat: (message, session_id, queue) -> None (pushes to queue)
StreamingChatFn = Callable[..., None]

# Type for settings callbacks
SettingsCallbacks = dict[str, Any]


def create_chat_app(
    chat_fn: ChatFn,
    streaming_fn: StreamingChatFn | None = None,
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

            header_text = f"**{title}**"
            if subtitle:
                header_text += f" &nbsp; {subtitle}"

            header_md = gr.Markdown(header_text)

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

            # --- Settings drawer ---
            if settings:
                with gr.Sidebar(label="Settings", open=False, position="right"):

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
                            provider_dropdown = gr.Dropdown(
                                label="Provider",
                                choices=[],
                                interactive=True,
                            )
                            switch_status = gr.Markdown("")
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

                        def load_provider_choices():
                            choices = settings["get_provider_choices"]()
                            current = settings["get_current_provider"]()
                            return gr.update(choices=choices, value=current)

                        def switch_provider(choice):
                            return settings["switch_provider"](choice)

                        def load_subtitle():
                            return settings["get_subtitle"]()

                        # Load initial state
                        app.load(fn=load_mcp_config, outputs=[mcp_editor])
                        app.load(fn=load_mcp_status, outputs=[mcp_status])
                        app.load(fn=load_tools, outputs=[tools_display])
                        app.load(fn=load_model, outputs=[model_display])
                        app.load(fn=load_provider_choices, outputs=[provider_dropdown])

                        # Refresh buttons
                        refresh_mcp_btn.click(fn=load_mcp_status, outputs=[mcp_status])
                        refresh_tools_btn.click(fn=load_tools, outputs=[tools_display])
                        refresh_model_btn.click(fn=load_model, outputs=[model_display]).then(
                            fn=load_provider_choices, outputs=[provider_dropdown]
                        )

                        # Provider switch
                        provider_dropdown.change(
                            fn=switch_provider,
                            inputs=[provider_dropdown],
                            outputs=[switch_status],
                        ).then(
                            fn=load_model,
                            outputs=[model_display],
                        ).then(
                            fn=load_subtitle,
                            outputs=[header_md],
                        )

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

            def add_user_message(message: str, history: list[dict]):
                """Instantly render user message and clear input."""
                if not message.strip():
                    return "", history, message
                history.append({"role": "user", "content": message})
                return "", history, message

            _SENTINEL = object()

            def get_response(history: list[dict], original_msg: str, sid: str):
                """Call LLM, yielding progress updates as they arrive."""
                if not original_msg.strip():
                    yield history, sid
                    return

                # Handle slash commands synchronously
                stripped = original_msg.strip()
                if stripped.startswith("/"):
                    result = asyncio.run(chat_fn(original_msg, sid))
                    for msg in result:
                        meta = msg.get("metadata", {})
                        if meta.get("_clear"):
                            yield [], sid
                            return
                        if meta.get("_new"):
                            yield [], secrets.token_hex(4)
                            return
                    history.extend(result)
                    yield history, sid
                    return

                # Streaming: run agent in thread, yield progress from queue
                if streaming_fn is None:
                    # Fallback to non-streaming
                    result = asyncio.run(chat_fn(original_msg, sid))
                    history.extend(result)
                    yield history, sid
                    return

                q = queue.Queue()
                thread = threading.Thread(
                    target=streaming_fn,
                    args=(original_msg, sid, q),
                    daemon=True,
                )
                thread.start()

                while True:
                    try:
                        msg = q.get(timeout=0.2)
                    except queue.Empty:
                        continue
                    if msg is _SENTINEL:
                        break
                    # Check for sentinels (from slash commands routed through agent)
                    meta = msg.get("metadata", {}) if isinstance(msg, dict) else {}
                    if meta.get("_clear"):
                        yield [], sid
                        return
                    if meta.get("_new"):
                        yield [], secrets.token_hex(4)
                        return
                    history.append(msg)
                    yield history, sid

                thread.join(timeout=5)

            # Hidden state to pass the original message between steps
            pending_msg = gr.State("")

            # Step 1: render user message instantly
            # Step 2: stream LLM response with progress updates
            for trigger in [txt.submit, send_btn.click]:
                trigger(
                    fn=add_user_message,
                    inputs=[txt, chatbot],
                    outputs=[txt, chatbot, pending_msg],
                ).then(
                    fn=get_response,
                    inputs=[chatbot, pending_msg, session_id],
                    outputs=[chatbot, session_id],
                )

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
