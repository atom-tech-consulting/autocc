## Goal

Current focus: OpenAI Codex provider support. goal.md Done-when
bullet #4 reads verbatim:

> README and ARCHITECTURE document the Codex install path alongside
> Claude Code, with no broken anchors and no sections that silently
> assume Claude Code is the only provider

Today README.md's `## Install` section names only
`autocc install` against `~/.claude/`, and ARCHITECTURE.md's
"The hook" section walks a Claude-Code-only events table
(PreToolUse / PermissionRequest / Stop / Elicitation / PostCompact)
without acknowledging that the `--agent codex` install branch on
disk has a different hook script, install target, and
document-and-skip story. This task closes that documentation gap
so a first-time Codex user can find an entry point.

Why now: The Codex install path runs end-to-end against synthetic
fixtures today (the installer's `--agent codex` flag, the
`autocc-hooks-codex.py` script, and the env-var-fallback skill
glue are all already on disk and covered by passing unit tests),
but a Codex user reading README.md still sees only the
Claude-Code instructions. Without this docs pass, even an
operator who fully understands the implementation has no
linkable docs to point a new Codex user at, and the "first-time
Codex user can pipx install → autocc install → start the loop"
Done-when bullet #2 has no documented entry point. Shipping
the docs alongside the implementation prevents the standard
"code shipped, README stale" drift while it's cheap to fix.

## Scope

- README.md:
  - In `## Install`, document `autocc install --agent codex`
    alongside the existing `autocc install` invocation. Show
    the resulting on-disk layout
    (`${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/.codex-plugin/plugin.json`
    + a marketplace entry at `~/.agents/plugins/marketplace.json`)
    and note that `--agent {claude,codex}` is the only branch
    point.
  - In the "What you get on disk" / Quickstart sections, note
    that the Codex install lands a plugin folder under
    `~/plugins/autocc/` rather than patching
    `~/.claude/settings.json`, so first-time Codex users know
    where to look.
  - Brief safety note: the auto-approve policy under
    `.autocc/flag` applies to both providers; OS-level
    sandboxing recommendation remains identical (point at the
    existing ARCHITECTURE permission-model callout).
  - One bullet under `## Tests` noting that
    `AUTOCC_REAL_SDK=1 uv run pytest -q` now exercises both
    Claude (`test_reflector_e2e.py`) and Codex
    (`test_reflector_e2e_codex.py`) smokes when the respective
    CLIs are logged in.
- ARCHITECTURE.md:
  - In "The hook" section (or a new "Provider branches"
    subsection), document that `autocc-hooks-codex.py` is the
    Codex-side equivalent of `autocc-hooks.py`, emitting
    Codex's `permissionDecision` / `stop` JSON shapes instead
    of Claude Code's `hookSpecificOutput.decision.behavior`
    shape. Cite `docs/codex-mapping.md` for the full
    event-by-event mapping rather than duplicating it inline.
  - Document the Codex install layout
    (`${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/.codex-plugin/plugin.json`
    + marketplace registration at
    `~/.agents/plugins/marketplace.json`) as a peer of the
    Claude `~/.claude/settings.json` patch.
  - Document the
    `${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}}`
    fallback chain that the `afk` / `reflector` skills now
    use, plus the `${AUTOCC_AGENT_NAME:-Claude}` /
    `${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}` trailer
    parameterization in `commit-changes`.
  - Document the document-and-skip gaps (`statusline` skipped
    under Codex; Elicitation + PostCompact accept-as-limitation
    pending polyfills), citing `docs/codex-mapping.md`.
- Do NOT rewrite either file end-to-end — this is a targeted
  additive pass. Existing Claude-Code sections stay correct;
  the goal is to make Codex coverage a peer, not to refactor
  the documentation structure.

## Design

Additive edits only. Keep existing anchor IDs stable (no
section rename that would break a deep link). Where a sentence
currently says "Claude Code" without qualification but the
statement is now provider-agnostic, soften to "the agent" or
"Claude Code / Codex" — but don't bulk-rewrite; only adjust
sentences that would mislead a Codex reader.

Cite `docs/codex-mapping.md` for wire-shape and gap-list
detail rather than duplicating it inline (keeps README short;
keeps `docs/codex-mapping.md` as the single source of truth on
provider-equivalence details).

## Verification

- `grep -q "autocc install --agent codex" README.md` — README documents the Codex installer branch.
- `grep -qE "AUTOCC_CODEX_PLUGIN_ROOT|~/plugins/autocc" README.md` — README documents the Codex install layout.
- `grep -q "autocc-hooks-codex" ARCHITECTURE.md` — ARCHITECTURE names the Codex-side hook script.
- `grep -qE "permissionDecision|codex-mapping" ARCHITECTURE.md` — ARCHITECTURE either names the Codex wire shape or cites the mapping doc.
- `grep -qE "AUTOCC_PROJECT_DIR|AUTOCC_AGENT_NAME" ARCHITECTURE.md` — ARCHITECTURE documents the env-var fallback chain.
- `awk '/^# /{n++} END{exit !(n==1)}' README.md` — README still has exactly one top-level heading (sanity check the edit didn't split or duplicate the title).
- `awk '/^# /{n++} END{exit !(n==1)}' ARCHITECTURE.md` — ARCHITECTURE still has exactly one top-level heading.
- `uv run pytest -q` — full pytest suite still passes (regression gate; docs-only edit shouldn't touch any test).
- Prose: README.md and ARCHITECTURE.md include no section that says "only Claude Code" or equivalent language that contradicts the documented `--agent codex` install path; judge confirms by reading both files end-to-end.

## Out of scope

- Adding a Codex quickstart screenshot or asciicast — text-only docs pass.
- Rewriting `docs/codex-mapping.md` — it is already the source of truth; this task cites it, doesn't replace it.
- Adding a new top-level docs file (e.g. `docs/codex-quickstart.md`) — keep the docs surface flat; README + ARCHITECTURE cover both providers per Done-when bullet #4.
- Editing the briefings of prior Codex tasks to add cross-references.
- Documenting Elicitation / PostCompact polyfills — only mention them as "accepted-limitation" gaps citing `docs/codex-mapping.md`.
- Adding a CI workflow that lints the README for provider-symmetry — out of scope; manual review is sufficient.
