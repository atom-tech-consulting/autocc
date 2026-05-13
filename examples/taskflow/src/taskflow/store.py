"""JSON file-based task storage."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .models import Task, Status  # noqa: F401 (Status used after bug fix)


class TaskStore:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._tasks: list[Task] = []
        if self._path.exists():
            self._load()

    def _load(self) -> None:
        data = json.loads(self._path.read_text())
        self._tasks = [Task.from_dict(t) for t in data]

    def _save(self) -> None:
        self._path.write_text(json.dumps([t.to_dict() for t in self._tasks], indent=2))

    def add(self, task: Task) -> Task:
        self._tasks.append(task)
        self._save()
        return task

    def get(self, task_id: str) -> Optional[Task]:
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def list(self, status: Optional[str] = None, priority: Optional[str] = None) -> list[Task]:
        result = self._tasks
        if status:
            result = [t for t in result if t.status.value == status]
        if priority:
            result = [t for t in result if t.priority.value == priority]
        return result

    def update(self, task_id: str, **kwargs) -> Optional[Task]:
        task = self.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        self._save()
        return task

    def delete(self, task_id: str) -> bool:
        for i, task in enumerate(self._tasks):
            if task.id == task_id:
                self._tasks.pop(i)
                self._save()
                return True
        return False

    def search(self, query: str) -> list[Task]:
        query_lower = query.lower()
        return [
            t for t in self._tasks
            if query_lower in t.title.lower() or query_lower in t.description.lower()
        ]
