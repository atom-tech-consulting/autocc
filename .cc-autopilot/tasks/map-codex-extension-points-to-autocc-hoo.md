# Map Codex extension points to autocc hook + skill requirements

Tags: #codex #discovery #docs

## Goal

Discovery task threading back to Current focus: OpenAI Codex provider
support. Produce a single markdown document that, for each behavior
autocc relies on inside Claude Code, names the equivalent Codex
extension point (or records "no analog"). Without this mapping every
downstream installer or hook task is guesswork — we would be writing
Codex-side code blind.

Specifically, the document must cover:
- Each of autocc's six Claude-Code hook events (PreToolUse for
  AskUserQuestion and EnterPlanMode, PermissionRequest, Elicitation,
  Stop, PostCompact) mapped to a Codex extension point or marked
  "no analog".
- The on-disk config directory Codex reads at startup (the target
  `autocc install --agent codex` will write into).
- Each of autocc's six skills (afk, reflector, taskboard, tb,
  housekeeping, commit-changes) classified as portable-as-is,
  needs-provider-specific-glue, or no-codex-analog.
- A short list of "no analog" gaps that will need to be either
  polyfilled, documented, or accepted as Codex-side limitations.

Why now: this is the first task under the new Codex focus, and the
v0.1.0 installer + hook script hard-code Claude Code's surface area.
Every subsequent installer/hook/skill task is speculative until the
mapping exists, so doing this first de-risks the milestone and lets
downstream briefings cite concrete Codex extension points instead of
guesses.

## Scope

- `docs/codex-mapping.md` — new file, the deliverable.
- Read-only inspection of the locally-installed codex CLI
  (`codex --help`, `codex <subcommand> --help`, `~/.codex/` if it
  exists, plus any docs the binary ships) to determine its actual
  extension surface.
- Cross-reference against `ARCHITECTURE.md` (the canonical list of
  hook events autocc cares about), `~/.claude/hooks/autocc-hooks.py`
  if installed locally, and the skill markdowns under `skills/`.

## Design

Single markdown file at `docs/codex-mapping.md`. Suggested section
shape:

1. Codex config + extension surface — where does codex read config,
   what extension points exist, what is the analog to
   `~/.claude/settings.json`.
2. Hook event mapping table — one row per autocc hook event, columns
   for Claude Code event name, Codex equivalent (or "no analog"), and
   notes on the impedance mismatch.
3. Skill portability table — one row per autocc skill, columns for
   skill name, current Claude-Code-specific assumptions, Codex
   portability classification.
4. Gap list — bullets naming the "no analog" cases, each tagged
   "polyfill candidate" / "document and skip" / "accept as limitation"
   with a one-line rationale.

This is research output, not a design doc — bias toward citing codex
CLI help text and config-file shapes verbatim over speculation. If a
behavior is undocumented in codex 0.128.0, record it as such rather
than inventing one.

## Verification

- `uv run pytest -q` — full suite still passes (regression gate).
- `test -f docs/codex-mapping.md` — deliverable landed at the
  expected path.
- prose: docs/codex-mapping.md contains a hook event mapping table
  with one row for each of: PreToolUse AskUserQuestion, PreToolUse
  EnterPlanMode, PermissionRequest, Elicitation, Stop, PostCompact.
- prose: docs/codex-mapping.md identifies the on-disk config
  directory Codex reads at startup, named explicitly (e.g.
  `~/.codex/config.toml` or whatever path Codex 0.128.0 actually
  uses).
- prose: docs/codex-mapping.md contains a skill portability section
  classifying each of autocc's six skills (afk, reflector, taskboard,
  tb, housekeeping, commit-changes) as portable-as-is,
  needs-provider-specific-glue, or no-codex-analog.
- prose: docs/codex-mapping.md ends with a gap list naming each
  Claude-Code feature that has no Codex analog, with a one-line
  disposition (polyfill / document-and-skip / accept-as-limitation).

## Out of scope

- Writing any installer code for Codex (the `autocc install --agent
  codex` branch). Follow-up briefing once this mapping exists.
- Writing any Codex-side hook script. Same — follow-up.
- Modifying ARCHITECTURE.md to add a Codex section. Hold until the
  mapping is settled and reviewed.
- Speculative Codex behaviors not present in the locally-installed
  codex 0.128.0 binary. Record absent surfaces as "no analog" rather
  than inventing them.
