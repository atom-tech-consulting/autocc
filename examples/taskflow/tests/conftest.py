"""Shared fixtures for taskflow tests."""
import pytest

from taskflow.models import Priority, Status, Task
from taskflow.store import TaskStore


@pytest.fixture
def store(tmp_path):
    return TaskStore(tmp_path / "tasks.json")


@pytest.fixture
def sample_tasks(store):
    tasks = [
        Task(
            id="t1", title="Write docs",
            description="Write API documentation",
            priority=Priority.HIGH, status=Status.TODO,
        ),
        Task(
            id="t2", title="Fix login bug",
            description="Users cannot login with email",
            priority=Priority.CRITICAL, status=Status.IN_PROGRESS,
        ),
        Task(
            id="t3", title="Add tests",
            description="Add unit tests for models",
            priority=Priority.MEDIUM, status=Status.DONE,
        ),
    ]
    for t in tasks:
        store.add(t)
    return tasks
