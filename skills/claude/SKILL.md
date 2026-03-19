---
name: claude
description: Invoke Claude (Anthropic) for complex reasoning, code review, and self-improvement tasks.
always: true
---

# Claude Tool

You have a `claude` tool that invokes Claude Code CLI (Anthropic) as a subprocess. This gives you access to a more capable model for tasks beyond your local LLM.

## Budget

This tool is **rate-limited** — you have a fixed number of calls per 24-hour window (default: 10). The remaining budget is shown in the tool description every time your tools are loaded. Treat each call as expensive.

## When to Use

Use the `claude` tool ONLY when:
- The task genuinely requires stronger reasoning than you can provide
- You need deep code review or architectural analysis
- You're stuck and have exhausted your own tools and reasoning
- The user explicitly asks you to use Claude
- Self-improvement: analyzing your own behavior, refining your approach

## When NOT to Use

Do NOT use the `claude` tool for:
- Simple questions you can answer yourself
- File operations, searches, or web lookups (use your local tools)
- Tasks where your local tools are sufficient
- Casual conversation or formatting

**Exhaust local tools first.** Read files, search code, run commands — if you can solve it with your own tools, do that instead.

## How to Use

```
Tool: claude
Parameters:
  prompt (required): Clear, specific task description. Be detailed — you're paying for this call.
  max_turns (optional): Max agentic iterations (default 5, max 20). Keep low unless the task is complex.
  allowed_tools (optional): Comma-separated tools Claude can use (default: Read,Glob,Grep,Bash). Use "all" for full access.
```

## Best Practices

1. **Be specific in your prompt.** Vague prompts waste the call. Include file paths, context, and what you want back.
2. **Front-load context.** Read relevant files yourself first, then include key snippets in the prompt so Claude doesn't spend turns re-reading.
3. **Keep max_turns low.** Most tasks need 3-5 turns. Only increase for complex multi-file analysis.
4. **Use restricted tools.** Default `Read,Glob,Grep,Bash` is usually enough. Only pass `all` if Claude needs to edit files.
5. **One call, one task.** Don't try to pack multiple unrelated tasks into one prompt.

## Example Prompts

Good:
```
"Review /sandbox/server.py for security vulnerabilities. Focus on the chat() function and any injection risks in slash command parsing. Return a list of findings with severity and suggested fixes."
```

Bad:
```
"Look at my code and tell me if it's good"
```

## Availability

The claude tool only loads if credentials are available (API key or CLI OAuth). If you don't see it in `/tools`, credentials are not configured. Do not attempt to call it if it's not listed.
