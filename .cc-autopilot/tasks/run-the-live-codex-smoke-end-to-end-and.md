# Run the live Codex smoke end-to-end and confirm it actually passes

Tags: #codex #smoke #tests #live

## Goal

Current focus: OpenAI Codex provider support. Done-when bullet #5
requires that the opt-in real-SDK smoke test runs cleanly against
`examples/taskflow` under Codex as well as Claude Code. Every other
Codex criterion (install branch, hook script, portable skills, docs)
has shipped and verified across TB-2 / TB-3 / TB-4 / TB-7 / TB-8 —
but #5 has never actually been confirmed. The smoke file
`tests/smoke/test_reflector_e2e_codex.py` exists and is structurally
checked, but TB-6 relocated its live invocation to `## Out of scope`
so the daemon could verify it without spending real codex credits.
That left the single highest-signal validation of the whole
milestone — does a real `codex` session actually discover the
installed plugin, load the skills, and fire `autocc-hooks-codex.py`?
— unproven.

This task closes that gap: actually run the live smoke against the
real `codex` CLI, get it to genuinely pass, and capture the outcome
in a committed results artifact. If the live run surfaces real bugs
in the installer, the hook script, or the test itself, fix them here
until the smoke passes; the discovery doc (`docs/codex-mapping.md`)
flagged several "verify before depending on it" items
(`plugin_hooks` runtime behavior, marketplace path resolution,
auth-state coupling) and this is the task that resolves them against
reality.

Why now: the Codex roadmap is otherwise complete and the daemon has
already advanced the focus pointer to exhausted — but declaring the
milestone done while its core "it actually works" check has never
been run is premature. This is the one task standing between
"green synthetic tests" and "confirmed working against real codex."

## Scope

- Run `AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py`
  against the real, locally-installed `codex` CLI (codex-cli
  0.128.0 at `/opt/homebrew/bin/codex`, already logged in under the
  operator's `~/.codex/auth.json`).
- If the smoke fails, diagnose and fix the root cause — this may
  touch any of:
    - `src/autocc/installer.py` (the Codex install branch / plugin
      manifest / marketplace entry shape)
    - `src/autocc/hooks/autocc-hooks-codex.py` (the Codex wire-shape
      hook script)
    - `tests/smoke/test_reflector_e2e_codex.py` itself (fixture
      setup, sandboxed HOME, `--enable plugin_hooks`, trust-level
      seeding, the assertion logic)
  Iterate until the smoke's mandatory assertion (autocc-hooks-codex.py
  fired at least once, evidenced in the workspace's
  `.autocc/decisions.log`) genuinely passes against real codex.
- Create `docs/codex-smoke-results.md` capturing the real run:
  the exact command, codex version, pass/fail of the mandatory and
  stretch assertions, the hook-fired evidence, and a list of any
  bugs found and fixed to get it green. This is the artifact that
  records that the live validation actually happened.
- If — and only if — the smoke cannot be made to pass because of an
  environment constraint outside the codebase (codex account/rate
  limits, network egress blocked in the sandbox, an auth flow that
  needs interactive login), report `blocked` via
  `report_result(status="blocked", ...)` with a summary naming the
  exact wall hit, AND still commit `docs/codex-smoke-results.md`
  documenting how far the run got and what blocked it. Do NOT thrash
  retries against an unresolvable environment wall.

## Design

This is the one Codex task where running the live smoke as the
verification gate is correct: the deliverable IS a passing live run,
so gating on it is intentional (contrast the earlier smoke-authoring
task, where the live invocation was an incidental side-effect that
wrongly froze the task). The task agent runs on the same machine as
the operator's codex install and inherits its auth, so it can drive
`codex exec` directly.

Keep fixes minimal and provider-scoped — `goal.md` Non-goals still
bans a generic provider plugin SDK. If a fix touches the Claude-side
install/hook paths, that's a smell; the Codex smoke should be
closeable without disturbing Claude behavior. Re-run the full unit
suite after any installer/hook fix to confirm no Claude-side
regression.

The results artifact is the durable record: even a green run is
worth documenting, because the next person to touch the Codex
install path needs to know what "working" looked like and which of
the discovery doc's open questions got resolved.

## Verification

- `uv run pytest -q` — full unit suite passes (regression gate;
  confirms no Claude-side breakage from any fix).
- `bash -c 'AUTOCC_REAL_SDK=1 uv run pytest -q tests/smoke/test_reflector_e2e_codex.py'`
  — the live Codex smoke passes against the real codex CLI. This is
  the core gate for this task.
- `test -f docs/codex-smoke-results.md` — the results artifact
  landed.
- prose: `docs/codex-smoke-results.md` records an actual real-codex
  run — the exact command, codex version, the mandatory hook-fired
  assertion outcome, and any bugs found + fixed to reach green
  (judge confirms via Read; a purely hypothetical or templated doc
  with no real run output does not satisfy this).
- prose: if the run required code changes to pass, the diff touches
  the Codex install/hook/test surface and `docs/codex-smoke-results.md`
  explains each fix and which `docs/codex-mapping.md` "verify before
  depending on it" item it resolved (judge confirms via Read).

## Out of scope

- Adding the Codex smoke to CI — smokes stay operator-triggered by
  design (real cost).
- Extracting a shared smoke-runner helper across the Claude and
  Codex smokes — separate refactor task if desired.
- Re-running or modifying the Claude-side smoke
  (`tests/smoke/test_reflector_e2e.py`) — leave it as-is.
- Broadening the smoke to assert a full Backlog → Complete reflector
  cycle as a hard gate — the mandatory bar stays "hook fired at
  least once"; a full-cycle pass is a welcome stretch but must not
  become a hard requirement (it's fragile against codex rate limits
  / auth-flow quirks that aren't autocc bugs).
- Probing the externalAgentConfig migration JSON-RPC surface — the
  install path doesn't use it; out of scope for the smoke.
## Attempts

### 2026-05-21 — error
(no summary)
- **error:** Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T063846Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T063846Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T063846Z-TB-9.messages.jsonl`
### 2026-05-21 — error
(no summary)
- **error:** Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T064422Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T064422Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T064422Z-TB-9.messages.jsonl`
### 2026-05-21 — error
(no summary)
- **error:** Exception: Command failed with exit code 1 (exit code: 1)
Error output: Check stderr output for details
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T065710Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T065710Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T065710Z-TB-9.messages.jsonl`
### 2026-05-21 — timeout
(no summary)
- **timeout_s:** 1200
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T165041Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T165041Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T165041Z-TB-9.messages.jsonl`
### 2026-05-21 — timeout
(no summary)
- **timeout_s:** 1200
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T171118Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T171118Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T171118Z-TB-9.messages.jsonl`
### 2026-05-21 — timeout
(no summary)
- **timeout_s:** 1200
- **stderr_tail:** 
- **Debug dumps:** `prompt: .cc-autopilot/debug/20260521T173154Z-TB-9.prompt.md`, `stream: .cc-autopilot/debug/20260521T173154Z-TB-9.stream.jsonl`, `messages: .cc-autopilot/debug/20260521T173154Z-TB-9.messages.jsonl`
