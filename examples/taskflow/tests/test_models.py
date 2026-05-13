"""Tests for taskflow.models."""
from taskflow.models import Priority, Status, Task


def test_task_creation():
    t = Task(id="1", title="Test task")
    assert t.title == "Test task"
    assert t.priority == Priority.MEDIUM
    assert t.status == Status.TODO


def test_task_to_dict():
    t = Task(id="1", title="Test", priority=Priority.HIGH, status=Status.DONE)
    d = t.to_dict()
    assert d["id"] == "1"
    assert d["priority"] == "high"
    assert d["status"] == "done"


def test_task_from_dict():
    d = {"id": "1", "title": "Test", "priority": "high", "status": "done"}
    t = Task.from_dict(d)
    assert t.id == "1"
    assert t.priority == Priority.HIGH
    assert t.status == Status.DONE


def test_task_roundtrip():
    t = Task(id="1", title="Test", description="Desc", priority=Priority.CRITICAL, tags=["a", "b"])
    d = t.to_dict()
    t2 = Task.from_dict(d)
    assert t.id == t2.id
    assert t.title == t2.title
    assert t.priority == t2.priority
    assert t.tags == t2.tags
