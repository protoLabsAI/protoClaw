---
name: beads
description: Issue tracking and long-horizon task management with dependency-driven work queues.
always: true
---

# Beads Issue Tracker

You have access to the Beads issue tracker via MCP tools (`mcp_beads_*`). Beads is your **persistent memory for work** — your session memory resets, but beads persists across sessions. Use it to track everything that matters.

## Core Concept

Beads is a local-first, git-native issue tracker. Issues live in `.beads/` as SQLite + JSONL. The key innovation is the **ready queue**: `br ready` returns only issues that are unblocked and actionable, computed from a dependency graph.

## When to Create Issues

Create issues whenever:
- The user describes work that has multiple steps
- A task can't be finished in the current session
- You discover a bug, follow-up, or subtask while working
- The user says "track this", "remind me", "we need to", or describes future work
- You want to leave a note for your future self

**Default to creating issues.** It's cheap and keeps work visible. An untracked task is a forgotten task.

## Issue Lifecycle

```
open → in_progress → closed
         ↓
       deferred → open (after defer date)
```

| Status | Meaning | Shows in ready queue? |
|--------|---------|----------------------|
| open | Not started | Yes (if unblocked) |
| in_progress | Actively working | Yes (if unblocked) |
| closed | Done | No |
| deferred | Postponed | No (until defer_until date) |

## Priority Levels

| Priority | Label | When to use |
|----------|-------|-------------|
| 0 | CRITICAL | Blocking all other work, needs immediate fix |
| 1 | HIGH | Important, should be done soon |
| 2 | MEDIUM | Default — normal work items |
| 3 | LOW | Nice to have, do when convenient |
| 4 | BACKLOG | Someday/maybe, park for later |

## Issue Types

`task` (default), `bug`, `feature`, `epic`, `chore`, `docs`, `question`

## Dependency Types

| Type | Blocks ready? | Use for |
|------|--------------|---------|
| blocks | YES | "X cannot start until Y is done" |
| parent-child | YES | Epic → subtask decomposition |
| related | No | Cross-references, "see also" |
| discovered-from | No | "Found this while working on Y" |

**Only `blocks` and `parent-child` affect the ready queue.** Use `related` for soft connections — don't over-block.

## Session Workflow

### Starting a session
1. Run `br ready --json` to see what's actionable
2. Pick the highest-priority unblocked item
3. Run `br show <id>` to get full context + comments
4. Update status: `br update <id> --status in_progress`

### During work
- When you discover a new task: `br create "Found X" --type task`
- Link discoveries: `br dep add <new-id> <original-id> --type discovered-from`
- Add blockers if needed: `br dep add <child> <parent> --type blocks`
- Leave notes: `br comment add <id> "Progress update or findings"`

### Ending a session
1. Close completed work: `br close <id> --reason "What was done"`
2. Update in-progress items with comments about current state
3. Create issues for anything discovered but not yet addressed

## MCP Tools Available

All beads tools are prefixed `mcp_beads_`. Key tools:

| Tool | Purpose |
|------|---------|
| `ListIssuesTool` | Query issues with filters (status, priority, assignee, labels) |
| `ShowIssueTool` | Get full issue details with dependencies and comments |
| `CreateIssueTool` | Create new issues with title, description, type, priority, labels |
| `UpdateIssueTool` | Change status, priority, assignee, add labels |
| `CloseIssueTool` | Resolve issues with a close reason |
| `ManageDependenciesTool` | Add/remove dependency relationships |
| `ProjectOverviewTool` | High-level summary of all work |

## Decomposition Pattern

Break large goals into small, concrete issues:

```
User: "Add authentication to the API"

You create:
  bd-1: [epic] "Add API authentication" (P1, feature)
  bd-2: [task] "Research auth options (JWT vs OAuth)" (P2)
  bd-3: [task] "Implement auth middleware" (P1)
  bd-4: [task] "Add login/register endpoints" (P1)
  bd-5: [task] "Write auth tests" (P2)

Dependencies:
  bd-3 blocks bd-4 (middleware before endpoints)
  bd-2 blocks bd-3 (research before implementation)
  bd-5 parent-child bd-1 (subtask of epic)
  bd-3 parent-child bd-1
  bd-4 parent-child bd-1

Ready queue shows: bd-2 (only unblocked item)
After bd-2 closes: bd-3 becomes ready
After bd-3 closes: bd-4 becomes ready
```

## Comments as Memory

Since your session memory resets, use comments to leave notes for your future self:

```
br comment add bd-abc123 "Investigated the timeout — root cause is missing DB index on users.email. Need to create migration."
```

Next session, `br show bd-abc123` gives you full context without re-investigating.

## Quick Access via Slash Commands

Users can type these in chat for quick views:
- `/beads ready` — Show actionable work
- `/beads list` — Show all issues
- `/beads stats` — Project statistics
- `/beads blocked` — Show blocked issues

For mutations (create, update, close, deps), use the MCP tools directly.
