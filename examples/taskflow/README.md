# taskflow — autocc example fixture

A small Python CLI project seeded with three workable tasks. Used as the test
bed for autocc's end-to-end smoke test, but also useful as a reference for
what an autocc-ready project looks like:

- `CLAUDE.md` has an `## Autopilot` section pointing at the task list
- `TASKS.md` follows the 5-section format with `TB-N` IDs
- `.autocc/tasks/` holds briefings for prepared tasks
- `.autocc/progress.md` records previously-completed work

## What's on the board

| ID | Status | Task |
|---|---|---|
| TB-1 | Complete | Fix delete persistence bug *(reference: was completed previously)* |
| TB-2 | Complete | Fix status filter bug *(reference: was completed previously)* |
| TB-3 | Ready | Fix `validate_due_date(None)` crash |
| TB-4 | Backlog | Implement `format_csv()` |
| TB-5 | Backlog | Add tests for `TaskStore.search()` |

TB-1 and TB-2 are already fixed and live in Complete so the briefings/progress
log show what a finished task looks like. TB-3 through TB-5 are the actual
work the agent needs to do.

## Try it manually

```bash
# Install autocc first (one-time): `pipx install autocc && autocc install`

cd examples/taskflow
uv venv && uv pip install -e ".[dev]"

uv run pytest -v          # baseline — should show failing tests in TB-3/TB-4 areas
claude                    # open a Claude Code session here, then:
#   /afk                  # autopilot on, reflector starts
```

A complete reflector session should leave you with TB-3/4/5 in the Complete
section, all of `uv run pytest -v` green, and a populated `.autocc/progress.md`.

## Run the automated smoke test

```bash
# From the autocc repo root:
AUTOCC_REAL_SDK=1 pytest tests/smoke/ -v -s
```

The smoke is opt-in (skipped without the env var) because it makes real API
calls and costs a few dollars per run. See [`tests/smoke/README.md`](../../tests/smoke/README.md).
