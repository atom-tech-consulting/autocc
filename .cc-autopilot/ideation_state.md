# Ideation State

_Last updated: 2026-05-17T08:04:00Z by ideation cron_

## Mission alignment
Project mission is "skills + hooks that let a Claude Code or Codex
session run unattended against TASKS.md." Current focus is OpenAI
Codex provider support. Only one Complete exists so far: TB-1 (Map
Codex extension points to autocc hook + skill requirements). That
deliverable — `docs/codex-mapping.md` pinned to codex-cli 0.128.0
— is squarely on mission: it identifies `~/.codex/config.toml`
`[hooks]` + `~/.codex/plugins/<name>/` as the installer targets,
classifies all six skills (3 portable-as-is, 3 need glue), and
lists 5 Claude-only behaviors with disposition (Elicitation +
PostCompact = polyfill candidate; AskUserQuestion + EnterPlanMode
= accept-as-limitation; statusline = document-and-skip). No
drift; the deliverable directly de-risks the install-path Done-when
bullet.

## Current focus assessment

- **OpenAI Codex provider support**
  - Progress so far: TB-1 produced the discovery doc
    `docs/codex-mapping.md` naming `~/.codex/config.toml`
    `[hooks]` + `~/.codex/plugins/` as install targets, mapping
    all six autocc hook events + six skills to Codex 0.128.0
    equivalents, with a 5-item gap list (commit `98ccd89`).
  - Gaps: (a) installer still has no `--agent codex` branch —
    `src/autocc/cli.py` exposes only `install` with no agent
    flag; `src/autocc/installer.py` hard-codes `~/.claude/` and
    the Claude `settings.json` hook shape; (b) hook script
    `src/autocc/hooks/autocc-hooks.py` emits the Claude JSON wire
    format (`hookSpecificOutput.decision.behavior: allow`) which
    Codex rejects — Codex expects `permissionDecision: allow`
    (TB-1 mapping §2a row 3); (c) three skills carry Claude-only
    assumptions per TB-1 mapping §3: `afk` + `reflector` read
    `$CLAUDE_PROJECT_DIR`, `commit-changes` hard-codes
    `Co-Authored-By: Claude <noreply@anthropic.com>` trailer.
  - Status: `in-progress`
  - Reasoning: TB-1 was the discovery slot; three concrete
    follow-up implementation slots are now unblocked and
    well-scoped.

## Non-goal risk check
None. The follow-up proposals are tightly scoped to a single
second provider (Codex) — no plugin SDK, no parallel-worker
infrastructure, no PyPI work, no remote state. The plugin-shape
install lands one directory under `~/.codex/plugins/autocc/`
and stays local.

## Considered & deferred this cycle
- **Elicitation polyfill MCP server**: TB-1 mapping §4 flags
  this as polyfill candidate, but it depends on the installer
  branch landing first (the MCP server has to be registered via
  the installer). Defer until the installer + hook script tasks
  ship.
- **PostCompact polyfill via user_prompt_submit hook**: same
  ordering constraint — needs the codex hook script in place
  first. Defer.
- **ARCHITECTURE.md + README Codex section** (Done-when bullet
  #4): premature to document an install path that doesn't run
  yet; revisit after the installer branch ships.
- **Codex smoke test under `tests/smoke/`** (Done-when bullet
  #5): blocked on real installer/hook artifacts; revisit after
  the three proposed tasks land.
- **`statusline` document-and-skip note**: trivial doc edit;
  fold into the README/ARCHITECTURE pass rather than spending
  a slot on it standalone.

## Cycle observations
- First post-TB-1 ideation. Prior cycle's state file was a
  placeholder (no real bullets to triage). Establishing the
  follow-up chain (installer → hook script → skill glue) here
  to anchor next cycle's "Considered & deferred" carryover.
- `validator_judge_timeout` at 06:32:04Z (1 in 24h per
  `ap2 status`) — single occurrence, not a pattern; carry only
  if it repeats next cycle.
- `ideation_error` at 06:03:46Z lost stderr (empty
  `stderr_tail`). Worth noting once for next cycle's triage
  signal in case it recurs; do not propose remediation yet.

## Decisions needed from operator
(none this cycle — the operator-review gate on each proposal
is the natural decision surface, and no `cron_proposed` events
are unadopted)

## Proposals this cycle
- TB-2: Add `--agent codex` install branch (closes focus gap a)
- TB-3: Codex-side hook script with Codex JSON wire shapes
  (closes focus gap b)
- TB-4: De-Claude the three skills with provider-specific glue
  (closes focus gap c)
