from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .models import CalendarEvent


class CalendarStore:
    schema_version = 1

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)

    def load(self) -> tuple[CalendarEvent, ...]:
        if not self.path.exists():
            return ()
        with self.path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict) or payload.get("schema_version") != self.schema_version:
            raise ValueError("unsupported calendar file")
        events = payload.get("events", [])
        if not isinstance(events, list):
            raise ValueError("events must be a list")
        return tuple(CalendarEvent.from_dict(item) for item in events)

    def save(self, events: Iterable[CalendarEvent]) -> tuple[CalendarEvent, ...]:
        result = tuple(sorted(events, key=lambda event: (event.starts_at, event.id)))
        payload = {
            "schema_version": self.schema_version,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "events": [event.to_dict() for event in result],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False, suffix=".tmp") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            temporary_path = Path(handle.name)
        os.replace(temporary_path, self.path)
        return result
