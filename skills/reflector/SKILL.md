---
description: "Find and work on useful tasks autonomously — code cleanup, testing, tasks.md items — without irreversible actions. Use when idle or on autopilot."
user_invocable: true
---

# Reflector

Autonomous work loop. Picks tasks from the taskboard, executes them, documents progress. Designed for unattended operation (pairs with `.autocc/flag` and `/afk`).

## When to use

- Human invokes `/reflector` before going AFK
- Agent has finished assigned work and wants to stay productive
- Continuous improvement passes on the codebase

## Project-root resolution

This skill, and the autopilot stop-hook it pairs with, both anchor at
the project root. Resolve the root with this provider-neutral fallback
chain (first set wins):

    PROJECT_DIR="${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"

`AUTOCC_PROJECT_DIR` is the portable override; `CLAUDE_PROJECT_DIR`
covers Claude Code; `CODEX_PROJECT_DIR` covers Codex; `$PWD` is the
last-resort fallback when neither harness exports a project-root
variable. The agent's native `CLAUDE.md` parse (below) and the
`.autocc/` reads/writes throughout this skill all anchor at
`$PROJECT_DIR`.

## Bootstrap (run FIRST, before any work)

1. **Read CLAUDE.md `## Autopilot` section** for resolved paths
   (read it at `$PROJECT_DIR/CLAUDE.md`):
   - Task list (default: `TASKS.md`)
   - Task briefings directory (default: `.autocc/tasks/`)
   - Progress log (default: `.autocc/progress.md`)
   - Next task ID (default: `TB-1`)
   - If the Autopilot section is missing, fall back to defaults above

2. **Verify the files exist.** If TASKS.md is missing, tell the user to run `/taskboard init` and stop.

3. Store the resolved paths and refer to them as `TASK_FILE`, `BRIEFINGS_DIR`, `PROGRESS_FILE`, and `NEXT_ID` throughout.

## Core principles

1. **No irreversible actions.** Do not push, publish, deploy, delete branches, drop data, or modify shared state. All work stays local.
2. **Move forward without human help.** Do not use AskUserQuestion. Make your best judgment and document it.
3. **Document everything.** Append progress to `PROGRESS_FILE` so the human can review when they return.

## Continuous execution loop

**CRITICAL: You MUST keep working in a continuous loop. Do NOT stop, summarize, or wait for user input between tasks. The only reasons to stop are listed below under "When to stop."**

After bootstrap, enter the work loop. When running under autopilot (`.autocc/flag` is set), the Stop hook blocks idle — if Claude would otherwise stop, the hook returns a block decision instructing Claude to invoke `/reflector` and continue working.

```
LOOP:
  0. INTERRUPTS   — handle pending messages and user input
  1. DISCOVER     — check taskboard, prep if needed
  2. EXECUTE      — pick a task and do the work
  3. VERIFY       — confirm correctness
  4. COMPLETE     — commit, update taskboard, document
  5. CHECKPOINT   — check context usage
  6. GO TO 0
```

**Between tasks:** Do NOT output a summary or ask what to do next. Immediately start step 0 again. Every time you finish a task, your very next action must be a tool call — never a text-only response.

### 0. INTERRUPTS

Before starting or resuming work, check for pending notifications:

- **Background task completions:** if any `run_in_background` process has completed, process its output (test suites, builds, etc.). For task-related processes: incorporate the result into the Active task's progress.
- **User messages:** if the user sent a message, respond to them. If they say "stop" or "back", exit the loop. Otherwise answer their question and resume.

This step is lightweight — if there are no pending notifications, proceed immediately to step 1. Do NOT proactively poll or check for messages; just handle ones that have already arrived as background task completions.

### 1. DISCOVER

Read `TASK_FILE` and check the sections:

- **If Active is non-empty:** skip discovery, go to step 2 (resume the active task).
- **If Active is empty and Ready is non-empty:** skip discovery, go to step 2.
- **If both Active and Ready are empty:** run housekeeping scan, then prep up to 3 tasks.

#### Housekeeping scan

Invoke `/housekeeping` to scan the codebase for maintenance tasks (lint errors, broken tests, dead code, stale comments). It returns taskboard-formatted task lines with `#housekeeping` tags, already deduplicated against TASKS.md.

Append the returned tasks to the **bottom of Backlog** in `TASK_FILE`, assigning `TB-N` IDs from `NEXT_ID` (increment in CLAUDE.md for each).

#### Prep tasks (Backlog → Ready)

After the housekeeping scan, prep up to 3 tasks from Backlog → Ready. **At least 1 must be a `#housekeeping` task** if any are available in Backlog. The rest are picked by priority (top of Backlog).

For each task to prep:
1. Check if it has an existing briefing (`[→ brief]` link).
   - **If briefing exists:** read it. Check `## Attempts` (if any) for unresolved blockers. If workable, move to Ready. If still blocked, skip and try the next.
   - **If no briefing:** explore the relevant code, assess workability. If yes, write a briefing to `BRIEFINGS_DIR/<slug>.md` (see `/taskboard` for format), add the `[→ brief]` link. Assign a `TB-N` ID if missing (use `NEXT_ID`, increment in CLAUDE.md).
2. Skip tasks that are blocked or lack enough info — leave in Backlog.

If no tasks could be prepped (all blocked or Backlog empty), stop and summarize.

### 2. EXECUTE

- **If Active has a task:** check for in-flight background processes (see below), then read its briefing (including any Attempts section) and resume work.
- **If Active is empty:** move the top Ready task to Active in `TASK_FILE`, then read its briefing and start work.
- **If the task has no briefing** (no `[→ brief]` link): write one before starting work. Explore the relevant code, write the briefing to `BRIEFINGS_DIR/<slug>.md`, add the link to the task line in `TASK_FILE`. Then proceed with the work.
- Do the work: edit files, run commands, fix issues. Follow the briefing's Approach and Verification sections.

#### Background process awareness

Before resuming an Active task, check if there are background processes still running that relate to it (e.g., a test suite, a build). You can tell by checking if you have pending `run_in_background` completions that haven't been processed yet.

If background work is in flight for the Active task:
- **Do NOT duplicate the work** — don't start the same test/build/command again.
- **Do complementary work** — if tests are running, work on a different part of the task (e.g., write docs, fix lint, prepare the next step).
- **If nothing complementary to do**, skip to a Ready task instead. Leave the Active task in Active — it will be resumed when the background process completes and you process the result in step 0 (INTERRUPTS).
- **If no Ready tasks either**, move to DISCOVER and prep from Backlog. The Active task stays active.

### 3. VERIFY

Run the verification commands from the briefing. Determine the outcome:

- **Complete:** all verification passes, task is done.
- **Incomplete:** made progress but not finished (e.g., fixed 2 of 3 issues, tests partially passing).
- **Blocked:** cannot proceed (needs human input, missing access, external dependency, failed after 2 honest attempts).

### 4. COMPLETE

Based on the outcome from step 3:

**If Complete:**
- `git add` + `git commit` locally (do NOT push). Clear commit message referencing the TB-N ID.
- Mark `- [x]` and move to Complete section in `TASK_FILE`.
- Append to `PROGRESS_FILE`:
  ```
  ## [timestamp] TB-N: <task title>
  - **Result:** complete
  - **Summary:** <what was done, 1-3 sentences>
  - **Files:** <list of changed files>
  - **Verified:** <how — tests passed, lint clean, etc.>
  ```

**If Incomplete:**
- `git add` + `git commit` partial progress locally (so work isn't lost).
- Move task back to Backlog (bottom) in `TASK_FILE`. Keep the `[→ brief]` link.
- Update the briefing file — append to `## Attempts`:
  ```
  ### [timestamp] Attempt N
  - **Result:** incomplete
  - **Progress:** what was accomplished
  - **Remaining:** what's left to do
  ```
- Append a brief note to `PROGRESS_FILE`.

**If Blocked:**
- Commit any partial progress locally.
- Move task back to Backlog (bottom) in `TASK_FILE`. Keep the `[→ brief]` link.
- Update the briefing file — append to `## Attempts`:
  ```
  ### [timestamp] Attempt N
  - **Result:** blocked
  - **Progress:** what was accomplished (if any)
  - **Blocker:** what's preventing completion
  ```
- Append a brief note to `PROGRESS_FILE`.

### 5. CHECKPOINT

Check context usage:

```bash
PROJECT_DIR="${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}"
used_pct=$(jq -r '.context_window.used_percentage // empty' "$PROJECT_DIR/.autocc/context.json" 2>/dev/null)
```

If `context.json` is missing or `used_pct` is empty, skip checkpoint and go to step 6. (Today only the Claude Code statusline writes `context.json`; under Codex this read returns empty and the branch no-ops — a polyfill for Codex token-usage tracking is a separate follow-up.)

**Below 70%:** No checkpoint. Go to step 6.

**At or above 70%:** Write a checkpoint file to `.autocc/checkpoints/[timestamp].md`:

```
# Checkpoint [timestamp] (N% context used)

## State
- Last completed task: TB-N [description]
- Completed this session: [N tasks, list TB-N titles]
- Next task: TB-N [description and why]
- Blocked items: [if any, with TB-N IDs]

## Status
continuing
```

Also append a one-line summary to `PROGRESS_FILE`:
```
### [timestamp] Checkpoint (N% used) — completed: TB-N → next: TB-N
```

Then continue to step 6. **Never stop proactively** — keep working until auto-compaction fires. The PostCompact hook injects the latest checkpoint into the resumed session.

### 6. GO TO 1

Immediately start discovering the next task. Do NOT stop.

## Handling bigger tasks

Not every task is a one-line fix. For larger tasks (new skills, refactors, multi-file changes):

1. **Attempt it.** Complexity is not a blocker. If a task is in Backlog, it's workable until proven otherwise by actually trying.
2. **Break it down.** Decompose into steps. Commit after each meaningful step so progress isn't lost.
3. **Use incomplete, not blocked.** If you run out of context or hit diminishing returns, mark as incomplete with progress documented. The next reflector session picks up where you left off via the briefing's Attempts section.
4. **Blocked means genuinely stuck.** Missing access, external dependency, needs human decision on a design question. "This looks hard" or "this requires significant implementation" are NOT blockers.

The incomplete→Backlog flow exists precisely for big tasks. Make progress, commit it, document what's left.

## Session report (write before stopping)

Before going idle on an empty board, write a session summary to `PROGRESS_FILE` and output it:

```
## [timestamp] Reflector session complete

- **Tasks completed:** N (list TB-N IDs)
- **Tasks incomplete/blocked:** N (list TB-N IDs with reasons)
- **Commits:** N
- **Context usage:** N%
- **Board state:** Active: N, Ready: N, Backlog: N
- **Stop reason:** board exhausted / all blocked / user requested
```

Also write a JSON metrics file to `.autocc/metrics/<timestamp>.json`:

```json
{
  "timestamp": "ISO8601",
  "tasks_completed": ["TB-N", "..."],
  "tasks_incomplete": ["TB-N", "..."],
  "tasks_blocked": ["TB-N", "..."],
  "total_tasks_attempted": 0,
  "commits": 0,
  "context_used_pct": 0,
  "stop_reason": "board_exhausted"
}
```

This ensures the human always has a report to review, even if they don't return to the session. Commit the progress update before going idle.

## When to stop (the ONLY valid reasons)

- The user sends a message saying "stop" or "back" (the `/afk` skill handles flag removal)
- Both Ready and Backlog are empty — no tasks remain
- All Backlog tasks are blocked and no implicit work was found (after two full passes)

**Always write the session report before stopping.**

**NEVER remove the autopilot flag yourself.** Do not run `rm .autocc/flag`. Only the user controls the flag via `/afk`. If you think you should stop, just let the turn end — the Stop hook will either nudge you back to work or let you stop (if `stop_hook_active` is true, meaning you were already nudged once and genuinely have nothing to do).

**NOT valid reasons to stop:**
- "Remaining tasks are complex" — attempt them
- "Remaining tasks need design decisions" — make your best judgment, document it
- "Remaining tasks are outside housekeeping" — the reflector works on ALL task types, not just cleanup
- "I've done enough for this session" — keep working until compaction fires; PostCompact hook resumes the loop in the next session automatically
- "Active task is running remotely / in background" — the Active task stays active, but you MUST move to DISCOVER and prep Backlog tasks. Work on those while the remote process runs. A running background process is NOT a reason to stop the loop.
- "Remaining tasks can wait" — if they're in Backlog, prep and attempt them now

## Safety guardrails

**Guiding principle:** If `git checkout -- .` can undo it, it's safe. If it affects state outside the repo working tree, it's not.

**SAFE (allowed):**
- Modify any version-controlled file (source, config, docs, tests)
- Change package dependencies (package.json, pyproject.toml, Cargo.toml, etc.) — local and reversible
- Modify project environment files (`.env`, `.envrc`) — local and reversible via git
- Delete files that are tracked by git — reversible via `git checkout`
- Add/remove dev dependencies
- Run local commands (tests, linters, builds, scripts)

**UNSAFE (never do):**
- Remove or modify `.autocc/flag` — only the user controls autopilot via `/afk`
- `git push`, `git push --force`, or any remote operations
- Global installations (`pip install --user`, `npm install -g`, `brew install`)
- Global config changes (`~/.bashrc`, `~/.gitconfig`, etc.)
- Modify CI/CD configs that auto-deploy on commit
- Run commands that affect external services (APIs, databases, message queues)
- Amend or rebase published commits

**ALWAYS:**
- Work in small, incremental changes — commit after each meaningful step
- Run tests after each change
- If tests fail after 2 attempts, mark incomplete (not blocked) and move on
- When in doubt about safety, skip the action (not the task) and document why

## Arguments

`/reflector` accepts an optional focus area:

- `/reflector` — full scan, use taskboard priority order
- `/reflector tests` — focus on test-related tasks
- `/reflector cleanup` — focus on code quality tasks
- `/reflector tasks` — only work from TASKS.md, no implicit discovery
