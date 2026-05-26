# Re-home Codex hooks to config-layer install + crack non-interactive hook trust

Tags: #codex #hooks #installer #spike

## Goal

Current focus: OpenAI Codex provider support. This task removes the
last blocker on Done-when bullet #5 (the opt-in real-SDK smoke test
runs cleanly against `examples/taskflow` under Codex) by fixing the
reason autocc's hooks never fire on real codex.

A live validation run (committed at `ffa523e`, documented in
`docs/codex-smoke-results.md`) plus upstream research established the
root cause definitively:

  1. **Plugin-bundled `hooks.json` never executes.** This is an open
     upstream bug — openai/codex issue #16430 — confirmed against
     codex 0.118 through the local 0.132 run: `codex-rs/core/src/
     plugins/manifest.rs` parses `skills`, `mcpServers`, and `apps`
     from the plugin manifest but NOT `hooks`, and hook discovery only
     scans config folders, never plugin roots. autocc currently ships
     its hook inside the plugin (`~/plugins/autocc/hooks.json`), so it
     is silently dropped. The `plugin_hooks` feature flag is "under
     development" and does not change this.
  2. **The supported, working path is config-layer hooks.** Per the
     official Codex hooks docs and issue #16430's own reporter, hooks
     placed at `~/.codex/hooks.json` or in an inline `[hooks]` table
     in `~/.codex/config.toml` "work immediately." The current
     `docs/codex-smoke-results.md` recommends AGAINST writing a
     `[hooks]` block into config.toml on architectural-purity grounds
     — that recommendation is wrong and must be corrected; the
     config-layer path is how codex hooks are meant to be installed
     today.
  3. **Non-managed hooks require trust, and the review is TUI-only.**
     The docs state "Non-managed command hooks must be reviewed and
     trusted before they run" via the `/hooks` command; there is no
     documented non-interactive approval. The live run observed codex
     persisting trust as a `trusted_hash` / `HookTrustStatus::trusted`
     in binary strings but did not locate where it is stored. This
     trust gate is the real obstacle to autocc's unattended
     (`codex exec`) use case.

This task: (1) re-home the Codex installer's hook registration from
the plugin-bundled `hooks.json` to the supported config-layer
location; (2) investigate codex 0.132's persisted hook-trust state
and, if feasible, have the installer pre-establish trust for autocc's
own hook so it fires non-interactively; (3) correct the docs that
steer away from config-layer hooks.

Why now: the live validation and the upstream issues conclusively
show autocc's Codex autopilot is non-functional as shipped — the hook
that drives prompt-suppression, auto-approval, and stop-blocking
literally never runs — so the entire "unattended on Codex" value
proposition is dead until the hook install is re-homed. This is
concrete, unit-testable installer work plus a bounded trust-mechanism
spike, not a passive wait on an upstream fix, and it is the single
highest-leverage step left in the Codex milestone.

## Scope

- `src/autocc/installer.py` — the Codex branch must register the
  autocc hook via a **config-layer** entry rather than (or in
  addition to) the plugin-bundled `hooks.json`. Write either
  `${CODEX_HOME:-~/.codex}/hooks.json` or an inline `[hooks]` table in
  `${CODEX_HOME:-~/.codex}/config.toml` (pick whichever the codex
  0.132 loader honors most reliably; document the choice). Keep the
  plugin manifest + skills install as-is (skills DO work via the
  plugin — the live run proved that end-to-end); only the hook
  registration moves out of the plugin folder. `uninstall --agent
  codex` must cleanly remove the config-layer hook entry too
  (idempotent merge / unmerge, never clobbering unrelated user hooks).
- Hook-trust investigation (bounded spike): determine where codex
  0.132 persists hook trust (`trusted_hash` / `HookTrustStatus`).
  Probe `${CODEX_HOME}` state files, the binary strings, and the
  `startup_hooks_review.rs` / trust-review code paths. Establish
  whether autocc can write that trust state at install time so its
  hook is pre-trusted without a TUI `/hooks` step. If feasible,
  implement it in the installer; if not, document the dead-end
  precisely (what was tried, why it can't work on 0.132).
- `src/autocc/hooks/autocc-hooks-codex.py` — the current script
  already implements the correct project-root resolution chain and
  logs Stop-event decisions to `.autocc/decisions.log`; preserve that
  behavior and adjust only if the config-layer move changes the cwd /
  env contract the hook relies on.
- `docs/codex-mapping.md` — correct §1a and §1c: state that
  plugin-bundled `hooks.json` does NOT fire (cite upstream issue
  #16430) and that config-layer hooks are the working path; document
  the hook-trust review gate and the persisted-trust findings; bump
  the pinned-version note from 0.128.0 to 0.132.0 (the live machine
  has auto-updated).
- `docs/codex-smoke-results.md` — append the upstream cross-reference
  (issues #16430 and #17532, the official hooks docs) and explicitly
  retract the existing "do NOT write a `[hooks]` block into
  config.toml" recommendation, replacing it with the corrected
  guidance.
- `tests/test_installer.py` — add cases pinning the config-layer hook
  install: install writes the config-layer hook entry; uninstall
  removes it; install is idempotent; an unrelated pre-existing user
  hook in the same file is preserved across install/uninstall.

## Design

This is part installer change, part bounded spike. The task is
allowed to complete by EITHER outcome:
  (a) autocc's hook fires non-interactively on codex 0.132 (config-
      layer install + a working pre-established-trust mechanism), or
  (b) a definitive, documented determination that non-interactive
      hook firing is impossible on 0.132 via the avenues explored —
      WITH the config-layer install + corrected docs landed
      regardless, so the moment codex ships the fix (or trust can be
      pre-seeded) autocc is already shaped correctly.

Do NOT gate completion on a passing live smoke — that is operator-run
and stays in Out of scope (the lesson from the prior live-smoke
attempts: a verifier cannot reliably drive a real codex session).
Gate on the installer change being unit-tested, the docs corrected,
and the trust-investigation outcome recorded. Keep all changes
Codex-scoped; the Claude install/hook path must not change.

If the config-layer write "leaks" install state outside the plugin
folder (it does), that is acceptable and correct per upstream — note
it in the docs rather than treating it as a smell. The marketplace-
driven plugin model still owns skills; only hooks move, because the
plugin hook surface is upstream-broken.

## Verification

- `uv run pytest -q` — full unit suite passes (regression gate; no
  Claude-side breakage).
- `uv run pytest -q tests/test_installer.py` — installer tests pass,
  including the new config-layer hook cases.
- `grep -qE "hooks\.json|\[hooks\]|config\.toml" src/autocc/installer.py`
  — the Codex install path references a config-layer hook target.
- prose: `src/autocc/installer.py`'s Codex branch registers the
  autocc hook at a config-layer location (`~/.codex/hooks.json` or
  `~/.codex/config.toml` `[hooks]`), not solely inside the plugin
  folder, and `uninstall --agent codex` removes that entry without
  clobbering unrelated user hooks (judge confirms via Read).
- prose: `docs/codex-mapping.md` is corrected to state plugin-bundled
  `hooks.json` does not fire (citing upstream issue #16430), that
  config-layer hooks are the working path, and the pinned version is
  updated to 0.132.0 (judge confirms via Read).
- prose: `docs/codex-smoke-results.md` records the hook-trust
  investigation outcome — where codex persists hook trust, whether
  autocc can pre-establish it, and the (a)/(b) determination — and
  retracts the old "do NOT write config.toml `[hooks]`" recommendation
  (judge confirms via Read).

## Out of scope

- Getting the live smoke (`tests/smoke/test_reflector_e2e_codex.py`)
  to pass as a hard gate — operator-run only; stays in Out of scope.
  If the trust unlock works, the operator re-runs the smoke per the
  results doc's recommendation #1.
- Filing the upstream codex GitHub issue — recommend it in the docs,
  but a code task must not depend on an external GH action landing.
- Touching the Claude install path or `autocc-hooks.py`.
- Polyfilling Elicitation / PostCompact — separate follow-ups.
- Re-homing skills out of the plugin — skills work via the plugin
  (the live run verified end-to-end); only hooks move.
