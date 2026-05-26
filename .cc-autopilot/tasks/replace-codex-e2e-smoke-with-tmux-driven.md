# Replace Codex e2e smoke with tmux-driven TUI test + document hook-trust prereq

Tags: #codex #smoke #tests #tui

## Goal

Current focus: OpenAI Codex provider support. The opt-in real-SDK
smoke test under Done-when bullet #5 currently lives at
`tests/smoke/test_reflector_e2e_codex.py` and drives codex via
`codex exec` — but live runs have established that `codex exec`
does not fire plugin hooks on 0.132/0.133 (upstream issue
openai/codex#16430 plus the `plugin_hooks` "under development"
flag), so that smoke encodes an impossible expectation and cannot
actually pass.

A live tmux-driven validation against the **interactive `codex`
TUI** has independently proved that, with the config-layer hook
install path documented in `docs/codex-mapping.md` and
`docs/codex-smoke-results.md`, plus a one-time operator `/hooks`
trust step, `autocc-hooks-codex.py` does fire on the `Stop` event
and writes `.autocc/decisions.log` correctly — confirmed by the
audit entry `Stop -> stop | board empty; flag dropped` in a real
codex 0.132 TUI run. That's the actual working autopilot loop and
the path Done-when #5 should validate.

This task: replace the existing `tests/smoke/test_reflector_e2e_codex.py`
with a tmux-driven TUI smoke that exercises the validated path, and
document the one-time manual `/hooks` trust step in the README and
the smoke's own docstring so the next operator can re-run it.

Why now: the existing exec-based smoke encodes a known-impossible
expectation (hooks firing under `codex exec` on 0.132/0.133), so
every honest attempt to run it must fail — that's worse than a
missing test because it actively misleads readers into thinking
the install is broken when the real failure is upstream-blocked
and well-understood. Replacing it with the validated TUI path
converts Done-when #5 from a stalled item into a passing opt-in
smoke any operator can re-run with one trivial setup ritual.

## Scope

- **Delete** `tests/smoke/test_reflector_e2e_codex.py` (the
  exec-based smoke). Before deleting, scan its docstring for any
  empirical findings not already captured in
  `docs/codex-smoke-results.md` and migrate them there so nothing
  useful is lost.
- **Add** `tests/smoke/test_reflector_e2e_codex_tui.py` (the new
  tmux-driven TUI smoke). Gating:
  - Skip when `AUTOCC_REAL_SDK` env var is unset (same gate as the
    Claude smoke at `tests/smoke/test_reflector_e2e.py`).
  - Skip when `shutil.which("tmux")` is `None`, with a message
    naming `brew install tmux` as the fix.
  - Skip when `~/.codex/config.toml` lacks autocc's
    `# >>> autocc managed hooks (do not edit) >>>` marker block,
    OR lacks a `[hooks.state."<config>:stop:0:0"]` entry with a
    `trusted_hash` — with a message naming the exact setup
    commands the operator must run (`autocc install --agent codex`
    + open `codex`, run `/hooks`, trust the three entries).
  Test flow inside the body:
    1. Create a workspace under `tmp_path` containing
       `.autocc/flag` and an empty 5-section `TASKS.md`.
    2. Handle project trust either by pre-seeding a marker-bounded
       `[projects."<tmp_path>"]` block into `~/.codex/config.toml`
       with cleanup-on-teardown, OR by detecting and answering
       codex's interactive trust prompt — implementer's choice,
       but the test must NOT leave any persistent mutation in the
       operator's real `~/.codex/` after teardown.
    3. Launch `codex` via `tmux new-session -d -s autocc-smoke-tui
       -x 200 -y 50 "cd <workspace> && codex"`.
    4. Wait for codex's banner. If the update-available prompt
       appears, send `2` then Enter (Skip).
    5. Send a short prompt body (e.g. "Say the word hello and
       stop.") followed by a single Enter (codex 0.132's submit
       key in the TUI; Ctrl+J inserts a newline instead).
    6. Poll for `<workspace>/.autocc/decisions.log` up to ~60s.
    7. Assert the file exists AND contains a `Stop -> stop` entry
       (the mandatory hook-fired evidence captured in the live
       validation).
    8. Quit codex (Ctrl+C twice) and `tmux kill-session`.
- **README.md** — add a short subsection under the existing
  `## Tests` heading documenting the Codex smoke setup ritual:
    1. `autocc install --agent codex` writes the config-layer
       `[[hooks.*]]` block into `~/.codex/config.toml`.
    2. Launch codex interactively, run the `/hooks` slash
       command, and trust the three autocc entries (PreToolUse,
       PermissionRequest, Stop). This persists `trusted_hash`
       values codex needs before it will spawn the hook script.
    3. `AUTOCC_REAL_SDK=1 uv run pytest tests/smoke/test_reflector_e2e_codex_tui.py`.
    Note the per-run cost (~$0.20 of codex usage).
- **docs/codex-smoke-results.md** — append a new
  "Live TUI validation (codex 0.132)" section recording the
  successful real-codex evidence: the exact steps that worked
  (config-layer install + manual `/hooks` trust + tmux-driven
  TUI), the `decisions.log` audit entry observed, and an explicit
  note that this validates Done-when #5 for the interactive path.
  Leave the existing exec-blocked analysis intact for audit — it
  remains true for `codex exec` on 0.132/0.133.

## Design

The new smoke deliberately mirrors what a real operator does — it
does NOT try to install autocc into a sandboxed HOME (that
pattern is exactly what produced the unit-test-leakage bug that
mutated the operator's real `~/.codex/config.toml`; see Out of
scope). Instead it skips cleanly if the operator hasn't done the
install + trust setup yet, and tests only the runtime behavior of
the operator's actual install. The smoke is "live" in the truest
sense: it exercises the same config codex uses for the operator's
day-to-day work.

tmux is the right driver because codex's TUI requires a real TTY,
and a tmux pane provides one while still being scriptable. `codex
exec` is intentionally not used — it does not fire hooks on
0.132/0.133 per the upstream-blocker analysis already documented
in `docs/codex-smoke-results.md`.

Skip-gating is operator-friendly: if any of the three setup
preconditions is missing (no tmux, no autocc install, no trust
state), the test prints a clear actionable message naming exactly
which command to run to fix it. This avoids failing a test on
operator-only state while still giving the operator a precise
next step.

## Verification

- `uv run pytest -q` — full unit suite passes (regression gate;
  the new smoke is skipped without `AUTOCC_REAL_SDK=1`).
- `test -f tests/smoke/test_reflector_e2e_codex_tui.py` — the
  new TUI smoke file exists.
- `test ! -f tests/smoke/test_reflector_e2e_codex.py` — the
  old exec-based smoke has been removed.
- `grep -qE "(tmux|new-session|send-keys)" tests/smoke/test_reflector_e2e_codex_tui.py`
  — the new smoke drives codex via tmux.
- `grep -qE "/hooks" README.md` — README documents the manual
  `/hooks` trust step.
- prose: `tests/smoke/test_reflector_e2e_codex_tui.py` defines
  three skip gates (AUTOCC_REAL_SDK, tmux availability, autocc
  config-layer install + at least one persisted `trusted_hash`)
  with operator-friendly messages naming the exact fix commands
  (judge confirms via Read).
- prose: `docs/codex-smoke-results.md` contains a new
  "Live TUI validation" subsection that records the actual
  decisions.log audit entry observed in a successful real codex
  run, names codex 0.132 as the validated version, and states
  that Done-when #5 is closed for the TUI path while remaining
  upstream-blocked for `codex exec` (judge confirms via Read).
- prose: the new smoke writes ONLY into `tmp_path` plus an
  optional cleanup-on-teardown idempotent marker-guarded
  `[projects."<tmp_path>"]` entry in `~/.codex/config.toml` —
  no writes to `[hooks]`, no plugin install, no other
  persistent real-config mutations (judge confirms via Read).

## Out of scope

- **Fixing the installer-test-leakage bug** (a separate
  test-isolation issue in `tests/test_installer.py` that
  mutated the operator's real `~/.codex/config.toml` with
  pytest-tmp paths). That's its own future task; this smoke
  deliberately avoids the pattern by not running any installer
  inside `tmp_path`.
- **Adding the smoke to CI** — smokes stay operator-triggered
  by design (real cost, real auth, real network).
- **Validating `codex exec` hooks** — still upstream-blocked
  per the existing analysis; the new smoke explicitly uses TUI.
- **Touching the Claude smoke** at
  `tests/smoke/test_reflector_e2e.py` — leave as-is.
- **Auto-establishing the `/hooks` trust step from the
  installer** — still impossible on 0.132/0.133 without
  published hash inputs; a future codex release may unlock this.
- **Driving the full reflector loop end-to-end** as a hard
  gate — the mandatory bar stays "Stop hook fired at least
  once and wrote a `decisions.log` entry." A full
  Backlog → Complete cycle is fine as a stretch but must not
  become a hard requirement.
