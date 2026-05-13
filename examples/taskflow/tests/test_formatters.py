"""Tests for taskflow.formatters."""
import json

import pytest

from taskflow.formatters import format_csv, format_json, format_table
from taskflow.models import Priority, Status, Task


@pytest.fixture
def tasks():
    return [
        Task(
            id="1", title="Task A",
            priority=Priority.HIGH, status=Status.TODO,
            due_date="2026-12-01",
        ),
        Task(
            id="2", title="Task B",
            priority=Priority.LOW, status=Status.DONE,
            due_date=None,
        ),
    ]


def test_format_table(tasks):
    output = format_table(tasks)
    assert "Task A" in output
    assert "Task B" in output
    assert "high" in output


def test_format_table_empty():
    assert format_table([]) == "No tasks found."


def test_format_json(tasks):
    output = format_json(tasks)
    parsed = json.loads(output)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "1"


@pytest.mark.xfail(reason="CSV export not yet implemented")
def test_format_csv(tasks):
    output = format_csv(tasks)
    lines = output.strip().split("\n")
    assert len(lines) == 3  # header + 2 rows
    assert "id" in lines[0]
    assert "Task A" in lines[1]
