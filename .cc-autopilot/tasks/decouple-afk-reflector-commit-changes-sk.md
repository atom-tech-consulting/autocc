
# Decouple afk / reflector / commit-changes skills from Claude-only assumptions

Tags: #codex #skills

## Goal

Current focus: OpenAI Codex provider support. Done-when bullet
#3 — "The taskboard, reflector, housekeeping, and
commit-changes skills are portable: the same `TASKS.md`
protocol and briefing contract drive the loop under both
Claude Code and Codex" — fails today because three skills
carry Claude-only assumptions documented in the discovery
table (`docs/codex-mapping.md` §3):

  - `skills/afk/SKILL.md` and `skills/reflector/SKILL.md`
    read `$CLAUDE_PROJECT_DIR` directly to locate the
    project root. Codex does not set this variable; under
    Codex the skills resolve to an empty path and fail to
    find `.autocc/flag` or `CLAUDE.md`'s `## Autopilot`
    section.
  - `skills/commit-changes/SKILL.md` hard-codes the trailer
    `Co-Authored-By: Claude <noreply@anthropic.com>` in its
    commit-message guidance, which mis-attributes commits
    authored under Codex.

This task introduces a provider-neutral resolution chain
(`${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`,
or equivalent), parameterizes the commit trailer, and adds
unit coverage that pins the new behavior under both providers'
env shapes. Skills the discovery table classifies as
portable-as-is (`taskboard`, `tb`, `housekeeping`) are
explicitly out of scope.

Why now: even after the installer copies the six skill
markdowns into `~/plugins/autocc/skills/` (the corrected
home-rooted plugin path per `docs/codex-mapping.md` §1a — NOT
`~/.codex/plugins/`, which the original discovery doc wrongly
recommended), a Codex session loading them still cannot find
the autopilot flag or the task board because the skill bodies
read the wrong env var — the install path will appear to
succeed and then the loop will fail on the first turn.
Decoupling the env-var contract is the last piece needed for
an end-to-end Codex autopilot run.

## Scope

- `skills/afk/SKILL.md` — replace `$CLAUDE_PROJECT_DIR`
  with the resolution chain
  `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`.
  Update the inline shell snippet wherever it appears and
  add one sentence noting the fallback order.
- `skills/reflector/SKILL.md` — same env-var change. The
  skill body cites the variable in multiple places; replace
  all occurrences. Do NOT yet change the 70%-context
  CHECKPOINT branch; the discovery doc flags that as a
  separate polyfill decision and a later task will handle
  it.
- `skills/commit-changes/SKILL.md` — parameterize the
  trailer. The new contract:
  `Co-Authored-By: ${AUTOCC_AGENT_NAME:-Claude} <${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}>`.
  The installer's Codex branch (now landed) sets those env
  vars to `Codex` / `noreply@openai.com` via the
  `~/plugins/autocc/hooks.json` `env` block (the corrected
  home-rooted plugin path) or the skill's preamble — pick
  whichever surface the skill loader honors and document
  the choice in the skill body.
- `tests/test_autocc_hook.py` (or a new
  `tests/test_skills_portable.py`) — add tests that grep the
  three skill files to assert:
    - no remaining bare `$CLAUDE_PROJECT_DIR` reference
      without the fallback chain
    - the `commit-changes` body references both
      `AUTOCC_AGENT_NAME` and `AUTOCC_AGENT_EMAIL`
    - the literal trailer `Co-Authored-By: Claude
      <noreply@anthropic.com>` no longer appears as a
      hard-coded line outside the fallback default
- Document the new env vars in a short "Provider-portable
  skills" subsection of `docs/codex-mapping.md` so the
  contract is preserved alongside the discovery output.

## Design

The fallback chain — `AUTOCC_*` first, then each provider's
native var, then `$PWD` — keeps the skill bodies
provider-neutral without requiring a runtime check. The
preferred env-var names use the `AUTOCC_` prefix so a future
third provider can opt in by setting `AUTOCC_PROJECT_DIR`
explicitly without any skill edit. The trailer default
remains `Claude / noreply@anthropic.com` to preserve current
Claude-side behavior; the installer's Codex branch overrides
it via the env-var contract.

## Verification

- `uv run pytest -q` — full suite passes (regression gate).
- `bash -c '! grep -RnE "\$CLAUDE_PROJECT_DIR(?![A-Za-z_])" skills/afk skills/reflector | grep -v AUTOCC_PROJECT_DIR'`
  — no bare `$CLAUDE_PROJECT_DIR` reference remains in the
  two affected skill files outside the fallback chain.
- `grep -q "AUTOCC_PROJECT_DIR" skills/afk/SKILL.md` — afk
  skill cites the new portable env var.
- `grep -q "AUTOCC_PROJECT_DIR" skills/reflector/SKILL.md`
  — reflector skill cites the new portable env var.
- `grep -q "AUTOCC_AGENT_NAME" skills/commit-changes/SKILL.md`
  — commit-changes skill parameterizes the trailer name.
- `grep -q "AUTOCC_AGENT_EMAIL" skills/commit-changes/SKILL.md`
  — commit-changes skill parameterizes the trailer email.
- Prose: `docs/codex-mapping.md` includes a new subsection
  documenting the `AUTOCC_PROJECT_DIR` / `AUTOCC_AGENT_NAME`
  / `AUTOCC_AGENT_EMAIL` env-var contract (judge confirms
  via Read).

## Out of scope

- Touching the `taskboard`, `tb`, or `housekeeping` skills
  — the discovery table classifies all three as
  portable-as-is, and changing them risks Claude-side
  regression with no Codex-side benefit.
- Replacing the reflector's 70%-context CHECKPOINT trigger
  — that's the statusline polyfill decision flagged in the
  discovery doc's gap list; defer.
- Polyfilling Elicitation / PostCompact (separate
  follow-ups).
- Updating README / ARCHITECTURE — hold until installer +
  hook script + skill decoupling all land and can be
  documented together.
