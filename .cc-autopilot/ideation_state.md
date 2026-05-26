# Ideation State

_Last updated: 2026-05-18T18:15:18Z by ideation cron_

## Mission alignment
Project mission: "skills + hooks that let a Claude Code or Codex
session run unattended against TASKS.md." Four of five Done-when
bullets now have shipped code: TB-1 (Codex discovery doc), TB-2
(`--agent codex` installer branch), TB-3 (Codex hook script with
permissionDecision/stop wire shapes), TB-4 (portable skills via
`$AUTOCC_PROJECT_DIR` / `$AUTOCC_AGENT_NAME` fallback chains). All
four trace directly to focus item "OpenAI Codex provider support."
No drift. TB-5 (real-SDK Codex smoke) hit `retry_exhausted` but
attempt 1 already passed 5/6 bullets including the file-existence,
gate, and hook-evidence checks — the failure is verification-shape,
not implementation.

## Current focus assessment

- **OpenAI Codex provider support**
  - Progress so far: TB-2 added `--agent codex` installer branch
    (plugin folder at `${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/`
    + marketplace registration; 9 new installer tests). TB-3 added
    `src/autocc/hooks/autocc-hooks-codex.py` emitting Codex's
    `permissionDecision`/`stop` JSON shapes (24 subprocess tests
    covering all event paths + PLUGIN_ROOT/CLAUDE_PLUGIN_ROOT
    fallbacks). TB-4 parameterized `$CLAUDE_PROJECT_DIR` →
    `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`
    in `afk` + `reflector` and added `$AUTOCC_AGENT_NAME` /
    `$AUTOCC_AGENT_EMAIL` to `commit-changes` (11 portable-skill
    tests; docs/codex-mapping.md §3a documents the contract).
    TB-5 landed `tests/smoke/test_reflector_e2e_codex.py` at
    commit `e0d1b66` but is Frozen — see Gap (a).
  - Gaps:
    (a) TB-5 `## Verification` bullet
    `` `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py'` ``
    is non-auto-verifiable (matches the TB-122 pattern from CLAUDE.md
    failure-review section — daemon can't run a real `codex` CLI
    end-to-end, and the briefing's own `## Out of scope` says smokes
    are "operator-triggered by design (real $$ cost)"). Attempt 1
    passed bullet #1 (full suite, smoke skipped) and the four
    structural bullets; bullet #2 failed once, then two
    `error`-class retries on the same gate. Implementation is on
    disk per commit `e0d1b66`; the briefing needs the live-run
    bullet relocated to `## Out of scope`.
    (b) goal.md Done-when bullet #4 ("README and ARCHITECTURE
    document the Codex install path alongside Claude Code, with no
    broken anchors and no sections that silently assume Claude Code
    is the only provider") has no TB-N yet — README's `## Install`
    block names only `~/.claude/` + `autocc install`, and
    ARCHITECTURE's "The hook" section walks Claude Code's events
    table only. TB-5 briefing explicitly punts the README walkthrough.
    (c) TB-4 hard-coded `AUTOCC_AGENT_NAME:-Claude` /
    `AUTOCC_AGENT_EMAIL:-noreply@anthropic.com` defaults in
    `skills/commit-changes/SKILL.md`. Under `--agent codex` the
    natural default trailer identity is `Codex`, still overridable
    via env var — small but user-visible on every Codex-created
    commit.
  - Status: `in-progress`
  - Reasoning: focus item is on track; remaining work is one
    fix-briefing (unblocks TB-5), one deferred README/ARCHITECTURE
    pass (Done-when #4), and one UX polish that lands the
    provider-aware default already implied by `--agent codex`.

## Non-goal risk check
None. All three proposals stay inside the focus item; no
parallel-worker work, no PyPI, no remote state, no generic provider
SDK. Proposal #3 keeps the existing env-var-override pattern from
TB-4 (no new abstraction); proposal #2 is documentation only.

## Considered & deferred this cycle
- **Elicitation / PostCompact polyfill MCP servers**: prior cycle
  deferred until smoke surfaces real gaps; smoke is still
  operator-pending after TB-5 unfreezes. Defer.
- **externalAgentConfig JSON-RPC verification**: flagged in TB-5's
  `## Out of scope` as separate task; punt until either smoke
  output or installer needs surface a concrete failure.
- **Shared smoke-runner helper extraction across providers**:
  explicit dup-now-refactor-later per goal.md Non-goals (no generic
  provider SDK before two providers actually work). Defer until
  both smokes have stabilized.
- **CI workflow for the Codex smoke**: TB-5 `## Out of scope`
  lists this — smokes stay operator-triggered (real $ cost). Defer.
- **`statusline` document-and-skip note in ARCHITECTURE**: fold
  into the README/ARCHITECTURE pass (proposal #2) rather than
  standalone.

## Cycle observations
- Prior cycle's three follow-ups (installer / hook script / skill
  glue) all shipped within ~12 minutes of operator approval; the
  follow-up chain pattern is working. Carrying only the TB-5
  failure-shape observation forward as it directly informs this
  cycle's `#fix-briefing` proposal.
- TB-5 attempt-1 logged a clean `verification_failed` (5/6 bullets
  pass) but attempts 2 and 3 logged `error` (exit 1) with empty
  `stderr_tail`. The TB-5 implementation is on disk per
  `git_log_grep` (commit `e0d1b66`); the empty-stderr error class
  may warrant a separate look if it recurs in another task's
  retries — carry-and-watch.

## Decisions needed from operator
- Decision needed: after the proposed TB-6 `#fix-briefing` lands,
  run `ap2 unfreeze TB-5` to re-attempt the Codex real-SDK smoke
  task. Unblock-condition: with the live-`codex` invocation
  relocated from `## Verification` to `## Out of scope`, the
  daemon's per-task verifier can pass the remaining auto-verifiable
  bullets and TB-5 promotes through to Complete; the actual
  real-SDK smoke run stays operator-triggered as designed.

## Proposals this cycle
- TB-6: `#fix-briefing` — strip the live-`codex` `AUTOCC_REAL_SDK=1`
  invocation from TB-5's `## Verification`, document it in
  `## Out of scope` as the operator's manual smoke trigger
  (closes Gap a).
- TB-7: README + ARCHITECTURE Codex install walkthrough
  (closes Gap b / Done-when bullet #4).
- TB-8: Provider-aware default for `AUTOCC_AGENT_NAME` /
  `AUTOCC_AGENT_EMAIL` in `commit-changes` (closes Gap c).
