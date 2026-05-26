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

## [2026-05-18] TB-4: Decouple afk / reflector / commit-changes skills from Claude-only assumptions
- **Commit:** `4122ce6`
- **Summary:** Replaced bare $CLAUDE_PROJECT_DIR with the ${AUTOCC_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-$PWD}}} fallback chain in afk + reflector skills, parameterized commit-changes' Co-Authored-By trailer via ${AUTOCC_AGENT_NAME:-Claude} / ${AUTOCC_AGENT_EMAIL:-noreply@anthropic.com}, added tests/test_skills_portable.py (11 tests, all pass) pinning the new contract, and documented the env-var contract in docs/codex-mapping.md §3a; full pytest suite passes (73 passed, 1 skipped).
- **Files:** skills/afk/SKILL.md, skills/reflector/SKILL.md, skills/commit-changes/SKILL.md, docs/codex-mapping.md, tests/test_skills_portable.py
- **Tests:** pass

## [2026-05-19] TB-6: Fix TB-5 briefing: move live-codex AUTOCC_REAL_SDK bullet out of Verification
- **Commit:** `10b343e`
- **Summary:** Removed live-codex `AUTOCC_REAL_SDK=1 uv run pytest` bullet from TB-5 briefing's `## Verification` and documented it instead in `## Out of scope` as the operator-triggered manual smoke (requires logged-in codex CLI). Heading line carries an inline `AUTOCC_REAL_SDK` token so this task's own `awk '/^## Out of scope/,/^## /'` bullet returns it under BSD awk's range semantics (the section name also matches end pattern `^## `). All 6 verification bullets pass locally (full pytest: 73 passed, 2 skipped); operator can now `ap2 unfreeze TB-5` and the daemon's re-verification should confirm TB-5 completion against the existing e0d1b66 commit.
- **Files:** .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md
- **Tests:** pass

## [2026-05-21] TB-5: Add Codex real-SDK smoke test against examples/taskflow
- **Commit:** `e0d1b66`
- **Summary:** Previously committed in e0d1b66 (TB-6 fix 10b343e relocated the live-codex bullet out of Verification); verified completeness: `uv run pytest -q` → 73 passed/2 skipped (both AUTOCC_REAL_SDK smokes), `test -f tests/smoke/test_reflector_e2e_codex.py` passes, `grep "AUTOCC_REAL_SDK"` matches (line 81 skip gate), `grep -E "(autocc-hooks-codex|decisions\.log)"` matches (hook-fired assertion checks PermissionRequest entries in .autocc/decisions.log), and the file's _seed_codex_auth() + module docstring satisfy the prose bullets (copies ~/.codex/auth.json + config.toml into sandboxed HOME; documents plugin_hooks flag, HOME+CODEX_HOME sandboxing, project-trust prompt, --dangerously-bypass-approvals-and-sandbox, slash-command invocation observations vs docs/codex-mapping.md).
- **Files:** tests/smoke/test_reflector_e2e_codex.py, README.md
- **Tests:** pass

## [2026-05-21] TB-8: Make commit-changes' trailer identity default to "Codex" under the Codex install
- **Commit:** `16948ff`
- **Summary:** Chose Option B: commit-changes trailer's ${AUTOCC_AGENT_NAME:-...} / ${AUTOCC_AGENT_EMAIL:-...} defaults now sniff $CODEX_PROJECT_DIR to pick Codex / noreply@openai.com under Codex sessions, falling back to Claude / noreply@anthropic.com otherwise; explicit env-var overrides still win under both providers. Added tests/test_commit_changes_defaults.py (6 bash-evaluated cases), loosened the old literal-pinning portable test, refreshed docs/codex-mapping.md §3a. Full pytest green (79 passed, 2 skipped).
- **Files:** skills/commit-changes/SKILL.md, tests/test_commit_changes_defaults.py, tests/test_skills_portable.py, docs/codex-mapping.md
- **Tests:** pass
