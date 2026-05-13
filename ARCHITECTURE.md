# Architecture

`autocc` is three things glued together:

1. **A flag file** (`.autocc/flag`) — the on/off switch
2. **A hook script** (`autocc-hooks.py`) — the actual mechanism that changes Claude's behavior when the flag is set
3. **A set of skills** (`/afk`, `/reflector`, `/taskboard`, …) — the work loop and task-board protocol the agent follows

Plus a statusline shell script, which is load-bearing for one specific reason (see below).

## The flag

`.autocc/flag` is an empty file. Its presence in a project's root is the signal that the user is AFK and the agent should run unattended.

Everything is gated on this file. The hook returns a no-op if it doesn't exist. The skills check for it. The user removes it to turn autopilot off.

The agent **never** removes the flag — only the user does, via `/afk` "back" or by deleting it manually. This is deliberate: if the agent could remove its own kill switch, it could escape the unattended-mode constraints.

## The hook

`~/.claude/hooks/autocc-hooks.py` is one Python script. It's registered in `~/.claude/settings.json` against five Claude Code hook events, where each event invokes the same script with the event name as a positional argument (`python3 ~/.claude/hooks/autocc-hooks.py PreToolUse`, etc.). The script dispatches internally based on `sys.argv[1]` and the stdin JSON payload.

The hook is small (~250 lines), stateless, and gated on the flag file: when `.autocc/flag` is absent, every event returns a no-op `{}` and Claude Code's default behavior runs unchanged.

### ⚠️ Permission model — unconditional auto-approval

**When the flag is set, the `PermissionRequest` branch returns `{"behavior": "allow"}` for every request, with no inspection of tool name or arguments.** This is by design: autonomous operation can't pause on interactive prompts. But it has direct security implications, and the operator should pair autocc with at least one additional control:

1. **Inherent to autonomous mode.** The hook does not classify or filter — it grants the agent the full authority of Claude Code's tool surface for the duration of the run.
2. **Recommended: enable Claude Code's built-in auto mode.** Auto mode performs its own classification of tool calls before they reach the hook. When auto mode passes a call through, no `PermissionRequest` fires and the hook is a no-op for that call — i.e., the auto-mode classifier becomes the effective gate. This is meaningfully safer than autocc's blanket allow.
3. **Preferred: run autopilot in an OS-level sandbox.** Claude Code's tool surface includes shell access to the invoking user's home directory; that defines the practical blast radius. For unattended runs, isolate that radius at the OS level — a separate restricted user, a container, or a VM. The agent's authority cannot escape the sandbox even when prompt-injection or a skill regression slips past the other controls.

`permissions.deny` rules in `~/.claude/settings.json` are enforced by Claude Code **before** the hook runs, so they hold under autopilot. Use them as a hard-block layer for known-bad patterns.

### Events handled

| # | Event (settings.json key) | Matcher | Decision when flag is set | Decision when flag is absent |
|---|---|---|---|---|
| 1 | `PreToolUse` | `AskUserQuestion` | Deny with "make your best judgment, log to `.autocc/decisions.log`" | No-op |
| 2 | `PreToolUse` | `EnterPlanMode` | Deny with "skip plan mode, proceed" | No-op |
| 3 | `PermissionRequest` | (all) | `{"behavior": "allow"}` + log | No-op |
| 4 | `Elicitation` | (all) | Deny with "use safe defaults" | No-op |
| 5 | `Stop` | (all) | See "Stop logic" below | No-op |
| 6 | `PostCompact` | (all) | See "PostCompact logic" below | No-op |

PreToolUse with any *other* `tool_name` (Bash, Edit, Write, etc.) also no-ops — the settings.json matcher should keep them out, but the script defends against an over-broad matcher too.

### Per-event detail

**1. `PreToolUse(AskUserQuestion)` → deny.** When the agent is about to ask the human a question, the hook denies the tool call and returns a `reason` string telling the agent to make its own judgment and log the reasoning to `.autocc/decisions.log`. This prevents the loop from blocking on human input while the human is away.

**2. `PreToolUse(EnterPlanMode)` → deny.** Plan mode interactively pauses for human approval of a proposed plan. Same deny pattern, with reason "skip plan mode and proceed directly with implementation."

**3. `PermissionRequest` → auto-allow.** When Claude Code is about to prompt the user to approve a tool call (Bash, Edit, etc.), the hook returns `hookSpecificOutput.decision = {"behavior": "allow"}` and logs the request. See the **"Permission model — unconditional auto-approval"** callout above for the safety implications and recommended additional controls. Static `permissions.deny` rules in `settings.json` still apply (they're enforced by Claude Code before this hook runs).

**4. `Elicitation` → deny.** Generic input-elicitation requests are denied with "use safe defaults, document what was skipped."

**5. `Stop` → conditional block.** This is the load-bearing one. When the agent would otherwise stop and `.autocc/flag` is present, the hook decides based on board state and the `stop_hook_active` flag from Claude Code:

1. If `stop_hook_active` is true (we already nudged once and Claude tried to stop again), the hook removes the flag and lets stop proceed. Prevents infinite "no, keep going" loops.
2. If the task board's `## Active`, `## Ready`, and `## Backlog` sections all contain zero unchecked `- [ ]` lines, the hook removes the flag and allows stop — the work is done.
3. Otherwise, the hook returns `{"decision": "block", "reason": "...invoke /reflector and continue..."}` and Claude resumes the loop.

The task-board path comes from `CLAUDE.md`'s `## Autopilot` section (`Task list: \`path\``), falling back to `TASKS.md` in the project root.

**6. `PostCompact` → inject checkpoint.** Long autopilot sessions hit Claude Code's auto-compaction threshold (~70-80% context). When compaction fires, the conversation is summarized and most state is lost — including the reflector's loop awareness. The reflector writes a checkpoint to `.autocc/checkpoints/<ISO-timestamp>.md` whenever context usage crosses 70%. After compaction, this hook reads the latest checkpoint (filenames sort lexicographically = chronologically) and injects it back as `additionalContext` with the instruction "resume /reflector immediately." When no checkpoint exists, it falls back to a generic resume nudge.

### State files the hook touches

| Path | Read | Written |
|---|:---:|:---:|
| `.autocc/flag` | ✓ (presence check) | removed (Stop event, on terminate-loop conditions) |
| `.autocc/decisions.log` | — | ✓ (appended) |
| `.autocc/checkpoints/*.md` | ✓ (latest) | — |
| `TASKS.md` (or `CLAUDE.md`-specified path) | ✓ (board emptiness) | — |
| `CLAUDE.md` | ✓ (task list path) | — |

The hook never writes to TASKS.md, briefings, progress.md, or any code under the project — those are the agent's domain.

### Resolving the project root

The hook reads `CLAUDE_PROJECT_DIR` from the environment, falling back to `cwd` if unset. Claude Code sets `CLAUDE_PROJECT_DIR` to the session root, so the flag is found regardless of which subdirectory the agent has navigated into during the run.

### Test coverage

`tests/test_autocc_hook.py` exercises the hook as a subprocess (matching Claude Code's invocation pattern) with synthetic stdin. 21 tests cover all 17 distinct decision paths:

- All 6 event types under flag-absent (no-op assertions) — 7 tests
- AskUserQuestion / EnterPlanMode / other-tool PreToolUse under flag-set — 3 tests
- PermissionRequest under flag-set, for Bash and Edit (log formatting) — 2 tests
- Elicitation under flag-set — 1 test
- Stop branches: open work, already-nudged, board empty, TASKS.md missing, custom CLAUDE.md task path — 5 tests
- PostCompact branches: checkpoint exists, no checkpoint — 2 tests
- Cross-cutting: `CLAUDE_PROJECT_DIR` honored over `cwd` — 1 test

Run with `pytest tests/test_autocc_hook.py -v`. No API cost.

## The statusline (yes, it's load-bearing)

`~/.claude/statusline-command.sh` is registered as Claude Code's `statusLine` command. Its primary side effect: it writes the full statusline JSON input to `<project_dir>/.autocc/context.json` every time it's called.

That JSON contains `context_window.used_percentage`. The reflector reads it during the CHECKPOINT step to decide whether to snapshot. Without this file, the 70% checkpoint trigger doesn't fire, and PostCompact recovery degrades to "resume blind."

(The statusline is also a normal statusline — shows user/host/cwd/git-branch/model/context% — but the side effect is what's actually critical for autocc.)

## The skills

```
   /afk
    │  creates .autocc/flag,
    │  invokes ↓
    │
   /reflector ───┐
    │ loop:      │
    │            │
    │  DISCOVER  │ ← (Active+Ready empty?) /housekeeping ──┐
    │     │      │                                          │
    │     ▼      │                          deduplicated, ─┘
    │  prep      │                          appended to Backlog
    │  Backlog→Ready
    │     │
    │  EXECUTE   │ ← move Ready→Active, follow briefing
    │     │
    │  VERIFY    │ ← run briefing's Verification commands
    │     │
    │  COMPLETE  │ ← commit locally, move Active→Complete
    │     │      │   or back to Backlog if incomplete/blocked
    │     │      │   /commit-changes captures the doc-update + commit
    │  CHECKPOINT │ ← if context >= 70%, write checkpoint .md
    │     │
    └─────┘  GO TO DISCOVER
```

Skills are markdown files (with YAML frontmatter) loaded into the Claude Code session. They describe the loop to the agent in natural language. There's no Python execution path through them — they're prompts.

## The task board

`TASKS.md` is the human-and-agent shared state. Five sections, in priority order top-to-bottom within each section.

- **Active**: at most 1 task. The agent moves Ready→Active when it picks one up.
- **Ready**: tasks with briefings prepared. The agent picks from the top.
- **Backlog**: discovered tasks. May or may not have briefings.
- **Complete**: append-only audit trail.
- **Frozen**: human-only. The agent never reads, prepares, or works on Frozen tasks. This is the human's "don't touch" list.

Each task has a stable `TB-N` ID assigned on creation and never reused. The ID survives section moves, so progress.md, briefings, and commit messages can reference tasks unambiguously.

Briefings live in `.autocc/tasks/<slug>.md` and have a fixed structure: Objective, Context, Files, Approach, Verification, optional Tags. The reflector reads the briefing, follows the Approach, and runs the Verification commands to decide outcome.

## The on-disk state model

```
project/
├── CLAUDE.md                       — has ## Autopilot section pointing at task list paths
├── TASKS.md                        — 5-section board, human + agent edit
└── .autocc/
    ├── flag                        — empty file, presence = autopilot on
    ├── decisions.log               — appended by the hook for every suppressed prompt
    ├── progress.md                 — narrative log, appended by reflector per task
    ├── context.json                — written by statusline; read by reflector for checkpoint trigger
    ├── tasks/<slug>.md             — briefings; one per TB-N
    ├── checkpoints/<ts>.md         — written by reflector at 70% context; read by PostCompact
    └── metrics/<ts>.json           — per-session summary written before idle stop
```

`flag` and `context.json` are runtime-only — gitignore them. `tasks/`, `progress.md`, `decisions.log`, and the metrics dir typically *are* committed; they're the audit trail.

## What's deliberately not here (v1)

- **No daemon.** Everything happens inside the Claude Code session. The closest thing to a "background process" is the agent looping on itself, gated by the Stop hook.
- **No parallel workers.** v1 is single-threaded. Future versions may add an orchestrator pattern for dispatching tasks to background sessions.
- **No remote state.** All state is local to the project's `.autocc/` directory. No network, no auth, no central server.
- **No model-specific code.** autocc works with whatever model your Claude Code session is configured to use.
