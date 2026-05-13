"""Tests for taskflow.validators."""
from datetime import date, timedelta

from taskflow.validators import validate_due_date, validate_priority, validate_title


def test_validate_title_valid():
    assert validate_title("Buy groceries") is True


def test_validate_title_empty():
    assert validate_title("") is False


def test_validate_title_blank():
    assert validate_title("   ") is False


def test_validate_title_too_long():
    assert validate_title("x" * 201) is False


def test_validate_title_max_length():
    assert validate_title("x" * 200) is True


def test_validate_due_date_future():
    future = (date.today() + timedelta(days=7)).isoformat()
    assert validate_due_date(future) is True


def test_validate_due_date_today():
    assert validate_due_date(date.today().isoformat()) is True


def test_validate_due_date_past():
    past = (date.today() - timedelta(days=1)).isoformat()
    assert validate_due_date(past) is False


def test_validate_due_date_invalid_format():
    assert validate_due_date("not-a-date") is False


def test_validate_due_date_none():
    """None means no due date — should return True, not crash."""
    assert validate_due_date(None) is True


def test_validate_priority_valid():
    assert validate_priority("low") is True
    assert validate_priority("critical") is True


def test_validate_priority_invalid():
    assert validate_priority("urgent") is False
