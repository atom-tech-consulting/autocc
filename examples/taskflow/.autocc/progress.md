# Progress

## [2026-03-30] TB-1: Fix delete persistence bug
- **Result:** complete
- **Summary:** Added `self._save()` call after `self._tasks.pop(i)` in `TaskStore.delete()`. Deletions now persist to disk.
- **Files:** `src/taskflow/store.py`
- **Verified:** `test_store.py::test_delete_persists` passes

## [2026-03-30] TB-2: Fix status filter bug
- **Result:** complete
- **Summary:** Changed `t.status == status` to `t.status.value == status` in `TaskStore.list()`. Status filtering now works correctly.
- **Files:** `src/taskflow/store.py`
- **Verified:** `test_store.py::test_list_by_status` passes
