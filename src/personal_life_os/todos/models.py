from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class TodoPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True, slots=True)
class TodoItem:
    id: str
    title: str
    priority: TodoPriority = TodoPriority.MEDIUM
    due_at: datetime | None = None
    description: str = ""
    completed: bool = False
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise ValueError("待办 id 和标题不能为空")
        if len(self.title) > 200:
            raise ValueError("待办标题不能超过 200 个字符")
        if self.due_at is not None and (self.due_at.tzinfo is None or self.due_at.utcoffset() is None):
            raise ValueError("截止时间必须包含时区")
        if self.completed_at is not None and (self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None):
            raise ValueError("完成时间必须包含时区")
        if self.completed != (self.completed_at is not None):
            raise ValueError("completed 和 completed_at 状态不一致")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "priority": self.priority.value,
                "due_at": self.due_at.isoformat() if self.due_at else None,
                "description": self.description, "completed": self.completed,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TodoItem":
        if not isinstance(value, dict):
            raise ValueError("待办必须是对象")
        def parse(value: Any) -> datetime | None:
            if value is None:
                return None
            try:
                result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("待办时间格式无效") from exc
            if result.tzinfo is None or result.utcoffset() is None:
                raise ValueError("待办时间必须包含时区")
            return result
        try:
            priority = TodoPriority(str(value.get("priority", TodoPriority.MEDIUM)))
        except ValueError as exc:
            raise ValueError("待办优先级必须是 low、medium 或 high") from exc
        completed_value = value.get("completed", False)
        if not isinstance(completed_value, bool):
            raise ValueError("completed 必须是布尔值")
        completed = completed_value
        return cls(str(value["id"]), str(value["title"]), priority, parse(value.get("due_at")),
                   str(value.get("description", "")), completed, parse(value.get("completed_at")))
