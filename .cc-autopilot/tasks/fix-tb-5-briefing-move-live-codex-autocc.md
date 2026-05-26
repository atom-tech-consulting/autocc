## Goal

Current focus: OpenAI Codex provider support. TB-5 ("Add Codex
real-SDK smoke test against examples/taskflow") landed its
implementation at commit `e0d1b66` (file
`tests/smoke/test_reflector_e2e_codex.py` with auth-copying
fixture and decisions.log assertion), but the task is now Frozen
with `retry_exhausted` after three attempts. Attempt 1's
`verification_failed` event shows 5/6 bullets passed — the only
failing bullet is

> `` `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py'` `` — the new smoke runs and passes when the env var is set and a logged-in codex CLI is available.

The daemon's per-task verifier ran this bullet with
`AUTOCC_REAL_SDK=1` set, which causes the smoke to skip the
`pytest.skip(...)` gate and try to launch a real `codex` CLI.
The daemon environment has no logged-in codex, so the bullet
fails — and will keep failing on every retry. This is the same
pattern flagged in CLAUDE.md's failure-review section ("`Manual:
kick a long-running task... handler replies in <30s` kept failing
because the verifier cannot observe a live operator action") and
the same shape as TB-122.

Critically, the briefing's own `## Out of scope` already says
smokes are "operator-triggered by design (real $$ cost)" — so the
live-run bullet contradicts its own scope statement and should
never have been a gating Verification criterion.

Why now: TB-5 is Frozen at `retry_exhausted` blocking the last
Done-when bullet ("opt-in real-SDK smoke test runs cleanly...
under Codex as well as Claude Code"). The implementation is on
disk per commit `e0d1b66`; only the briefing needs surgery so
the daemon can confirm the remaining auto-verifiable bullets and
let the operator unfreeze TB-5 for promotion. Without this fix
TB-5 stays Frozen indefinitely and the smoke-coverage gap
remains formally open even though the test file exists.

## Scope

- Edit `.cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md`:
  - Remove the bullet
    `` `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py'` ``
    from the `## Verification` section.
  - Add a single bullet to the existing `## Out of scope` section
    documenting that the live smoke is operator-triggered with
    `AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py`
    (requires a logged-in `codex` CLI), so it cannot be a gating
    daemon check.
  - Leave all other bullets in `## Verification` unchanged: the
    full-suite regression gate, `test -f` file-existence check,
    two `grep -qE` structural checks, and the two prose bullets
    (fixture auth-copy + docstring divergence-notes).
- Do NOT modify `tests/smoke/test_reflector_e2e_codex.py` itself —
  the test was already accepted by attempt 1's structural checks
  and is on disk at commit `e0d1b66`.
- Do NOT unfreeze TB-5 — the operator owns `ap2 unfreeze TB-N`.

## Design

Pure briefing edit. No code, no test, no install change. After
this lands, the operator runs `ap2 unfreeze TB-5`; the daemon's
next tick re-dispatches TB-5; the per-task verifier re-runs the
revised `## Verification` section, which now contains only
auto-verifiable bullets that attempt 1 already passed → TB-5
promotes to Complete. The actual real-SDK smoke remains
operator-triggered (matching the briefing's own `## Out of scope`
intent and goal.md's "opt-in" framing).

This is the standard `#fix-briefing` shape from CLAUDE.md's
failure-review section: classification `edit-briefing`, action
"propose ONE meta fix-task whose briefing instructs the agent to
rewrite the broken bullets in the original briefing file."

## Verification

- `test -f .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md` — briefing file still present.
- `grep -vq "AUTOCC_REAL_SDK=1 uv run pytest" .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md || ! grep -A1 "## Verification" .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md | grep -q "AUTOCC_REAL_SDK=1 uv run pytest"` — the live-codex pytest invocation no longer appears as a gating bullet.
- `awk '/^## Out of scope/,/^## /' .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md | grep -q "AUTOCC_REAL_SDK"` — the live-codex invocation is now documented in `## Out of scope` as the operator's manual smoke trigger.
- `grep -q "tests/smoke/test_reflector_e2e_codex.py" .cc-autopilot/tasks/add-codex-real-sdk-smoke-test-against-ex.md` — the briefing still references the test file path (sanity check that the edit didn't gut the briefing).
- `test -f tests/smoke/test_reflector_e2e_codex.py` — Prose: the smoke test file from TB-5 commit `e0d1b66` remains on disk; this task only edits the briefing, not the test.
- `uv run pytest -q` — full pytest suite still passes (regression gate; the Codex smoke is skipped by default).

## Out of scope

- Editing `tests/smoke/test_reflector_e2e_codex.py` itself (TB-5 already shipped it).
- Unfreezing TB-5 (operator owns `ap2 unfreeze`).
- Adding a stubbed-codex unit test that mocks the real-SDK path — separate follow-up if attempt-2 of TB-5 surfaces fresh issues.
- Editing any other Frozen task's briefing.
- Documenting the manual smoke procedure in README/ARCHITECTURE — that's the scope of the parallel README walkthrough task.
