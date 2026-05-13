# Fix due_date validator crash on None

## Objective
Fix `validate_due_date()` to handle `None` input by returning `True` (None means no due date).

## Context
Bug in validators.py line 18: `date_str.strip()` crashes with AttributeError when `date_str` is None.

## Files
- `src/taskflow/validators.py` — line 14-20, add None check before `.strip()`
- `tests/test_validators.py::test_validate_due_date_none` — verification test

## Approach
1. Add `if date_str is None: return True` at the start of `validate_due_date()`
2. Run verification test

## Verification
- `uv run pytest tests/test_validators.py::test_validate_due_date_none -v`

## Tags
#bugfix
