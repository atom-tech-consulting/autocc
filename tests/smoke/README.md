# Real-SDK smoke tests

End-to-end tests that exercise the real `claude` and `codex` CLIs:

- `test_reflector_e2e.py` — full reflector session against the
  [`examples/taskflow`](../../examples/taskflow) fixture using the real
  `claude` CLI.
- `test_reflector_e2e_codex_tui.py` — tmux-driven `codex` TUI run that
  asserts the autocc Stop hook fires on an empty taskboard. Requires
  one-time `autocc install --agent codex` + `/hooks` trust ritual; see
  the test's docstring and the project README's "Codex smoke setup"
  section. (The previous exec-based codex smoke was removed in TB-11 —
  `codex exec` does not fire hooks on codex 0.132 / 0.133, so that
  expectation was impossible by design.)

## Opt-in

These tests are **skipped by default**. They make real API calls (whatever
model your `claude` CLI is configured to use — Opus runs we measured were
~60-90 turns at $2.50-$4.00 each), so budget a few dollars per run. Set the
env var to opt in:

```bash
AUTOCC_REAL_SDK=1 pytest tests/smoke/ -v -s
```

The default suite (`pytest`) still runs only the unit tier under `tests/`,
not anything here.

## Requirements

- `claude` CLI on `$PATH`, authenticated (e.g. `CLAUDE_CODE_OAUTH_TOKEN` set,
  or `claude login` completed)
- `uv` on `$PATH` (used to set up the fixture's venv during the test)
- Python 3.11+
- A working network connection

## What `test_reflector_e2e.py` actually does

1. Picks a workspace root: `tmp_path` by default, or
   `$AUTOCC_SMOKE_WORKSPACE` if set (see "Persistent workspace" below).
2. Copies `examples/taskflow` into `<workspace>/taskflow/` and `git init`s
   it (the reflector commits after each task).
3. Installs autocc into `<workspace>/claude_home/` (skills + hooks +
   statusline + patched `settings.json`).
4. Creates `.autocc/flag` in the fixture copy.
5. Runs `claude -p "/reflector"` against the fixture with a turn/budget cap.
6. Locates the session JSONL that the `claude` CLI wrote under
   `~/.claude/projects/<slug>/<session_id>.jsonl` and copies it to
   `<workspace>/session.jsonl` for inspection.
7. Verifies:
   - TB-3, TB-4, and TB-5 end up in the `## Complete` section of `TASKS.md`
   - `.autocc/progress.md` has entries for each
   - `uv run pytest` is green in the fixture

### Scope caveat

The claude CLI reads `~/.claude/` directly and doesn't honor
`CLAUDE_HOME`, so this smoke runs against whatever skills + hooks the
user has deployed to their real `~/.claude/`. It exercises the
**reflector skill** end-to-end (and indirectly the installer, since
that's what put the fixture's expected paths in motion), but the
isolated autocc-installed copy at `<workspace>/claude_home/` isn't
actually consulted by the CLI run.

Autopilot hook (`autocc-hooks.py`) behavior is covered by the unit
tests under `tests/test_autocc_hook.py` — pure-Python, deterministic,
no API. Together those two tiers cover skill loop + hook decisions.

## Costs and caps

The test caps `--max-turns 100` and `--max-budget-usd 5.00`. Observed runs:

| Run | Turns | Cost | Outcome |
|---|---|---|---|
| 1 | 61 | $2.65 | hit max-turns (was 60) mid-housekeeping after target tasks done |
| 2 | 91 | $4.03 | clean stop — completed target + 2 discovered housekeeping |

Both runs used `claude-opus-4-7[1m]`. Cost is heavily cache-discounted
(~95% of input tokens are cache reads after warm-up).

The reflector legitimately keeps looping after the target tasks are done —
its skill says to run `/housekeeping` when the board is empty and pick up
discovered work. So **the SDK's `terminal_reason` is not a success signal**;
the test deliberately doesn't gate on it. Success is measured purely by the
on-disk state. If the agent crashes before doing the work, the on-disk
assertions catch it.

## Running just the smoke locally

```bash
# from repo root, with autocc installed in editable mode:
uv venv && uv pip install -e ".[dev]"
AUTOCC_REAL_SDK=1 .venv/bin/pytest tests/smoke/ -v -s
```

## Inspecting the run

After a smoke run, the test prints something like:

```
[smoke] terminal_reason=completed turns=91 cost=$4.033599 returncode=0
[smoke] workspace: /Users/you/autocc-smoke-runs/latest
[smoke] session_id: 2ce862b9-0968-4ce1-b694-8fa237bdd3cd
[smoke] session trajectory (origin): /Users/you/.claude/projects/.../2ce862b9-...jsonl
[smoke] session trajectory (copy):   /Users/you/autocc-smoke-runs/latest/session.jsonl
```

The session JSONL is the full agent trajectory (~250+ events: user/assistant
messages, tool calls, tool results, hook decisions). It's preserved by the
claude CLI under `~/.claude/projects/`; the test copies it next to the
workspace as `session.jsonl` so it doesn't get lost when pytest cleans tmp.

### Persistent workspace

By default the test puts everything under pytest's `tmp_path`, which the next
pytest run will rotate away. To inspect the project's final state, the agent's
commits, the briefings, etc., set a persistent location:

```bash
AUTOCC_REAL_SDK=1 \
AUTOCC_SMOKE_WORKSPACE=~/autocc-smoke-runs/latest \
pytest tests/smoke/ -v -s
```

The fixture wipes and recreates that directory at the start of each run, so
prior runs aren't preserved — `cp -r` it elsewhere first if you need a
history.
