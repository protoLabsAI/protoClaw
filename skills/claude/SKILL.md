---
name: phone_a_friend
description: Call another AI model for help when stuck — multiple providers with different capabilities and costs.
always: true
---

# Phone a Friend

You have a `phone_a_friend` tool that lets you call other AI models when you need help. Each friend has different strengths, costs, and speed. The available friends are listed in the tool description (it updates dynamically).

## When to Use

Use `phone_a_friend` when:
- You're stuck on a problem and need a different perspective
- The task requires deeper reasoning than you can provide alone
- You need to plan a complex multi-step approach
- You need code review or architectural analysis
- Claude is rate-limited and you need *any* outside help
- The user explicitly asks you to get a second opinion

## When NOT to Use

Do NOT phone a friend for:
- Tasks you can handle yourself with local tools
- Simple file operations, searches, or web lookups
- Questions you already know the answer to

**Exhaust your own tools first.** Read files, search code, run commands. Only phone a friend when you genuinely need outside reasoning.

## Choosing the Right Friend

**Need deep reasoning or complex analysis?**
→ `claude-sonnet` or `claude-opus` (paid, rate-limited, expert-level)

**Claude unavailable or rate-limited? Need general reasoning?**
→ `nemotron` or `big-pickle` (free, strong reasoning)

**Need quick code help?**
→ `mimo-pro` (free, fast, code-focused)

**Need general writing or summarization?**
→ `minimax` (free, fast)

**Want fast local inference?**
→ `ollama-*` friends (free, runs on host GPU, no network latency)

## Best Practices

1. **Pick by task, not by habit.** Don't always call the same friend — match the friend to the problem.
2. **Be specific in your prompt.** Include context, file contents, and what you want back.
3. **Start free, escalate if needed.** Try a free friend first. If the answer isn't good enough, then try Claude.
4. **One call, one task.** Don't pack multiple unrelated questions into one prompt.
5. **Include what you've tried.** Tell your friend what you already know and what didn't work.

## Example

```
phone_a_friend(
    friend="nemotron",
    prompt="I need to implement a rate limiter with a sliding window in Python. Requirements: thread-safe, configurable limit and window, track usage per key. Give me a clean implementation."
)
```
