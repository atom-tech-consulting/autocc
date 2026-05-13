---
name: taskboard
aliases: ["tb"]
description: "Standardized task management for the project — task list format, lifecycle, and briefing protocol. Use to initialize, view, or manage tasks. Reflector depends on this."
user_invocable: true
---

<command-name>taskboard</command-name>

# Taskboard

Standardized task management for the project. Defines the task list format, lifecycle, briefing files, and CLAUDE.md configuration. Both human and agent use this to track work; reflector depends on it for task discovery.

## Usage

- `/taskboard` (or `/tb`) — show task list status (counts by section, next ready task)
- `/taskboard init` (or `/tb init`) — initialize task management in the current project
- `/tb prep TB-5` — create a briefing file for a backlog task and move it to Ready
- `/tb brief TB-5` — show the briefing for a ready/active task

## Init

When `/taskboard init` is invoked, set up the project for task management:

1. **Task list** — look for an existing task file:
   - Check CLAUDE.md for an `## Autopilot` section pointing to a task list
   - Glob for `TASKS.md`, `TODO.md`, `tasks.md` at project root
   - If found with a non-canonical name: rename in place to `TASKS.md` (e.g. `git mv TODO.md TASKS.md`), then migrate to the 5-section format (preserve existing tasks in Backlog; if it already has the 5 sections, leave content as-is). Assign `TB-N` IDs to any tasks that lack them.
   - If not found: create `TASKS.md` at project root with the empty 5-section template below
2. **Briefing directory** — create `.autocc/tasks/` (if not exists)
3. **Progress log** — look for an existing progress file (glob for `**/progress.md`). If found, keep it where it is. If not found, create `.autocc/progress.md`.
4. **CLAUDE.md** — add or update the `## Autopilot` section (see template below) with the **actual resolved paths** from steps 1-3. Do not overwrite other sections. The paths must reflect where the files actually are, not hardcoded defaults.

## Task List Format (`TASKS.md`)

The task list has exactly 5 sections, always in this order:

```markdown
# Tasks

## Active
<!-- Tasks currently being worked on by the agent. Max 1 for serial execution. -->

## Ready
<!-- Tasks with briefings prepared, ready to start. Agent picks from here. -->

## Backlog
<!-- Discovered tasks, not yet prepared. Agent can prioritize, append, or break down. -->

## Complete
<!-- Finished tasks. Keep for audit trail. -->

## Frozen
<!-- Excluded from agent work. Only the human moves tasks in/out of Frozen. -->
```

### Task line format

```
- [ ] **TB-1** **Task title** `#tag1` `#tag2` — One-line description [→ brief](.autocc/tasks/<slug>.md)
```

- **ID**: `TB-N`, bold. Assigned on creation, never changes. Sequential — read `next_id` from CLAUDE.md Autopilot section, increment after use.
- **Checkbox**: `- [ ]` unchecked, `- [x]` complete
- **Title**: bold, imperative verb ("Fix", "Add", "Implement")
- **Tags**: backtick-wrapped, `#`-prefixed. Link to features, areas, or epics. Not for priority — section position is priority.
- **Description**: one line, enough context to understand the task without reading the briefing
- **Brief link**: present for Ready and Active tasks. Optional for Backlog. Always present for Complete (preserves audit trail).

The ID is stable across section moves. Reference tasks by ID: "prep TB-5", "what's the status of TB-12".

### Section rules

| Section | Agent can add | Agent can remove | Agent can reorder | Briefing required |
|---------|:---:|:---:|:---:|:---:|
| Active | yes (from Ready) | yes (to Complete) | — | yes |
| Ready | yes (from Backlog) | yes (to Active) | yes | yes |
| Backlog | yes (new or breakdown) | yes (to Ready) | yes | no |
| Complete | yes (from Active) | no | no | preserved |
| Frozen | **no** | **no** | **no** | n/a |

**Frozen is human-only.** The agent never moves tasks into or out of Frozen, and never works on Frozen tasks. Frozen tasks are invisible to the agent's prioritization.

## Briefing File Format

Stored at `.autocc/tasks/<slug>.md`. Created by the agent when preparing a task (moving Backlog → Ready). This is the contract the agent works against.

### Slug naming

The slug is derived from the task title: lowercase, non-alphanumeric runs replaced with `-`, truncated to 40 chars, trailing `-` stripped. Examples:

- "Fix delete persistence bug" → `fix-delete-persistence-bug`
- "Add CSV export to formatters" → `add-csv-export-to-formatters`

**If a file with that slug already exists** (from a prior attempt or a similarly named task), append a numeric suffix: `fix-delete-persistence-bug-2.md`. Check before writing.

```markdown
# <Task title>

## Objective
What needs to be done. 1-3 sentences.

## Context
Why this matters. Link to related tasks, prior work, or requirements.

## Files
- `path/to/file.py` — what's relevant here
- `path/to/other.py` — what's relevant here

## Approach
Suggested implementation steps:
1. ...
2. ...
3. ...

## Verification
Commands to confirm the task is done:
- `test command here`
- `lint command here`
- Any other acceptance criteria

## Tags
#tag1 #tag2
```

The agent **reads relevant code** before writing the briefing. The Files section should list actual paths the agent verified exist. The Verification section should list commands the agent confirmed work (even if they currently fail — that's the point).

## CLAUDE.md Autopilot Section

Add this to the project's `CLAUDE.md`, using the actual resolved paths from init:

```markdown
## Autopilot

- Task list: `<resolved path to TASKS.md>`
- Task briefings: `.autocc/tasks/`
- Progress log: `<resolved path to progress.md>`
- Next task ID: TB-<N>
```

The `next_id` counter tracks the next available task ID. When creating a new task, use this value and increment it in CLAUDE.md. IDs are never reused — even if a task is deleted, its ID is retired.

The reflector reads these paths from CLAUDE.md. If the section is missing, it falls back to defaults (`TASKS.md`, `.autocc/tasks/`, `.autocc/progress.md`, `TB-1`).

## Task Lifecycle

```
            ┌─────────────────────────┐
            │        Backlog          │
            │  (discovered, unprepared)│
            └─────────┬───────────────┘
                      │ agent reads code,
                      │ writes briefing
                      ▼
            ┌─────────────────────────┐
            │         Ready           │
            │  (briefing prepared)    │
            └─────────┬───────────────┘
                      │ agent picks next
                      ▼
            ┌─────────────────────────┐
            │        Active           │
            │  (work in progress)     │
            └─────────┬───────────────┘
                      │ agent completes,
                      │ commits, updates board
                      ▼
            ┌─────────────────────────┐
            │       Complete          │
            │  (done, auditable)      │
            └─────────────────────────┘

   Frozen: human-managed, outside the lifecycle
```

### Prep step (Backlog → Ready)

When the agent prepares a task:

1. Check if the task already has a `[→ brief]` link (from a previous attempt).
   - **If briefing exists:** read it. Check `## Attempts` for unresolved blockers. If workable, move to Ready as-is.
   - **If no briefing:** explore the relevant code, write a briefing to `.autocc/tasks/<slug>.md`, add the `[→ brief]` link.
2. Move the task line from Backlog to Ready.
3. Prep is triggered when both Active and Ready are empty — prep up to 3 tasks at a time.

### Execute step (Ready → Active)

1. If Active is non-empty: resume the active task.
2. If Active is empty: move the top Ready task to Active, start work.
3. Each section is a **priority queue** — top = highest priority. Agent and human can reorder.

### Complete step (Active → Complete / Backlog)

Three outcomes:

- **Complete:** mark `- [x]`, move to Complete. Commit changes. Append to progress.md.
- **Incomplete** (made progress, not done): commit partial progress. Move to bottom of Backlog. Update briefing with `## Attempts` entry documenting progress and what remains.
- **Blocked** (can't proceed): commit any partial progress. Move to bottom of Backlog. Update briefing with `## Attempts` entry documenting the blocker.

Incomplete/blocked tasks keep their `[→ brief]` link. The briefing accumulates attempt history, so the next prep cycle can review what happened and decide if the task is now workable.

## Integration with reflector

- **Reflector** is the brain: reads TASKS.md, preps tasks (Backlog → Ready), executes them (Ready → Active → Complete/Backlog), documents progress. See `/reflector` skill for the full loop.
- The task list is the shared state between the human and the agent.
