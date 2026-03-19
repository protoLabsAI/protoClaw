"""OmniCoder provider — parses XML-style tool calls from text output.

OmniCoder uses a non-standard tool call format:
    <tool_call>
    <function=tool_name>
    <parameter=param_name>value</parameter>
    </function>
    </tool_call>

This provider wraps LiteLLMProvider, strips tools from the API request
(to avoid vLLM's auto-tool-choice requirement), injects them into the
system prompt using OmniCoder's native template, and parses the XML
tool calls from the text response.
"""

import re
from typing import Any

from nanobot.providers.base import LLMResponse, ToolCallRequest
from nanobot.providers.litellm_provider import LiteLLMProvider, _short_tool_id


_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*<function=(\w+)>(.*?)</function>\s*</tool_call>",
    re.DOTALL,
)
_PARAM_RE = re.compile(
    r"<parameter=(\w+)>(.*?)</parameter>",
    re.DOTALL,
)


def _parse_tool_calls(text: str) -> tuple[str, list[ToolCallRequest]]:
    """Extract tool calls from OmniCoder's XML format.

    Returns (cleaned_text, tool_calls) where cleaned_text has the
    tool call blocks removed.
    """
    tool_calls: list[ToolCallRequest] = []

    for match in _TOOL_CALL_RE.finditer(text):
        func_name = match.group(1)
        body = match.group(2)
        args: dict[str, Any] = {}
        for param_match in _PARAM_RE.finditer(body):
            key = param_match.group(1)
            value = param_match.group(2).strip()
            # Try to parse numeric values
            if value.isdigit():
                args[key] = int(value)
            else:
                try:
                    args[key] = float(value)
                except ValueError:
                    args[key] = value

        tool_calls.append(ToolCallRequest(
            id=_short_tool_id(),
            name=func_name,
            arguments=args,
        ))

    cleaned = _TOOL_CALL_RE.sub("", text).strip() if tool_calls else text
    return cleaned, tool_calls


def _tools_to_system_block(tools: list[dict[str, Any]]) -> str:
    """Format tools as OmniCoder expects in the system prompt."""
    import json
    lines = ["# Tools\n\nYou have access to the following functions:\n\n<tools>"]
    for tool in tools:
        lines.append(json.dumps(tool, ensure_ascii=False))
    lines.append("</tools>")
    lines.append(
        '\nIf you choose to call a function ONLY reply in the following format '
        'with NO suffix:\n\n'
        '<tool_call>\n'
        '<function=example_function_name>\n'
        '<parameter=example_parameter_1>\nvalue_1\n</parameter>\n'
        '<parameter=example_parameter_2>\n'
        'This is the value for the second parameter\n'
        'that can span\nmultiple lines\n</parameter>\n'
        '</function>\n'
        '</tool_call>\n\n'
        '<IMPORTANT>\n'
        'Reminder:\n'
        '- Function calls MUST follow the specified format: an inner '
        '<function=...></function> block must be nested within '
        '<tool_call></tool_call> XML tags\n'
        '- Required parameters MUST be specified\n'
        '- You may provide optional reasoning for your function call in '
        'natural language BEFORE the function call, but NOT after\n'
        '- If there is no function call available, answer the question directly\n'
        '</IMPORTANT>'
    )
    return "\n".join(lines)


class OmniCoderProvider(LiteLLMProvider):
    """LiteLLM provider with OmniCoder XML tool call parsing."""

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> LLMResponse:
        # Move tools into the system prompt so we don't need vLLM's
        # --enable-auto-tool-choice flag.
        modified_messages = list(messages)
        if tools:
            tools_block = _tools_to_system_block(tools)
            # Prepend or append to existing system message
            if modified_messages and modified_messages[0].get("role") == "system":
                orig = modified_messages[0]["content"] or ""
                modified_messages[0] = {
                    **modified_messages[0],
                    "content": f"{orig}\n\n{tools_block}",
                }
            else:
                modified_messages.insert(0, {
                    "role": "system",
                    "content": tools_block,
                })

        # Call parent without tools (plain text completion)
        response = await super().chat(
            messages=modified_messages,
            tools=None,  # No structured tools
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            tool_choice=None,
        )

        # Parse tool calls from text output
        if response.content and "<tool_call>" in response.content:
            cleaned_text, tool_calls = _parse_tool_calls(response.content)
            if tool_calls:
                return LLMResponse(
                    content=cleaned_text or None,
                    tool_calls=tool_calls,
                    finish_reason="tool_calls",
                    usage=response.usage,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

        return response
