# taskflow

Python task management CLI. Run tests with `uv run pytest -v`. Lint with `uv run flake8 src/ tests/`.

## Dev setup
- Python 3.11+, dependency: `click`
- Tests: `uv run pytest -v`
- Lint: `uv run flake8 src/ tests/`

## Autopilot

- Task list: `TASKS.md`
- Task briefings: `.autocc/tasks/`
- Progress log: `.autocc/progress.md`
- Next task ID: TB-6

## Architecture
- `src/taskflow/models.py` — data models (Task, Priority, Status)
- `src/taskflow/store.py` — JSON file persistence (CRUD)
- `src/taskflow/cli.py` — Click CLI commands
- `src/taskflow/validators.py` — input validation
- `src/taskflow/formatters.py` — output formatting (table, json, csv)
