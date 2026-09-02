from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .models import Course


class FinalScheduleStore:
    """JSON-backed final schedule store shared by importers and future agents."""

    schema_version = 1

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> tuple[Course, ...]:
        if not self.path.exists():
            return ()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or payload.get("schema_version") != self.schema_version:
            raise ValueError("unsupported final schedule file")
        courses = payload.get("courses", [])
        if not isinstance(courses, list):
            raise ValueError("courses must be a list")
        return tuple(Course.from_dict(item) for item in courses)

    def save(self, courses: Iterable[Course]) -> None:
        serialized = sorted((course.to_dict() for course in courses), key=lambda item: (item["name"], item["id"]))
        payload = {
            "schema_version": self.schema_version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "courses": serialized,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)
        os.replace(temporary_path, self.path)

    def replace(self, courses: Iterable[Course]) -> tuple[Course, ...]:
        result = tuple(courses)
        self.save(result)
        return result
