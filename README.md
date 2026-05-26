# autocc — autopilot for Claude Code & Codex

Run a Claude Code or OpenAI Codex session unattended against a task board.

`autocc` is a small collection of **skills** and **hooks** that target two coding-agent CLIs — Claude Code (default) and OpenAI Codex (via `--agent codex`). Together they let you say "work on the task board until you run out of tasks," walk away, and come back to a stack of commits with an audit trail.

It's intentionally tiny:

- One Python hook per provider (`autocc-hooks.py` for Claude Code; `autocc-hooks-codex.py` for Codex) that gates on a flag file
- One shell statusline script (Claude Code only — see [ARCHITECTURE.md](ARCHITECTURE.md#the-statusline-yes-its-load-bearing) for why)
- Six skills (`/afk`, `/reflector`, `/taskboard` + `/tb`, `/housekeeping`, `/commit-changes`) — same payload under both providers
- A `TASKS.md` task-board format

No daemon. No background process. No new model. Everything happens inside your normal agent session — the hook just suppresses interactive prompts and the skills define the work loop.

## Install

autocc is install-from-source — there's no PyPI release. Install with `pipx` (or `uv tool`) directly from the git repo:

```bash
pipx install git+https://github.com/atom-tech-consulting/autocc.git
## or:
uv tool install git+https://github.com/atom-tech-consulting/autocc.git
```

Or clone and install editable for hacking:

```bash
git clone https://github.com/atom-tech-consulting/autocc.git
cd autocc && uv venv && uv pip install -e .
```

Then wire it into your agent of choice. `--agent {claude,codex}` is the only branch point; everything else (status, uninstall, the diff preview, `-y`, `--dry-run`) is identical between the two providers.

### Claude Code (default)

```bash
autocc install            # rsync skills, copy hooks, patch ~/.claude/settings.json
```

`autocc install` (== `autocc install --agent claude`) shows you a unified diff of the proposed `~/.claude/settings.json` change before applying it. Pass `-y` to skip the prompt, or `--dry-run` to preview without writing.

What lands on disk: skills under `~/.claude/skills/<name>/`, hook script at `~/.claude/hooks/autocc-hooks.py`, statusline at `~/.claude/statusline-command.sh`, plus autocc-managed `hooks` / `statusLine` entries patched into `~/.claude/settings.json`.

### OpenAI Codex

```bash
autocc install --agent codex
```

Codex discovers plugins via marketplaces rather than by scanning a single config dir, so the Codex branch installs as a self-contained **plugin folder** plus a single **marketplace entry**:

```
${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/
├── .codex-plugin/plugin.json        # plugin manifest (name, version, skills, hooks)
├── skills/<name>/SKILL.md           # same skill payload as the Claude install
├── hooks.json                       # registers PreToolUse / PermissionRequest / Stop
└── hooks/autocc-hooks-codex.py      # Codex-shaped autopilot hook (emits Codex's
                                     # permissionDecision / stop JSON shapes)

~/.agents/plugins/marketplace.json   # one `plugins[]` entry pointing at the folder
                                     # via source.path: ./plugins/autocc
```

Override `AUTOCC_CODEX_PLUGIN_ROOT` if you want the plugin folder somewhere other than `~/plugins/`. Codex resolves the marketplace's `source.path: ./plugins/autocc` against the marketplace's home anchor, so `~/.agents/plugins/marketplace.json` → `~/plugins/autocc/` (per `plugin-creator/SKILL.md`'s convention).

`autocc install --agent codex` shows a unified diff of the marketplace.json change before writing; `-y` / `--dry-run` work identically to the Claude branch.

### Shared

```bash
autocc status             # show what's installed (auto-detects agent layout)
autocc uninstall          # reverse install (use --agent codex to target the Codex install)
```

## Quickstart

In any project:

```bash
## 1. Initialize the task board (creates TASKS.md + adds the Autopilot section to CLAUDE.md)
claude   # or: codex
         # then in the session: /taskboard init

## 2. Add a task or two
##    (Edit TASKS.md by hand, or describe them to the agent in the session.)

## 3. Go AFK
/afk
```

`/afk` creates `.autocc/flag`, then invokes `/reflector`. The reflector loop reads the next task off the board, executes it, commits locally, and moves on. The hook file ensures the agent doesn't stop to ask you questions while you're gone — questions are auto-suppressed with "decide yourself, document your reasoning in `.autocc/decisions.log`."

When you come back, send any message — say "back" or "stop" to end the loop.

### Try it on a known-good fixture

If you want to see a complete reflector run before pointing autocc at your own code, [`examples/taskflow`](examples/taskflow) is a small Python project with three workable tasks (one bug, one missing feature, one missing tests) and a populated task board. See [its README](examples/taskflow/README.md) for the walkthrough.

## What you get on disk

After `/taskboard init` and a reflector session, the per-project layout is identical between providers:

```
your-project/
├── CLAUDE.md                       # ## Autopilot section added
├── TASKS.md                        # the 5-section board
└── .autocc/
    ├── flag                        # presence = autopilot on (created by /afk)
    ├── decisions.log               # suppressed-prompt audit trail
    ├── progress.md                 # narrative log of every task
    ├── context.json                # context-window snapshot (Claude only; written by statusline)
    ├── tasks/                      # per-TB-N briefing markdown
    ├── checkpoints/                # snapshots written at 70% context (used by PostCompact)
    └── metrics/                    # per-session JSON
```

The **agent-side** install differs by provider — Claude patches `~/.claude/settings.json` and drops files under `~/.claude/skills/` + `~/.claude/hooks/`; Codex lands a plugin folder under `${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/` and registers it in `~/.agents/plugins/marketplace.json` (see [Install](#install) above for the exact layout). `context.json` and the 70%-context checkpoint trigger are Claude-only — Codex has no `statusLine.command` shell-out, so on Codex the reflector's checkpoint logic degrades gracefully (see [ARCHITECTURE.md](ARCHITECTURE.md#provider-branches) and [`docs/codex-mapping.md`](docs/codex-mapping.md) for the gap list).

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

Under Codex, the hook script is `autocc-hooks-codex.py` (installed into the plugin folder rather than `~/.claude/hooks/`); it implements the same PreToolUse / PermissionRequest / Stop semantics using Codex's `permissionDecision` JSON shape. The `Elicitation` and `PostCompact` events have no Codex analog and are tracked as documented gaps — see [ARCHITECTURE.md](ARCHITECTURE.md#provider-branches) and [`docs/codex-mapping.md`](docs/codex-mapping.md).

The flag file is the kill switch: delete `.autocc/flag` and the hook returns to no-op mode immediately, on either provider.

## The task board (`TASKS.md`)

Under a `# Tasks` top-level heading, five sections in order:

```markdown
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

**When `.autocc/flag` is set, autocc auto-approves every `PermissionRequest` unconditionally — under both Claude Code and Codex.** This is by design — autonomous operation can't pause on every interactive prompt — but it means the agent has the full authority of your Claude Code / Codex tool surface for the duration of the run. You should understand and bound that authority before pointing autocc at anything important:

1. **(a) autocc approves all permission requests by design.** The hook doesn't inspect tool name or arguments; every `PermissionRequest` returns the provider's auto-allow shape (`{"behavior": "allow"}` on Claude Code; `{"permissionDecision": "allow"}` on Codex). This is what allows the loop to make progress without you.

2. **(b) Strongly recommended: turn on the provider's built-in auto mode.** Both providers ship a classifier-backed auto mode (Claude Code's auto mode; Codex's `-a/--ask-for-approval=never` startup flag pairs with its own classifier). Auto mode handles permission auto-approval natively and applies the provider's own classifier before allowing tool calls. When auto mode is on, autocc's `PermissionRequest` hook becomes a no-op (no prompt to short-circuit — auto mode already passed it through), so the classifier is what's actually gating the agent. This is meaningfully safer than autocc's blanket allow.

3. **(c) Preferred: run autopilot sessions in a system-level sandbox.** Both providers' tool surfaces include shell access to your home directory, so the blast radius is whatever the *invoking OS user* can touch. For unattended runs, the most robust safety measure is to isolate that radius at the OS level — a separate macOS / Linux user with restricted privileges, a container, or a VM. The agent's authority then can't escape the sandbox even if a prompt-injection or skill-regression slips a destructive action past everything else. The OS-level sandbox recommendation is identical for Claude Code and Codex; see [ARCHITECTURE.md's permission-model callout](ARCHITECTURE.md#-permission-model--unconditional-auto-approval).

`permissions.deny` rules in `~/.claude/settings.json` still apply under autopilot on Claude Code — they're enforced by Claude Code before the hook runs. Use them to hard-block specific patterns (e.g., `Bash(rm -rf *)`, `Bash(git push --force*)`) regardless of which mode you're in. Codex's equivalent is its sandbox / approval-policy config in `~/.codex/config.toml`; the same blanket auto-allow caveat applies, so OS-level sandboxing (option (c) above) is the recommended hard backstop on both providers.

### What autocc still does on top of auto mode

Auto mode covers permission auto-approval. autocc on top of that adds:

- **Suppresses `AskUserQuestion`** (Claude Code) — auto mode doesn't answer agent questions, just permissions. The hook denies these with "decide yourself, log to `.autocc/decisions.log`." Codex has no `AskUserQuestion` tool; the matcher is registered but never fires, and the skill prompt enforces the "don't ask" constraint instead.
- **Suppresses `EnterPlanMode` and Elicitation** (Claude Code) — same reasoning. Neither has a Codex analog; see [ARCHITECTURE.md](ARCHITECTURE.md#provider-branches) and [`docs/codex-mapping.md`](docs/codex-mapping.md) for the gap list.
- **Blocks Stop** — keeps the agent on the loop until the task board is exhausted, instead of letting it idle out. Implemented on both providers via their respective `Stop` hook events.
- **Survives auto-compaction** (Claude Code) — `PostCompact` re-injects the latest checkpoint so the reflector loop continues seamlessly in the new context. Codex has no `PostCompact` hook; the reflector's per-task checkpoint pass partially compensates.
- **Provides the task-board loop itself** — `/reflector`, `/taskboard`, `/housekeeping`, briefings, progress.md. Identical under both providers.

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

- `AUTOCC_PROJECT_DIR` — portable session-root override read by the `afk` / `reflector` skills. Resolution chain is `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`, so you only set this to pin a non-default project root regardless of which agent harness is running. Skill behavior is identical under Claude and Codex.
- `CLAUDE_PROJECT_DIR` — set by Claude Code, used by the hook to find the right `.autocc/flag` regardless of which subdirectory the agent is currently in. You don't set this.
- `CODEX_PROJECT_DIR` — Codex's analog of `CLAUDE_PROJECT_DIR`. The Codex install's `hooks.json` can set it explicitly if Codex doesn't export it natively in your environment.
- `CLAUDE_HOME` — override `~/.claude` for testing (used by `autocc install`, Claude branch).
- `AUTOCC_CODEX_PLUGIN_ROOT` — override the parent directory for the Codex plugin folder (default `~/plugins`, so the plugin lands at `~/plugins/autocc/`). Used by `autocc install --agent codex`.
- `AUTOCC_AGENT_NAME` / `AUTOCC_AGENT_EMAIL` — parameterize the `Co-Authored-By` trailer that the `commit-changes` skill writes. Defaults `Claude` / `noreply@anthropic.com`; the Codex install's `hooks.json` overrides them to `Codex` / `noreply@openai.com` so commits made under Codex are attributed correctly.

## Uninstall

```bash
autocc uninstall                  # Claude branch (default)
autocc uninstall --agent codex    # Codex branch
```

Claude branch: removes the six skill directories from `~/.claude/skills/`, deletes the hook + statusline scripts, and strips autocc-managed entries from `~/.claude/settings.json` (leaving any other hook entries you have intact).

Codex branch: removes the plugin folder at `${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/` and strips the autocc entry from `~/.agents/plugins/marketplace.json` (preserving other plugins' entries).

Per-project state in `.autocc/` is left in place under both branches — delete the directory yourself if you don't want it.

## Roadmap

Things considered but **not in v1**:

- **Parallel workers** — dispatching tasks to background sessions via either provider's agent SDK. Likely a follow-up release.
- **Permission gating** — explicitly *not* shipped. Both providers' built-in auto modes handle permission auto-approval natively, so a custom PreToolUse Bash filter is largely unnecessary. See ["Safety model"](#safety-model) above.
- **`/ideation`** — a manual task-proposal skill. Standalone, didn't make the core loop cut.

## Tests

Two tiers:

```bash
## Unit tier — fast, no API cost. Runs by default.
pytest                                  # installer + hook unit suite (covers BOTH providers'
                                        # installer + hook paths)

## Smoke tier — real CLI against examples/taskflow. ~$2-4 per run on Opus.
## AUTOCC_REAL_SDK=1 runs BOTH the Claude smoke (real `claude` CLI) and the
## Codex smoke (real `codex` CLI; requires `codex login` completed).
AUTOCC_REAL_SDK=1 uv run pytest -q      # end-to-end reflector tests (Claude + Codex)
```

- `AUTOCC_REAL_SDK=1 uv run pytest -q` exercises both `tests/smoke/test_reflector_e2e.py` (Claude smoke, requires `claude` CLI logged in) and `tests/smoke/test_reflector_e2e_codex.py` (Codex smoke, requires `codex login` completed). Either smoke is auto-skipped if the corresponding CLI isn't on `$PATH` / isn't authenticated.

See [`tests/smoke/README.md`](tests/smoke/README.md) for what the smokes verify and how they're gated.

## License

MIT — see [LICENSE](LICENSE).
