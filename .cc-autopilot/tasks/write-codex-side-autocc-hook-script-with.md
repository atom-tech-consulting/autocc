
# Write Codex-side autocc hook script with Codex JSON wire shapes

Tags: #codex #hooks

## Goal

Current focus: OpenAI Codex provider support. Done-when bullet
#1 ("`autocc install --agent codex` wires the Codex-side
equivalents of hooks") requires a hook script that speaks
Codex's wire format, not Claude's. The existing
`src/autocc/hooks/autocc-hooks.py` emits
`hookSpecificOutput.decision.behavior: allow` for permission
events, but the discovery doc (`docs/codex-mapping.md` §2)
documents that Codex parses `permissionDecision: allow` (the
binary rejects unsupported variants by string match:
`PermissionRequest hook returned unsupported …`). Two of
autocc's six hook events have no Codex analog (`Elicitation`,
`PostCompact`) and one matcher does not exist
(`EnterPlanMode`); the script must no-op cleanly on those
inputs rather than crash. Stop and PermissionRequest do have
1:1 analogs and must keep the autopilot loop alive.

Why now: without a Codex-shaped hook script, the Codex install
branch ships a non-functional plugin — the model can load
skills but the autopilot loop dies the first time Codex asks
for permission or the model tries to stop, because Claude-shape
JSON triggers `PermissionRequest hook returned unsupported …`.
Closing this gap is the smallest step that gets a Codex
session through one unattended task.

## Scope

- New file `src/autocc/hooks/autocc-hooks-codex.py` (separate
  from `autocc-hooks.py` to keep each provider's wire format
  legible). Reuse the project-dir / flag / log-decision /
  task-board helpers; only the per-event handlers differ.
  Behavior per event:
    - `pre_tool_use` — Codex has no `AskUserQuestion` /
      `EnterPlanMode` tool to match against, so the matcher
      pattern will never fire. The script must still handle
      the `pre_tool_use` event JSON without crashing: read
      stdin, if the flag is absent emit `{}` and exit.
    - `permission_request` — emit
      `{"permissionDecision": "allow",
        "permissionDecisionReason": "AUTOPILOT: …"}` when
      the autopilot flag is set, log the decision, otherwise
      emit `{}`.
    - `stop` — same contract as the Claude `Stop` handler:
      emit `{"decision": "block", "reason": "AUTOPILOT: …"}`
      when the flag is set, the board is non-empty, and
      `stop_hook_active` is false; otherwise unset the flag
      and emit `{}`. The Codex binary's error string
      `Stop hook returned decision:block without a non-empty
      reason` requires that `reason` is always non-empty when
      blocking.
    - `elicitation` / `post_compact` — Codex emits no such
      hook events. The script should accept these as
      hook_type argv values and emit `{}` (defensive — in
      case the installer wires them by accident); do NOT
      attempt the Claude-shape `additionalContext` injection.
- Honor Codex's `PLUGIN_ROOT` / `CLAUDE_PLUGIN_ROOT` env vars
  (the codex binary mirrors the Claude env-var contract per
  `docs/codex-mapping.md` §1c) when locating the project
  directory; fall back to `cwd` from stdin or `os.getcwd()`.
- Wire the new script into the Codex install branch so
  `~/plugins/autocc/hooks.json` (per the corrected
  home-rooted plugin convention in `docs/codex-mapping.md`
  §1a — `~/.codex/plugins/` is NOT a Codex path) references
  `autocc-hooks-codex.py` instead of the Claude script (the
  installer task previously installed a stub — replace it
  with this real script). Update `src/autocc/installer.py`'s
  `HOOK_BASENAMES` (or the Codex provider equivalent) to
  include the new file.
- New `tests/test_autocc_hook_codex.py` — unit tests that
  pipe representative event JSON into the script via
  `subprocess.run` and assert the response shape:
    - `permission_request` with flag set → JSON with
      `"permissionDecision": "allow"`
    - `permission_request` without flag → empty JSON `{}`
    - `stop` with flag set and non-empty board →
      `{"decision": "block", "reason": ...}` with non-empty
      reason
    - `stop` with `stop_hook_active: true` → empty JSON,
      flag removed
    - `elicitation` / `post_compact` event names → empty
      JSON, no crash

## Design

Keep this script independent of the Claude script — sharing
helpers via an unstructured import becomes a 3rd-provider
trap (`goal.md` Non-goals forbids the generic plugin SDK).
Duplicate the 4-5 helper functions verbatim; total file size
stays under ~250 lines, comparable to the Claude script.

## Verification

- `uv run pytest -q` — full suite passes (regression gate).
- `uv run pytest -q tests/test_autocc_hook_codex.py` — new
  Codex hook tests pass.
- `test -f src/autocc/hooks/autocc-hooks-codex.py` — script
  exists at the expected path.
- `grep -q "permissionDecision" src/autocc/hooks/autocc-hooks-codex.py`
  — script emits the Codex permission shape, not the Claude
  shape.
- `grep -q "autocc-hooks-codex.py" src/autocc/installer.py`
  — installer wires the new script (not the stub) into the
  Codex plugin's `hooks.json`.
- Prose: `tests/test_autocc_hook_codex.py` includes a test
  case that pipes a `stop` event with `stop_hook_active:
  true` and asserts the response is `{}` and the autopilot
  flag has been removed (judge confirms via Read).

## Out of scope

- Polyfilling Elicitation through an MCP server (separate
  follow-up — needs an installer to register the MCP server).
- Polyfilling PostCompact via a `user_prompt_submit` hook
  conditioned on the rollout's most-recent
  `context_compacted` event (separate follow-up).
- Modifying the Claude hook script
  (`src/autocc/hooks/autocc-hooks.py`) — leave its wire
  shape intact for the Claude install path.
- Updating README / ARCHITECTURE — hold until both the
  installer branch and this hook script ship.
