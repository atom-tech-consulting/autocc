# Progress

## [2026-05-17] TB-1: Map Codex extension points to autocc hook + skill requirements
- **Commit:** `98ccd89`
- **Summary:** Added docs/codex-mapping.md mapping autocc's six hook events and six skills to Codex 0.128.0 extension points (hooks engine, plugin manifest, ~/.codex/), with a five-item gap list classifying AskUserQuestion / EnterPlanMode / Elicitation / PostCompact / statusline as polyfill / document-and-skip / accept-as-limitation; full test suite still passes (29 passed, 1 skipped).
- **Files:** docs/codex-mapping.md
- **Tests:** pass

## [2026-05-18] TB-2: Add `--agent codex` install branch to autocc installer
- **Commit:** `4164c86`
- **Summary:** Added `--agent {claude,codex}` flag to install/uninstall/status; Codex branch writes a plugin folder at ${AUTOCC_CODEX_PLUGIN_ROOT:-~/plugins}/autocc/ with .codex-plugin/plugin.json, all six skills, hooks.json (PreToolUse/PermissionRequest/Stop) plus a stub hook script, and registers it via ~/.agents/plugins/marketplace.json. 17/17 installer tests pass (9 new codex cases); full suite 38 passed, 1 skipped.
- **Files:** src/autocc/cli.py, src/autocc/installer.py, tests/test_installer.py
- **Tests:** pass

## [2026-05-18] TB-3: Write Codex-side autocc hook script with Codex JSON wire shapes
- **Commit:** `1818a0e`
- **Summary:** Added autocc-hooks-codex.py emitting Codex's permissionDecision/stop wire shapes (with defensive no-ops for elicitation / post_compact / pre_tool_use), rewired installer Codex branch to copy the real script in place of the stub, and added 24 subprocess-driven tests covering all event paths + PLUGIN_ROOT/CLAUDE_PLUGIN_ROOT env-var fallbacks; full suite 62 passed / 1 skipped.
- **Files:** src/autocc/hooks/autocc-hooks-codex.py, src/autocc/installer.py, tests/test_autocc_hook_codex.py
- **Tests:** pass
