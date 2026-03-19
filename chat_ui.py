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
        title="protoClaw",
        subtitle="protoLabs.studio",
    )
    app.launch(server_name="0.0.0.0", server_port=7865)
"""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

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

# protoLabs Studio dark theme — indigo accents (#6366f1), studio-dark backgrounds
PROTOLABS_DARK_CSS = """
    /* Force dark colour-scheme so Gradio's dark tokens activate */
    html { color-scheme: dark !important; }

    /* Dark backgrounds */
    body,
    .gradio-container,
    .main,
    .wrap,
    .gap,
    #component-0 {
        background: #0d0d1a !important;
    }

    /* Surface cards / panels */
    .block, .form, .panel, .tabitem,
    .sidebar, .sidebar-content {
        background: #12121f !important;
        border-color: rgba(99, 102, 241, 0.2) !important;
    }

    /* Input / textbox */
    input, textarea,
    .gr-input, .gr-textarea,
    [class*="input-"], [class*="textbox"] {
        background: #1a1a2e !important;
        color: #e2e8f0 !important;
        border-color: rgba(99, 102, 241, 0.35) !important;
    }
    input:focus, textarea:focus {
        border-color: #6366f1 !important;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25) !important;
    }

    /* Primary buttons — indigo */
    button.primary, .btn-primary, [class*="primary"][class*="btn"] {
        background: #6366f1 !important;
        border-color: #6366f1 !important;
        color: #fff !important;
    }
    button.primary:hover, .btn-primary:hover {
        background: #4f46e5 !important;
        border-color: #4f46e5 !important;
    }

    /* Secondary buttons */
    button.secondary, .btn-secondary {
        background: #1a1a2e !important;
        border-color: rgba(99, 102, 241, 0.35) !important;
        color: #818cf8 !important;
    }
    button.secondary:hover {
        background: #2d2b55 !important;
    }

    /* Chat bubble — assistant */
    .message.bot, .message.assistant,
    [data-testid="bot"], [class*="bot-message"] {
        background: #1e1e35 !important;
        border-left: 3px solid #6366f1 !important;
        color: #e2e8f0 !important;
    }

    /* Chat bubble — user */
    .message.user, [data-testid="user"], [class*="user-message"] {
        background: #2d2b55 !important;
        color: #e2e8f0 !important;
    }

    /* Markdown / text */
    .markdown, .prose, .gr-markdown,
    p, span, label, li {
        color: #e2e8f0 !important;
    }

    /* Headers */
    h1, h2, h3, .markdown h1, .markdown h2, .markdown h3 {
        color: #818cf8 !important;
    }

    /* Accordion / collapsible */
    .accordion-header, [class*="accordion"] button {
        background: #12121f !important;
        color: #818cf8 !important;
        border-color: rgba(99, 102, 241, 0.2) !important;
    }

    /* Dropdown */
    .dropdown, select {
        background: #1a1a2e !important;
        color: #e2e8f0 !important;
        border-color: rgba(99, 102, 241, 0.35) !important;
    }

    /* Code blocks */
    code, pre, .gr-code, [class*="code-"] {
        background: #0a0a14 !important;
        border-color: rgba(99, 102, 241, 0.2) !important;
        color: #a5b4fc !important;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0d0d1a; }
    ::-webkit-scrollbar-thumb {
        background: rgba(99, 102, 241, 0.4);
        border-radius: 3px;
    }
    ::-webkit-scrollbar-thumb:hover { background: #6366f1; }

    /* Tab selection */
    .tab-nav button.selected, [class*="tab"][aria-selected="true"] {
        border-bottom-color: #6366f1 !important;
        color: #818cf8 !important;
    }

    /* Sidebar toggle */
    .sidebar-toggle, [class*="sidebar-toggle"] {
        background: #6366f1 !important;
        color: #fff !important;
    }
"""

# HTML injected into <head> — PWA manifest link, theme-color, favicon, SW registration
PROTOLABS_PWA_HEAD = """
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="alternate icon" href="/static/favicon.svg">
<link rel="apple-touch-icon" href="/static/icons/icon-192.svg">
<link rel="manifest" href="/manifest.json">
<meta name="theme-color" content="#6366f1">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="protoClaw">
<script>
if ('serviceWorker' in navigator) {
    window.addEventListener('load', function () {
        navigator.serviceWorker
            .register('/sw.js', { scope: '/' })
            .then(function (reg) {
                console.log('[protoClaw] SW registered:', reg.scope);
            })
            .catch(function (err) {
                console.warn('[protoClaw] SW registration failed:', err);
            });
    });
}
</script>
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
    pwa: bool = True,
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
        pwa: Inject PWA head tags (manifest, favicon, service worker registration).
             Requires manifest.json and sw.js to be served at / by the host app.
    """
    _theme = gr.themes.Soft(primary_hue="indigo", neutral_hue="slate")
    _css = CLEAN_CSS + PROTOLABS_DARK_CSS + extra_css
    _head = PROTOLABS_PWA_HEAD if pwa else ""

    def _build() -> gr.Blocks:
        with gr.Blocks(
            title=title.replace("*", "").strip(),
            theme=_theme,
            css=_css,
            head=_head,
        ) as app:
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
                        save_mcp_btn = gr.Button(
                            "Save & Connect", size="sm", variant="primary"
                        )
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
                    refresh_model_btn.click(
                        fn=load_model, outputs=[model_display]
                    ).then(fn=load_provider_choices, outputs=[provider_dropdown])

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

            def get_response(history: list[dict], original_msg: str, sid: str):
                """Call LLM and append response."""
                if not original_msg.strip():
                    return history, sid
                result = asyncio.run(chat_fn(original_msg, sid))
                # Handle command sentinels
                for msg in result:
                    meta = msg.get("metadata", {})
                    if meta.get("_clear"):
                        return [], sid
                    if meta.get("_new"):
                        return [], secrets.token_hex(4)
                history.extend(result)
                return history, sid

            # Hidden state to pass the original message between steps
            pending_msg = gr.State("")

            # Step 1: render user message instantly
            # Step 2: call LLM (with loading indicator)
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
        # Theme and CSS are now baked into gr.Blocks at build time.
        # This wrapper only adds server-level defaults.
        kwargs.setdefault("server_name", "0.0.0.0")
        # pwa=True is supported in Gradio 5.x; silently skip on older versions.
        if kwargs.pop("pwa", None) is not None:
            try:
                return _original_launch(**kwargs, pwa=True)
            except TypeError:
                pass  # Gradio version does not support pwa= kwarg
        return _original_launch(**kwargs)

    app.launch = _launch
    return app
