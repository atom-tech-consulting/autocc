"""Tests for taskflow.store."""
from taskflow.models import Status, Task
from taskflow.store import TaskStore


def test_add_and_get(store):
    t = Task(id="1", title="Test task")
    store.add(t)
    result = store.get("1")
    assert result is not None
    assert result.title == "Test task"


def test_add_persists(store):
    t = Task(id="1", title="Persistent task")
    store.add(t)
    # Reload from disk
    store2 = TaskStore(store._path)
    assert store2.get("1") is not None
    assert store2.get("1").title == "Persistent task"


def test_list_all(store, sample_tasks):
    result = store.list()
    assert len(result) == 3


def test_list_by_status(store, sample_tasks):
    """Filter tasks by status string — should match enum values."""
    result = store.list(status="done")
    assert len(result) == 1
    assert result[0].id == "t3"


def test_list_by_priority(store, sample_tasks):
    result = store.list(priority="critical")
    assert len(result) == 1
    assert result[0].id == "t2"


def test_update(store, sample_tasks):
    store.update("t1", status=Status.IN_PROGRESS)
    t = store.get("t1")
    assert t.status == Status.IN_PROGRESS


def test_delete(store, sample_tasks):
    assert store.delete("t1") is True
    assert store.get("t1") is None


def test_delete_persists(store, sample_tasks):
    """After deleting, task must not reappear on reload."""
    store.delete("t1")
    # Reload from disk
    store2 = TaskStore(store._path)
    assert store2.get("t1") is None, "Deleted task reappeared after reload"


def test_delete_nonexistent(store):
    assert store.delete("missing") is False
