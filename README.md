# autocc — autopilot for Claude Code

Run a Claude Code session unattended against a task board.

`autocc` is a small collection of **skills** and **hooks** for Claude Code. Together they let you say "work on the task board until you run out of tasks," walk away, and come back to a stack of commits with an audit trail.

It's intentionally tiny:

- One Python hook (`autocc-hooks.py`) that gates on a flag file
- One shell statusline script
- Six skills (`/afk`, `/reflector`, `/taskboard` + `/tb`, `/housekeeping`, `/commit-changes`)
- A `TASKS.md` task-board format

No daemon. No background process. No new model. Everything happens inside your normal Claude Code session — the hook just suppresses interactive prompts and the skills define the work loop.

## Install

autocc is install-from-source — there's no PyPI release. Install with `pipx` (or `uv tool`) directly from the git repo:

```bash
pipx install git+https://github.com/atom-tech-consulting/autocc.git
# or:
uv tool install git+https://github.com/atom-tech-consulting/autocc.git
```

Or clone and install editable for hacking:

```bash
git clone https://github.com/atom-tech-consulting/autocc.git
cd autocc && uv venv && uv pip install -e .
```

Then wire it into `~/.claude/`:

```bash
autocc install            # rsync skills, copy hooks, patch ~/.claude/settings.json
```

`autocc install` shows you a unified diff of the proposed `~/.claude/settings.json` change before applying it. Pass `-y` to skip the prompt, or `--dry-run` to preview without writing.

```bash
autocc status             # show what's installed
autocc uninstall          # reverse install (removes artifacts + strips settings.json entries)
```

## Quickstart

In any project:

```bash
# 1. Initialize the task board (creates TASKS.md + adds the Autopilot section to CLAUDE.md)
claude   # then in the session: /taskboard init

# 2. Add a task or two
#    (Edit TASKS.md by hand, or describe them to Claude in the session.)

# 3. Go AFK
/afk
```

`/afk` creates `.autocc/flag`, then invokes `/reflector`. The reflector loop reads the next task off the board, executes it, commits locally, and moves on. The hook file ensures Claude doesn't stop to ask you questions while you're gone — questions are auto-suppressed with "decide yourself, document your reasoning in `.autocc/decisions.log`."

When you come back, send any message — say "back" or "stop" to end the loop.

### Try it on a known-good fixture

If you want to see a complete reflector run before pointing autocc at your own code, [`examples/taskflow`](examples/taskflow) is a small Python project with three workable tasks (one bug, one missing feature, one missing tests) and a populated task board. See [its README](examples/taskflow/README.md) for the walkthrough.

## What you get on disk

After `/taskboard init` and a reflector session:

```
your-project/
├── CLAUDE.md                       # ## Autopilot section added
├── TASKS.md                        # the 5-section board
└── .autocc/
    ├── flag                        # presence = autopilot on (created by /afk)
    ├── decisions.log               # suppressed-prompt audit trail
    ├── progress.md                 # narrative log of every task
    ├── context.json                # context-window snapshot (written by statusline)
    ├── tasks/                      # per-TB-N briefing markdown
    ├── checkpoints/                # snapshots written at 70% context (used by PostCompact)
    └── metrics/                    # per-session JSON
```

## How it works

```
                ┌─────────────────────┐
                │       /afk          │  ─ creates .autocc/flag
                └──────────┬──────────┘     invokes /reflector
                           ▼
                ┌─────────────────────┐
                │     /reflector      │ ─ loop: discover → execute →
                │   (in-session)      │   verify → complete → checkpoint
                └──────────┬──────────┘
                           │  agent might try to stop, or ask a question
                           ▼
                ┌─────────────────────┐
                │  autocc-hooks.py hook  │ ─ deny AskUserQuestion / EnterPlanMode
                │  (PreToolUse +      │   block Stop with "keep working"
                │   Stop + PostCompact)│  re-inject latest checkpoint after compaction
                └─────────────────────┘
```

The flag file is the kill switch: delete `.autocc/flag` and the hook returns to no-op mode immediately.

## The task board (`TASKS.md`)

Five sections, in order:

```markdown
# Tasks

## Active        — at most one task, currently being worked on
## Ready         — task has a briefing, ready to pick up
## Backlog       — discovered, not yet prepared
## Complete      — done, kept for audit
## Frozen        — human-only; the agent never touches these
```

Task lines look like:

```
- [ ] **TB-12** **Add CSV export** `#export` — formatters/csv.py [→ brief](.autocc/tasks/add-csv-export.md)
```

Briefings are markdown files in `.autocc/tasks/`. They define Objective, Context, Files, Approach, and Verification — the agent works against them.

See `/taskboard` for the full reference.

## Skills

| Skill | Purpose |
|---|---|
| `/afk` | Set the flag, start reflector. One-shot "go AFK." |
| `/reflector` | The work loop. Discover → execute → verify → complete → checkpoint. |
| `/taskboard` (alias `/tb`) | Task-board format, lifecycle, briefing protocol. Has `/tb init`, `/tb prep`, `/tb brief`. |
| `/housekeeping` | Scan the codebase for lint errors, broken tests, dead code, stale comments. Returns task lines. Reflector calls this when the board is empty. |
| `/commit-changes` | Wrap up: commit + update TASKS.md + update progress.md. |

## Safety model

### ⚠️ Permission auto-approval — read this first

**When `.autocc/flag` is set, autocc auto-approves every `PermissionRequest` unconditionally.** This is by design — autonomous operation can't pause on every interactive prompt — but it means the agent has the full authority of your Claude Code tool surface for the duration of the run. You should understand and bound that authority before pointing autocc at anything important:

1. **(a) autocc approves all permission requests by design.** The hook doesn't inspect tool name or arguments; every `PermissionRequest` returns `{"behavior": "allow"}`. This is what allows the loop to make progress without you.

2. **(b) Strongly recommended: turn on Claude Code's built-in auto mode.** Auto mode handles permission auto-approval natively and applies Anthropic's own classifier before allowing tool calls. When auto mode is on, autocc's `PermissionRequest` hook becomes a no-op (no prompt to short-circuit — auto mode already passed it through), so the classifier is what's actually gating the agent. This is meaningfully safer than autocc's blanket allow.

3. **(c) Preferred: run autopilot sessions in a system-level sandbox.** Claude Code's tool surface includes shell access to your home directory, so its blast radius is whatever the *invoking OS user* can touch. For unattended runs, the most robust safety measure is to isolate that radius at the OS level — a separate macOS / Linux user with restricted privileges, a container, or a VM. The agent's authority then can't escape the sandbox even if a prompt-injection or skill-regression slips a destructive action past everything else.

`permissions.deny` rules in `~/.claude/settings.json` still apply under autopilot — they're enforced by Claude Code before the hook runs. Use them to hard-block specific patterns (e.g., `Bash(rm -rf *)`, `Bash(git push --force*)`) regardless of which mode you're in.

### What autocc still does on top of auto mode

Auto mode covers permission auto-approval. autocc on top of that adds:

- **Suppresses `AskUserQuestion`** — auto mode doesn't answer agent questions, just permissions. The hook denies these with "decide yourself, log to `.autocc/decisions.log`."
- **Suppresses `EnterPlanMode` and Elicitation** — same reasoning.
- **Blocks Stop** — keeps the agent on the loop until the task board is exhausted, instead of letting it idle out.
- **Survives auto-compaction** — `PostCompact` re-injects the latest checkpoint so the reflector loop continues seamlessly in the new context.
- **Provides the task-board loop itself** — `/reflector`, `/taskboard`, `/housekeeping`, briefings, progress.md.

Auto mode handles approvals, autocc handles "keep working on the right things while I'm away." They compose.

### Reflector guardrails (conventions, not enforcement)

The reflector skill is told: **"if `git checkout -- .` can undo it, it's safe."** It can edit any tracked file, add/remove dependencies, run tests — anything reversible. It's instructed *not* to:

- `git push` or any remote write
- Modify your `~/.bashrc` / `~/.gitconfig` / global state
- Run commands against external services (APIs, DBs, queues)
- Modify or remove `.autocc/flag` (only `/afk` controls it)

These are prompt-level conventions in the skill markdown, **not enforced by code**. A regression in the skill or a prompt injection from a malicious dependency could bypass them. The OS-level sandbox in (c) above is what actually contains the agent.

## Configuration

### `CLAUDE.md` — `## Autopilot` section

`/taskboard init` adds this to your project's `CLAUDE.md`:

```markdown
## Autopilot
- Task list: `TASKS.md`
- Task briefings: `.autocc/tasks/`
- Progress log: `.autocc/progress.md`
- Next task ID: TB-1
```

The reflector reads these paths. If the section is missing, defaults are used.

### Environment

- `CLAUDE_PROJECT_DIR` — set by Claude Code, used by the hook to find the right `.autocc/flag` regardless of which subdirectory the agent is currently in. You don't set this.
- `CLAUDE_HOME` — override `~/.claude` for testing (used by `autocc install`).

## Uninstall

```bash
autocc uninstall
```

Removes the six skill directories from `~/.claude/skills/`, deletes the hook scripts, and strips autocc-managed entries from `~/.claude/settings.json` (leaving any other hook entries you have intact).

Per-project state in `.autocc/` is left in place — delete the directory yourself if you don't want it.

## Roadmap

Things considered but **not in v1**:

- **Parallel workers** — dispatching tasks to background sessions via the Agent SDK. Likely a follow-up release.
- **Permission gating** — explicitly *not* shipped. Claude Code's built-in auto mode handles permission auto-approval natively, so a custom PreToolUse Bash filter is largely unnecessary. See ["Safety model"](#safety-model) above.
- **`/ideation`** — a manual task-proposal skill. Standalone, didn't make the core loop cut.

## Tests

Two tiers:

```bash
# Unit tier — fast, no API cost. Runs by default.
pytest                                  # 29 tests: 8 installer + 21 hook

# Smoke tier — real CLI against examples/taskflow. ~$2-4 per run on Opus.
# AUTOCC_REAL_SDK=1 runs BOTH the Claude smoke (real `claude` CLI) and the
# Codex smoke (real `codex` CLI; requires `codex login` completed).
AUTOCC_REAL_SDK=1 pytest tests/smoke/   # end-to-end reflector tests (Claude + Codex)
```

See [`tests/smoke/README.md`](tests/smoke/README.md) for what the smoke verifies and how it's gated.

## License

MIT — see [LICENSE](LICENSE).
