from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .models import TodoItem


class TodoStore:
    schema_version = 1

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> tuple[TodoItem, ...]:
        if not self.path.exists():
            return ()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or payload.get("schema_version") != self.schema_version:
            raise ValueError("unsupported todo file")
        items = payload.get("todos", [])
        if not isinstance(items, list):
            raise ValueError("todos must be a list")
        return tuple(TodoItem.from_dict(item) for item in items)

    def save(self, items: Iterable[TodoItem]) -> tuple[TodoItem, ...]:
        result = tuple(sorted(items, key=lambda item: (item.completed, item.due_at is None, item.due_at or datetime.max.replace(tzinfo=timezone.utc), item.id)))
        payload = {"schema_version": self.schema_version, "updated_at": datetime.now(timezone.utc).isoformat(), "todos": [item.to_dict() for item in result]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)
        os.replace(temporary_path, self.path)
        return result
