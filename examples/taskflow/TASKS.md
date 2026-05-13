# Tasks

## Active

## Ready
- [ ] **TB-3** **Fix due_date validator crash on None** `#bugfix` — `validate_due_date(None)` raises `AttributeError` instead of returning `True`. Verify `test_validators.py::test_validate_due_date_none` passes. [→ brief](.autocc/tasks/fix-due-date-validator-crash.md)

## Backlog

- [ ] **TB-4** **Implement CSV export** `#feature` — `format_csv()` in `formatters.py` raises `NotImplementedError`. Implement using `csv` stdlib. Remove `@pytest.mark.xfail` from `test_formatters.py::test_format_csv`.
- [ ] **TB-5** **Add search functionality tests** `#testing` — `TaskStore.search(query)` exists but has no tests. Add `test_search_by_title` and `test_search_by_description` to `test_store.py`.

## Complete

- [x] **TB-1** **Fix delete persistence bug** `#bugfix` — `TaskStore.delete()` does not call `_save()` after removing a task. [→ brief](.autocc/tasks/fix-delete-persistence-bug.md)
- [x] **TB-2** **Fix status filter bug** `#bugfix` — Compare against Status enum .value instead of raw string. [→ brief](.autocc/tasks/fix-status-filter-bug.md)

## Frozen
