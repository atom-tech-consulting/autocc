# Project Goals

## Mission

A small collection of skills + hooks that let a coding-agent CLI session
(Claude Code or OpenAI Codex) run unattended against a `TASKS.md` task
board — no daemon, no new model, everything inside a normal agent
session.

## Done when

- `autocc install --agent codex` wires the Codex-side equivalents of
  hooks + skills into the canonical Codex plugin layout (per
  `plugin-creator/SKILL.md`: a plugin folder under `~/plugins/<name>/`
  registered via a marketplace entry at
  `~/.agents/plugins/marketplace.json`) so an unattended run works
  end-to-end with no manual fix-up
- A first-time Codex user can run `pipx install git+...` →
  `autocc install --agent codex` → initialize the task board → start
  the unattended loop, and watch the reflector walk the board to
  completion
- The taskboard, reflector, housekeeping, and commit-changes skills are
  portable: the same `TASKS.md` protocol and briefing contract drive
  the loop under both Claude Code and Codex
- README and ARCHITECTURE document the Codex install path alongside
  Claude Code, with no broken anchors and no sections that silently
  assume Claude Code is the only provider
- Unit suite covers both providers' installer + hook paths; the opt-in
  real-SDK smoke test runs cleanly against `examples/taskflow` under
  Codex as well as Claude Code

## Current focus: OpenAI Codex provider support

The v0.1.0 design assumed one provider (Claude Code) — the hook script,
the installer's settings-file patching, and several skill prompts all
hard-code Claude Code's extension surface. The next milestone is
adapting that surface so a Codex session can run the same reflector
loop against the same task board.

Concretely this means: identify Codex's actual extension points for the
behaviors autocc relies on (suppressing interactive prompts, auto-
approving permissions, blocking premature stop, surviving auto-
compaction); add a Codex branch to the installer that targets Codex's
config directory instead of `~/.claude/`; and split provider-specific
glue out of skills that today reference Claude-Code-only concepts.
Where Codex has no analog for a Claude Code feature, document the gap
rather than building a polyfill.

Bias toward the smallest abstraction that supports two concrete
providers. Resist building a generic provider plugin system before the
second provider is actually working.

## Non-goals

- **Parallel workers**: dispatching tasks to background sessions via
  any provider's agent SDK is still deferred. The single-session loop
  is the v1 promise under both providers.
- **Custom permission gating beyond each provider's built-in auto
  mode**: autocc auto-approves when the flag is set, the provider's
  classifier and OS-level sandboxing are the safety net. Don't build
  a separate permission classifier.
- **A standalone `/ideation` skill**: still out of the core loop.
- **PyPI distribution**: install-from-source only, both providers.
- **Remote state or central server**: all state stays local to the
  project's `.autocc/` directory regardless of provider.
- **Generic provider plugin SDK**: Codex is the second concrete
  provider, not the start of an ecosystem. Don't design extension
  hooks for hypothetical providers three and four.
- **Cross-provider parity feature-for-feature**: if a Claude-Code-only
  capability has no Codex analog, document the gap in ARCHITECTURE
  and move on — Codex-side polyfills are out of scope.

## Constraints

- **Python 3.9+** (per `pyproject.toml` `requires-python`), unchanged
  by adding Codex support.
- **No runtime dependencies**: the installer and both providers'
  hook scripts stay stdlib-only.
- **Skills are markdown prompts** loaded by the agent, not executable
  code. Codex must load them the same way for the loop to be portable.
- **Safety**: when `.autocc/flag` is set, autocc auto-approves every
  permission request unconditionally — under both providers.
  Mitigation is OS-level sandboxing (separate user, container, or VM)
  plus the provider's built-in classifier. Documented prominently in
  README + ARCHITECTURE for each provider's install path.
