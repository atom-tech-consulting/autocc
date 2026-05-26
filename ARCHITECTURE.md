# Architecture

`autocc` is three things glued together:

1. **A flag file** (`.autocc/flag`) — the on/off switch
2. **A hook script** (`autocc-hooks.py` on Claude Code, `autocc-hooks-codex.py` on Codex) — the actual mechanism that changes the agent's behavior when the flag is set
3. **A set of skills** (`/afk`, `/reflector`, `/taskboard`, …) — the work loop and task-board protocol the agent follows

Plus a statusline shell script (Claude Code only), which is load-bearing for one specific reason (see below).

autocc targets two coding-agent CLIs — Claude Code (default) and OpenAI Codex (via `autocc install --agent codex`). The two providers share the same flag, the same skills, and the same per-project `.autocc/` state model; they diverge only in (a) the hook script's JSON wire shapes, (b) the on-disk install layout, and (c) two events that have no Codex analog. See **[Provider branches](#provider-branches)** below for the full breakdown, and `docs/codex-mapping.md` for the event-by-event mapping that grounds it.

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

### Provider branches

The hook's behavior is identical between providers — gate on the flag; deny interactive prompts; auto-allow permission requests; block premature Stop — but the wire formats and the install layout differ. `docs/codex-mapping.md` is the source of truth for the full event-by-event mapping; the summary here is just what's needed to understand the two scripts side-by-side.

**Two hook scripts, one per provider:**

- `autocc-hooks.py` is the Claude Code hook. Installed by `autocc install` (default) into `~/.claude/hooks/autocc-hooks.py` and registered in `~/.claude/settings.json` against five hook events (`PreToolUse`, `PermissionRequest`, `Stop`, `Elicitation`, `PostCompact`). Emits Claude Code's `hookSpecificOutput.decision.behavior` JSON shape for permission auto-approval and the `{"decision": "block", "reason": "..."}` shape for Stop continuation.
- `autocc-hooks-codex.py` is the Codex hook. Installed by `autocc install --agent codex` into `${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/hooks/autocc-hooks-codex.py` and registered in the plugin's `hooks.json` against the three Codex hook events autocc actually uses (`PreToolUse`, `PermissionRequest`, `Stop`). Emits Codex's `{"permissionDecision": "allow", "permissionDecisionReason": "AUTOPILOT: ..."}` JSON shape for permission auto-approval — the Codex binary literally rejects unsupported variants by string match, so the shape is load-bearing — and a `decision: "block"` + non-empty `reason` for Stop continuation (Codex rejects `decision:block` without a non-empty reason, also a string-match check).

The two scripts are kept as separate files (not a shared module) so each provider's wire format stays legible in one place; per `goal.md`, a generic plugin SDK that would let a third provider tap in is explicitly out of scope.

**Codex install layout — peer of the Claude `~/.claude/settings.json` patch.** Codex discovers plugins via marketplaces rather than by scanning a single config dir, so the Codex branch installs as a self-contained **plugin folder** plus a single **marketplace entry**:

```
${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/
├── .codex-plugin/plugin.json        # manifest (name, version, skills path, hooks path)
├── skills/<name>/SKILL.md           # same skill payload as the Claude install
├── hooks.json                       # registers PreToolUse / PermissionRequest / Stop,
│                                    # plus an env block setting AUTOCC_AGENT_NAME=Codex
│                                    # and AUTOCC_AGENT_EMAIL=noreply@openai.com
└── hooks/autocc-hooks-codex.py      # the Codex-shaped hook script described above

~/.agents/plugins/marketplace.json   # one plugins[] entry with source.path: ./plugins/autocc
                                     # — Codex resolves this against the marketplace's home
                                     # anchor, so it maps to ~/plugins/autocc/
```

`AUTOCC_CODEX_PLUGIN_ROOT` overrides the parent directory if you don't want the plugin under `~/plugins/`. Uninstall reduces to deleting the plugin folder and stripping autocc's `plugins[]` entry from the marketplace.

**Skill env-var contract — the same six skills run under both providers.** TB-4 decoupled the skill bodies from Claude-only env vars so the markdown is provider-neutral; the installer's Codex branch wires the matching vars via the plugin's `hooks.json` `env` block:

- `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}` — the resolution chain the `afk` and `reflector` skills use to locate the session root (the directory holding `.autocc/flag`, `CLAUDE.md`, `TASKS.md`). `AUTOCC_PROJECT_DIR` is the portable override (operator-set only); the rest of the chain picks up whichever provider's native var is in scope and falls back to `$PWD`. A future third provider can opt in by exporting `AUTOCC_PROJECT_DIR` — no skill edit needed.
- `${AUTOCC_AGENT_NAME:-Claude}` / `${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}` — the `commit-changes` skill interpolates these into the `Co-Authored-By` trailer it writes on every commit. The autocc Codex plugin's `hooks.json` `env` block sets them to `Codex` / `noreply@openai.com` so commits made under Codex are attributed correctly. Unset preserves the historical Claude-side trailer.

**Document-and-skip gaps under Codex.** Two of autocc's Claude-side hook events have no Codex hook-event analog at codex-cli 0.128.0, and one of its load-bearing side mechanisms (the statusline shell-out) has no Codex equivalent. These are accepted as documented limitations per `goal.md`'s non-goal on cross-provider parity:

- **PreToolUse(`AskUserQuestion`) / PreToolUse(`EnterPlanMode`)** — accept-as-limitation. Codex doesn't ship those tools, so the matcher `pre_tool_use` registration is harmless but never fires. Enforce the "don't ask" constraint via the autopilot skill prompt and Codex's `-a/--ask-for-approval=never` startup policy instead.
- **Elicitation hook** — accept-as-limitation, polyfill candidate. Codex emits `elicitation_request` Events but has no `Elicitation` hook event for autocc to auto-deny. A polyfill via an MCP server proxying `elicit/create` is plausible but deferred.
- **PostCompact hook** — accept-as-limitation, polyfill candidate. Codex auto-compacts (`context_compacted` Event fires) but exposes no `PostCompact` hook, so the Claude-side "re-inject latest checkpoint as `additionalContext`" mechanism has no place to attach. A polyfill via a `user_prompt_submit` hook conditioned on a recent compaction is plausible but deferred.
- **Statusline shell-out** — document-and-skip. Codex's `status_line` TUI config is a widget list, not a shell-command hook — there's no analog to Claude Code's `statusLine.command`. The statusline-written `.autocc/context.json` simply doesn't exist on Codex, so the reflector's 70%-context CHECKPOINT branch no-ops; the reflector still checkpoints on task completion, just not on a context-usage threshold.

See `docs/codex-mapping.md` §4 for the full gap list with one-line rationales.

## The statusline (yes, it's load-bearing)

`~/.claude/statusline-command.sh` is registered as Claude Code's `statusLine` command. Its primary side effect: it writes the full statusline JSON input to `<project_dir>/.autocc/context.json` every time it's called.

That JSON contains `context_window.used_percentage`. The reflector reads it during the CHECKPOINT step to decide whether to snapshot. Without this file, the 70% checkpoint trigger doesn't fire, and PostCompact recovery degrades to "resume blind."

(The statusline is also a normal statusline — shows user/host/cwd/git-branch/model/context% — but the side effect is what's actually critical for autocc.)

**Codex has no analog.** Codex's `status_line` TUI config is a widget list rendered by the TUI itself, not a shell-command hook — there's no equivalent to Claude Code's `statusLine.command`. Under Codex, `.autocc/context.json` is never written and the reflector's 70%-context CHECKPOINT branch no-ops; the reflector falls back to checkpointing on task completion. This is the **statusline shell-out** gap in `docs/codex-mapping.md` §4.

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

Skills are markdown files (with YAML frontmatter) loaded into the agent session — Claude Code via `~/.claude/skills/<name>/SKILL.md`, Codex via the plugin's `skills/<name>/SKILL.md` discovered through the marketplace entry. The payload is identical across providers; the skill bodies route around provider-specific env vars via the `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}` resolution chain (see [Provider branches](#provider-branches)). They describe the loop to the agent in natural language. There's no Python execution path through them — they're prompts.

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
    ├── context.json                — Claude only: written by statusline; read by reflector
    │                                 for checkpoint trigger. Codex has no analog.
    ├── tasks/<slug>.md             — briefings; one per TB-N
    ├── checkpoints/<ts>.md         — written by reflector at 70% context (Claude) or on task
    │                                 completion (Codex); read by PostCompact on Claude
    └── metrics/<ts>.json           — per-session summary written before idle stop
```

`flag` and `context.json` are runtime-only — gitignore them. `tasks/`, `progress.md`, `decisions.log`, and the metrics dir typically *are* committed; they're the audit trail.

The agent-side install layout differs by provider — see [Provider branches](#provider-branches) for the Codex plugin folder + marketplace-entry shape vs. the Claude `~/.claude/{skills,hooks}/` + `settings.json` shape.

## What's deliberately not here (v1)

- **No daemon.** Everything happens inside the agent session (Claude Code or Codex). The closest thing to a "background process" is the agent looping on itself, gated by the Stop hook.
- **No parallel workers.** v1 is single-threaded under both providers. Future versions may add an orchestrator pattern for dispatching tasks to background sessions.
- **No remote state.** All state is local to the project's `.autocc/` directory. No network, no auth, no central server.
- **No model-specific code.** autocc works with whatever model your Claude Code / Codex session is configured to use.
- **No generic provider plugin SDK.** Codex is the second concrete provider, not the start of an ecosystem — the two hook scripts are intentionally separate files rather than a shared module with a plugin interface (per `goal.md`'s non-goal).
- **No Codex-side polyfills for the `Elicitation` / `PostCompact` gaps.** These are accepted as documented limitations; see [Provider branches](#provider-branches) and `docs/codex-mapping.md` §4.
