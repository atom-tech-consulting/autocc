---
name: housekeeping
description: "Scan the codebase for maintenance tasks — lint errors, broken tests, dead code, stale comments. Returns taskboard-formatted lines. Called by reflector during DISCOVER or invoked manually."
user_invocable: true
---

<command-name>housekeeping</command-name>

# Housekeeping

Scan the codebase for implicit maintenance tasks. Returns discovered issues as taskboard-formatted task lines with `#housekeeping` tag. Does NOT modify TASKS.md — the caller decides what to append.

## Usage

- `/housekeeping` — full scan, all categories
- `/housekeeping lint` — lint/type errors only
- `/housekeeping tests` — broken tests only
- `/housekeeping dead-code` — dead code only
- `/housekeeping comments` — stale comments only
- `/housekeeping docs` — documentation consistency only

## How it works

1. Detect project tooling (check `pyproject.toml`, `package.json`, `Makefile`, `Cargo.toml`, etc.)
2. Run the relevant scan categories
3. Deduplicate against existing Backlog (read TASKS.md, skip issues already tracked)
4. Output new task lines to the user (or return them to the calling skill)

## Scan categories

Run in this order. Skip categories where the project has no relevant tooling configured.

### 1. Lint / type errors

Detect and run the project's configured linter or type checker:

| Indicator | Command to run |
|-----------|----------------|
| `pyproject.toml` with `[tool.flake8]` or `[tool.ruff]` | `uv run flake8` or `uv run ruff check` |
| `pyproject.toml` with `[tool.mypy]` | `uv run mypy` |
| `package.json` with `lint` script | `npm run lint` |
| `Makefile` with `lint` target | `make lint` |
| `.eslintrc*` exists | `npx eslint .` |

Parse the output. Group related errors (same file, same rule) into one task. Each distinct group becomes one task line.

Example output:
```
- [ ] **TB-N** **Fix ruff E401 errors in src/store.py** `#housekeeping` — 3 unused import errors (lines 5, 12, 18)
```

### 2. Broken tests

Run the test suite:

| Indicator | Command to run |
|-----------|----------------|
| `pyproject.toml` with `[tool.pytest]` | `uv run pytest --tb=no -q` |
| `package.json` with `test` script | `npm test` |
| `Makefile` with `test` target | `make test` |

Parse failures. Each failing test (or group of related failures in the same file) becomes one task line.

Example:
```
- [ ] **TB-N** **Fix test_store.py::test_delete_persists** `#housekeeping` — assertion error, deleted task reappears after reload
```

### 3. Dead code

Use lightweight heuristics — do NOT run full coverage analysis:

- **Unused imports**: grep for imports, check if the imported name is used elsewhere in the file
- **Commented-out code blocks**: look for 3+ consecutive commented lines that appear to be code (contain `=`, `def`, `class`, `return`, `if`, etc.)
- **Unreachable code**: `return` followed by non-comment code at the same indent level

Keep this fast — scan `src/` or the main source directory, not the entire repo. Skip `vendor/`, `node_modules/`, `.venv/`, etc.

Example:
```
- [ ] **TB-N** **Remove unused imports in src/models.py** `#housekeeping` — 2 unused imports: `os`, `typing.Optional`
```

### 4. Stale comments

Look for comments that contradict adjacent code:

- TODO/FIXME/HACK/XXX comments that describe something already fixed
- Docstrings whose parameter lists don't match the function signature
- Comments saying "this is temporary" on code that hasn't changed in many commits

This is the least reliable category — only report clear contradictions, not ambiguous cases.

Example:
```
- [ ] **TB-N** **Remove stale TODO in src/cli.py:42** `#housekeeping` — TODO says "add validation" but validation was added in the function below
```

### 5. Documentation consistency

Cross-validate project documents to find inconsistencies and stale references:

- **CLAUDE.md vs reality** — check that paths, tool names, and deployment instructions in CLAUDE.md match what actually exists. Run `ls` on referenced directories, check that mentioned scripts are present.
- **Skill references** — check that skills reference each other correctly. Verify skill names match after renames.
- **TASKS.md vs progress.md** — check that tasks marked Complete in TASKS.md have corresponding entries in progress.md. Flag completed tasks with no audit trail.
- **README and other docs** — check for stale setup instructions, wrong command examples, or references to removed features.

Only report clear inconsistencies — not style differences or minor wording issues.

Examples:
```
- [ ] **TB-N** **Update CLAUDE.md deployment section** `#housekeeping` — references `hooks/statusline.sh` but file was moved to `scripts/`
- [ ] **TB-N** **Add progress.md entry for TB-15** `#housekeeping` — task marked complete in TASKS.md but no corresponding entry in progress.md
```

## Output format

Output each discovered task as a taskboard-formatted line:

```
- [ ] **TB-N** **<title>** `#housekeeping` — <one-line description>
```

- Use `TB-N` as a placeholder — the caller assigns the real ID from CLAUDE.md `Next task ID`
- Always tag with `#housekeeping`
- Keep titles actionable (imperative verb: "Fix", "Remove", "Update")
- Keep descriptions short — just enough to identify the issue

At the end, output a summary:
```
Found N new housekeeping tasks (L lint, T test, D dead code, C comments, O docs). S skipped (already in Backlog).
```

## Deduplication

Before outputting a task, check if TASKS.md already has a task covering the same issue. Match by:
- Same file + same general issue (e.g., "unused imports in src/models.py" matches existing "Remove unused imports in src/models.py")
- Don't match too broadly — "fix lint errors" doesn't match a specific "fix E401 in store.py"

When in doubt, output the task — a duplicate in Backlog is better than a missed issue.

## Performance

Keep the scan fast. Aim for under 10 tool calls total:
- 1-2 calls to detect tooling
- 1 call per scan category that has tooling
- 1 call to read TASKS.md for dedup
- Parsing is done from command output, not additional tool calls

If a category would require extensive scanning (e.g., dead code in a large codebase), limit to the most obvious issues and move on.
