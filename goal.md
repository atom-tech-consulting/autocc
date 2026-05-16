# Project Goals

## Mission
A small collection of skills + hooks that let a Claude Code session run
unattended against a `TASKS.md` task board — no daemon, no new model,
everything inside a normal Claude Code session.

## Done when
- v0.1.0 is published as an install-from-source git repo at
  github.com/atom-tech-consulting/autocc, installable via
  `pipx install git+...`
- README and ARCHITECTURE accurately reflect installed behavior, with
  no broken anchors or stale test/file counts
- Unit suite (installer + hook) is green; opt-in real-SDK smoke runs
  cleanly against `examples/taskflow`
- A first-time user can run `pipx install git+...` → `autocc install`
  → `/taskboard init` → `/afk` end-to-end without manual fix-up

## Current focus
- Pre-release polish before the first public push of autocc v0.1.0

## Non-goals
- Parallel workers (dispatching tasks to background sessions via the
  Agent SDK) — deferred
- Custom permission gating beyond what Claude Code's built-in auto
  mode already provides
- A standalone `/ideation` skill
- PyPI distribution — install-from-source only
- Remote state, network calls, or any central server — autocc is
  entirely local to the project's `.autocc/` directory

## Constraints
- Python 3.9+ (per pyproject.toml `requires-python`)
- No runtime dependencies — installer + hook are stdlib-only
- Skills are markdown prompts loaded into the Claude Code session,
  not executable code
- Safety: when `.autocc/flag` is set, the hook auto-approves every
  `PermissionRequest` unconditionally. Mitigation is OS-level
  sandboxing (separate user, container, or VM) plus Claude Code's
  built-in auto mode classifier. Documented prominently in README +
  ARCHITECTURE.
