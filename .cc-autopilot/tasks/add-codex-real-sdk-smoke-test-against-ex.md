# Add Codex real-SDK smoke test against examples/taskflow

Tags: #codex #smoke #tests

## Goal

Current focus: OpenAI Codex provider support. Done-when bullet
#5 requires that the opt-in real-SDK smoke test runs cleanly
against `examples/taskflow` under Codex as well as Claude Code
— but TB-2 / TB-3 / TB-4 all landed green against synthetic
fixtures only. Nothing in autocc has actually exercised real
`codex` discovering the installed plugin, loading the skills,
and firing the `autocc-hooks-codex.py` script. This task adds
the missing end-to-end check: install autocc into a sandboxed
HOME, launch codex against `examples/taskflow`, and assert the
Codex-side hook script ran at least once (with a stretch
assertion that the reflector loop moved a task Backlog →
Complete).

Why now: TB-2 / TB-3 / TB-4 produced an installer, a hook
script, and skill-portability changes that all pass synthetic
tests, but the first real codex session against the install
is the first opportunity to catch wire-shape errors,
plugin-discovery gotchas (marketplace path resolution,
`plugin_hooks` feature flag), slash-command invocation
differences, or auth-state coupling. The `docs/codex-mapping.md`
file flags several "verify before depending on it" items
(externalAgentConfig method names, `plugin_hooks` runtime
behavior) — running the smoke is how those open questions
get resolved. Closing this gap converts "green tests" into
"actually works."

## Scope

- New `tests/smoke/test_reflector_e2e_codex.py`, parallel to
  the existing Claude-side `tests/smoke/test_reflector_e2e.py`.
  Reuse the same `AUTOCC_REAL_SDK=1` skip gate (so when both
  files are present, the operator runs both smokes by setting
  one env var).
- Fixture flow inside the new test:
    1. Create a tempdir as sandboxed HOME (set `HOME=<tmp>`
       for the codex subprocess; copy `~/.codex/auth.json`
       and `~/.codex/config.toml` into `<tmp>/.codex/` so
       codex can authenticate without inheriting the real
       home).
    2. Run `autocc install --agent codex` against the
       sandboxed HOME (via `subprocess.run` or directly
       calling the installer entry point with HOME mocked);
       assert `<tmp>/plugins/autocc/.codex-plugin/plugin.json`
       and `<tmp>/.agents/plugins/marketplace.json` exist
       with the expected manifest + entry shapes.
    3. Copy `examples/taskflow` into the tempdir as the
       working project; set its `.autocc/flag` and seed one
       trivial Backlog task in `TASKS.md` (e.g. "add a
       comment to README" — single edit, no real
       computation).
    4. Launch `codex exec` non-interactively with a prompt
       that invokes `/reflector` against the taskflow
       project. Cap wall-clock at ~5 minutes; capture
       stdout/stderr.
    5. Assert (mandatory): the Codex-side hook fired at
       least once. Evidence: `.autocc/decisions.log` in the
       taskflow tempdir contains at least one entry written
       by `autocc-hooks-codex.py`. This proves install →
       discovery → hook-dispatch works end-to-end.
    6. Assert (stretch — soft-fail with a clear message
       rather than hard error): the seeded task moved
       Backlog → Complete in `TASKS.md` AND a commit landed
       on the taskflow branch whose subject references the
       task. If the stretch fails but the mandatory passes,
       the test still passes but logs a warning capturing
       why (max_turns, auth flow, slash-command
       invocation mismatch, etc.).
- One-line README addendum under `## Tests` mentioning that
  `AUTOCC_REAL_SDK=1` now runs both Claude and Codex smokes
  (with a logged-in `codex` CLI required for the Codex
  variant). Do NOT rewrite the broader README — goal.md
  Done-when #4 (full Codex install walkthrough) is a
  separate task.
- The test docstring must capture any slash-command,
  plugin-discovery, or auth-state behaviors observed during
  implementation that diverge from `docs/codex-mapping.md`'s
  predictions. Those observations close the "verify before
  depending on it" items in the discovery doc.

## Design

Mirror `tests/smoke/test_reflector_e2e.py`'s shape (same
fixture lifecycle, same temp-HOME sandboxing pattern, same
on-disk assertion style). If the existing Claude smoke
abstracts setup into helpers, reuse them; otherwise
duplicate the structure verbatim and let a future
"extract shared smoke helper" task de-dup. Dup-now-
refactor-later is consistent with goal.md Non-goals'
ban on a generic provider plugin SDK.

The mandatory assertion is "hook fired at least once"
rather than "full reflector cycle completed" because the
reflector loop itself is already exercised under Claude
in `test_reflector_e2e.py` — duplicating the full-cycle
expectation under Codex risks fragility from auth flow
quirks, codex rate limits, or one-turn slash-command
invocation differences that aren't really an autocc bug.
A single hook firing is sufficient evidence that the
install/discovery/wire-shape path is correct; the
stretch assertion catches the loop-level happy path
when the environment cooperates.

## Verification

- `uv run pytest -q` — full suite passes (regression
  gate); the new smoke is skipped by default.
- `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q
  tests/smoke/test_reflector_e2e_codex.py'` — the new
  smoke runs and passes when the env var is set and a
  logged-in codex CLI is available.
- `test -f tests/smoke/test_reflector_e2e_codex.py` —
  file landed at the expected path.
- `grep -q "AUTOCC_REAL_SDK" tests/smoke/test_reflector_e2e_codex.py`
  — the test honors the smoke-gate env var.
- `grep -qE "(autocc-hooks-codex|decisions\.log)" tests/smoke/test_reflector_e2e_codex.py`
  — the test asserts on hook-fired evidence.
- prose: `tests/smoke/test_reflector_e2e_codex.py` includes
  a fixture that copies `~/.codex/auth.json` (and
  `~/.codex/config.toml`) into a temp HOME before
  launching codex, so the smoke can authenticate without
  modifying the operator's live `~/.codex/` state (judge
  confirms via Read).
- prose: the test docstring documents any slash-command,
  plugin-discovery, or auth-state behaviors observed
  during implementation that diverge from
  `docs/codex-mapping.md`'s predictions (judge confirms
  via Read).

## Out of scope

- Rewriting README/ARCHITECTURE to add a full Codex
  install walkthrough — goal.md Done-when #4 is a
  separate task.
- Adding a CI workflow that runs the codex smoke
  automatically — smokes are operator-triggered by
  design (real $$ cost).
- Extracting a shared smoke-runner helper across
  providers — let dup-now-refactor-later play out; a
  follow-up task can de-dup once both smokes have
  stabilized.
- Polyfilling Elicitation / PostCompact — separate
  follow-ups, triggered by the smoke's findings if
  those gaps actually bite during a real session.
- Modifying the Claude smoke test — leave it as-is;
  this task only adds the Codex variant alongside.
- Verifying the externalAgentConfig migration JSON-RPC
  surface — out of scope for the smoke (the install
  path doesn't use it); a separate task can probe it
  via `codex` source/runtime if/when needed.
## Attempts

### 2026-05-18 — verification_failed
(no summary)
- **kind:** per_task
- **failed_criteria:** [fail] `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py'` — the newsmoke runs and passes wh
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260518T180222Z-TB-5.prompt.md`, `stream: .cc-autopilot/debug/20260518T180222Z-TB-5.stream.jsonl`, `messages: .cc-autopilot/debug/20260518T180222Z-TB-5.messages.jsonl`
### 2026-05-18 — error
(no summary)
- **error:** Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260518T180612Z-TB-5.prompt.md`, `stream: .cc-autopilot/debug/20260518T180612Z-TB-5.stream.jsonl`, `messages: .cc-autopilot/debug/20260518T180612Z-TB-5.messages.jsonl`
### 2026-05-18 — error
(no summary)
- **error:** Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260518T181116Z-TB-5.prompt.md`, `stream: .cc-autopilot/debug/20260518T181116Z-TB-5.stream.jsonl`, `messages: .cc-autopilot/debug/20260518T181116Z-TB-5.messages.jsonl`
