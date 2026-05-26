
# Add `--agent codex` install branch to autocc installer

Tags: #codex #installer

## Goal

Current focus: OpenAI Codex provider support. Done-when bullet
#1 requires that `autocc install --agent codex` wires the
Codex-side equivalents of hooks + skills into the canonical
Codex plugin layout (a plugin folder under `~/plugins/<name>/`
registered via `~/.agents/plugins/marketplace.json`) so an
unattended run works end-to-end with no manual fix-up. Today `src/autocc/cli.py` exposes only `install` with
no agent flag and `src/autocc/installer.py` hard-codes
`~/.claude/` plus the Claude `settings.json` hook shape. The
already-committed discovery doc `docs/codex-mapping.md`
identifies the install targets: a plugin folder at
`~/plugins/autocc/` (the home-rooted convention per
`~/.codex/skills/.system/plugin-creator/SKILL.md` — Codex
discovers plugins via marketplaces, not by scanning
`~/.codex/plugins/`, which is NOT a Codex convention) containing
`.codex-plugin/plugin.json`, `skills/`, and `hooks.json`, plus
a marketplace entry at `~/.agents/plugins/marketplace.json`
with `source.path: ./plugins/autocc`. Wire that branch
end-to-end (installer + CLI flag + status + uninstall + tests).
The hook script body is intentionally deferred to a separate
follow-up — for this task ship a stub hook that exits 0 so the
plugin loads cleanly.

Why now: the installer's hard-coded Claude paths block every
other Codex-provider workstream (the real hook script needs a
defined plugin-root path to write into; skill-glue work needs
a settled install layout to test against; README/ARCHITECTURE
updates need a real install command to document). Landing the
scaffolding here is the smallest unblocking step.

## Scope

- `src/autocc/cli.py` — add `--agent {claude,codex}` flag
  (default `claude`) to the `install`, `uninstall`, and
  `status` subparsers; thread the value into the installer
  entry-points.
- `src/autocc/installer.py` — factor the Claude-specific
  bits behind an internal provider abstraction (e.g.
  `_claude_provider()` / `_codex_provider()` returning paths
  + a settings-patch helper); add a Codex implementation that
  writes:
    - `~/plugins/autocc/.codex-plugin/plugin.json` with
      `name=autocc`, `version`, `description`, `skills`,
      `hooks` keys (Codex plugin manifest shape per
      `~/.codex/skills/.system/plugin-creator/SKILL.md`; the
      scaffold's manifest sets `"hooks": "./hooks.json"`)
    - `~/plugins/autocc/skills/<name>/SKILL.md` for all six
      skills (copy from the shared payload)
    - `~/plugins/autocc/hooks.json` registering the autocc
      hook command for each Codex-supported event
      (`pre_tool_use`, `permission_request`, `stop`) — the
      hook script body itself stays as a stub for now
    - a marketplace entry at
      `~/.agents/plugins/marketplace.json` with
      `source.path: ./plugins/autocc`, idempotent merge by
      name; if the marketplace file doesn't exist yet, seed
      it with top-level `name`, `interface.displayName`, and
      `plugins: []` per the plugin-creator skill's documented
      shape before adding the entry.
  - The plugin folder location does NOT depend on `CODEX_HOME`
    (plugin discovery is marketplace-driven, not a scan of
    `CODEX_HOME`); the installer should honor a single
    `AUTOCC_CODEX_PLUGIN_ROOT` override (defaulting to
    `~/plugins`) for testability, mirroring how the Claude
    branch honors `CLAUDE_HOME`.
- `tests/test_installer.py` — add cases that exercise the
  `--agent codex` branch end-to-end against a temp directory
  used as `AUTOCC_CODEX_PLUGIN_ROOT` (and a separate temp
  dir for the marketplace.json parent). At minimum: install
  creates the plugin tree at `<temp>/autocc/`; uninstall
  removes it AND the marketplace entry; install is
  idempotent; status reports the codex install correctly.
- Do NOT touch `src/autocc/hooks/autocc-hooks.py` runtime
  behavior here — install a stub for now; a separate task
  will write the real Codex hook body.

## Design

Keep the abstraction minimal — `goal.md` Non-goals explicitly
ban building a generic provider plugin SDK. Two concrete
provider helpers in `installer.py` is enough; a `Provider`
dataclass with fields (`home_dir`, `skills_dest`,
`hooks_dest`, `settings_patch_fn`, `uninstall_paths`) is the
upper bound. The Codex branch emits a plugin-shaped install
(not a `~/.codex/config.toml` patch) because Codex has
explicit plugin infrastructure and uninstall reduces to one
`rmtree` plus one marketplace entry removal.

## Verification

- `uv run pytest -q` — full suite passes (regression gate).
- `uv run pytest -q tests/test_installer.py` — installer
  tests pass, including the new Codex cases.
- `grep -q -- "--agent" src/autocc/cli.py` — CLI flag is
  present in the parser definition.
- `grep -qE "codex" src/autocc/installer.py` — installer
  references Codex as a known provider.
- Prose: `src/autocc/installer.py` defines a Codex install
  path that writes a `.codex-plugin/plugin.json` manifest
  inside `${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/`
  and adds a `source.path: ./plugins/autocc` entry to
  `~/.agents/plugins/marketplace.json` (judge confirms via
  Read of the new helper).
- Prose: `tests/test_installer.py` includes at least one
  test whose name contains `codex` and which sets a temp
  `AUTOCC_CODEX_PLUGIN_ROOT` plus a temp marketplace path,
  runs `install --agent codex`, asserts the plugin tree
  exists at `<temp>/autocc/` AND the marketplace.json
  contains a matching `plugins[]` entry; running
  `uninstall --agent codex` removes both.

## Out of scope

- Writing the real Codex hook body (separate follow-up).
- Touching skill markdowns for `CLAUDE_PROJECT_DIR` /
  `Co-Authored-By` glue (separate follow-up).
- Polyfilling Elicitation or PostCompact via an MCP server
  or `user_prompt_submit` hook — defer until the install
  path is functional.
- Updating README / ARCHITECTURE — hold until the install
  branch is reviewed and merged.
- Adding a real-SDK smoke test under Codex — separate
  follow-up once the install path is functional.
