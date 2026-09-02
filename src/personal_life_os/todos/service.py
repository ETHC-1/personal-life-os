from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .models import TodoItem, TodoPriority
from .storage import TodoStore


class TodoService:
    def __init__(self, store: TodoStore) -> None:
        self.store = store

    def create(self, *, title: str, priority: TodoPriority = TodoPriority.MEDIUM,
               due_at: datetime | None = None, description: str = "", todo_id: str | None = None) -> TodoItem:
        try:
            priority = TodoPriority(priority)
        except ValueError as exc:
            raise ValueError("待办优先级必须是 low、medium 或 high") from exc
        item = TodoItem(todo_id or str(uuid4()), title.strip(), priority, due_at, description.strip())
        items = self.store.load()
        if any(existing.id == item.id for existing in items):
            raise ValueError("待办 id 已存在")
        self.store.save((*items, item))
        return item

    def set_completed(self, todo_id: str, completed: bool) -> TodoItem | None:
        items = self.store.load()
        target = next((item for item in items if item.id == todo_id), None)
        if target is None:
            return None
        completed_at = datetime.now(timezone.utc) if completed else None
        updated = TodoItem(target.id, target.title, target.priority, target.due_at, target.description, completed, completed_at)
        self.store.save((updated, *[item for item in items if item.id != todo_id]))
        return updated

    def delete(self, todo_id: str) -> bool:
        items = self.store.load()
        remaining = tuple(item for item in items if item.id != todo_id)
        if len(remaining) == len(items):
            return False
        self.store.save(remaining)
        return True

    def update(self, todo_id: str, *, title: str, priority: TodoPriority,
               due_at: datetime | None = None, description: str = "") -> TodoItem | None:
        try:
            priority = TodoPriority(priority)
        except ValueError as exc:
            raise ValueError("待办优先级必须是 low、medium 或 high") from exc
        items = self.store.load()
        target = next((item for item in items if item.id == todo_id), None)
        if target is None:
            return None
        updated = TodoItem(target.id, title.strip(), priority, due_at, description.strip(), target.completed, target.completed_at)
        self.store.save((updated, *[item for item in items if item.id != todo_id]))
        return updated
