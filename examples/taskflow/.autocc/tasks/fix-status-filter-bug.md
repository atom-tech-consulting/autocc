# Fix status filter bug

## Objective
Fix `TaskStore.list(status=...)` to compare against `Status` enum value instead of raw string.

## Context
Bug in store.py line 38: `t.status == status` compares a Status enum against a string, so it never matches. Need to convert string to Status enum or compare against `.value`.

## Files
- `src/taskflow/store.py` — line 38, fix the comparison
- `tests/test_store.py::test_list_by_status` — verification test

## Approach
1. Change `t.status == status` to `t.status == Status(status)` or `t.status.value == status`
2. Run verification test

## Verification
- `uv run pytest tests/test_store.py::test_list_by_status -v`

## Tags
#bugfix
