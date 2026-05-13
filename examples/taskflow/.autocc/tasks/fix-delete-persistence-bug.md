# Fix delete persistence bug

## Objective
Add `self._save()` call after `self._tasks.pop(i)` in `TaskStore.delete()` so deletions persist to disk.

## Context
Bug in store.py line 57: delete removes from memory but never writes to disk. The deleted task reappears on next load.

## Files
- `src/taskflow/store.py` — line 57, add `self._save()` after the pop
- `tests/test_store.py::test_delete_persists` — verification test

## Approach
1. Add `self._save()` after `self._tasks.pop(i)` on line 57 of store.py
2. Run verification test

## Verification
- `uv run pytest tests/test_store.py::test_delete_persists -v`

## Tags
#bugfix
