from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from .models import CalendarEvent
from .storage import CalendarStore


class EventConflictError(ValueError):
    """Raised when two calendar events overlap."""


class CalendarService:
    def __init__(self, store: CalendarStore) -> None:
        self.store = store

    def list_between(self, starts_at: datetime, ends_at: datetime) -> tuple[CalendarEvent, ...]:
        self._ensure_aware_range(starts_at, ends_at)
        if ends_at <= starts_at:
            raise ValueError("查询结束时间必须晚于开始时间")
        return tuple(occurrence for event in self.store.load() for occurrence in event.occurrences_between(starts_at, ends_at))

    def create(self, *, title: str, starts_at: datetime, ends_at: datetime, description: str = "",
               location: str | None = None, event_id: str | None = None,
               metadata: dict | None = None, recurrence_rule: str | None = None,
               recurrence_until=None, reminder_minutes: int | None = None) -> CalendarEvent:
        event = CalendarEvent(event_id or str(uuid4()), title, starts_at, ends_at, description, location, metadata or {}, recurrence_rule, recurrence_until, reminder_minutes)
        events = self.store.load()
        check_start = min((existing.starts_at for existing in events), default=event.starts_at)
        check_end = max((existing.recurrence_until and datetime.combine(existing.recurrence_until, datetime.max.time(), existing.starts_at.tzinfo) or existing.ends_at for existing in events), default=event.ends_at)
        conflicts = [existing.id for existing in events for left in event.occurrences_between(check_start, check_end + timedelta(days=1)) for right in existing.occurrences_between(check_start, check_end + timedelta(days=1)) if left.starts_at < right.ends_at and left.ends_at > right.starts_at]
        if conflicts:
            raise EventConflictError(f"事件时间冲突：{', '.join(conflicts)}")
        self.store.save((*events, event))
        return event

    def delete(self, event_id: str) -> bool:
        events = self.store.load()
        remaining = tuple(event for event in events if event.id != event_id)
        if len(remaining) == len(events):
            return False
        self.store.save(remaining)
        return True

    def update(self, event_id: str, *, title: str, starts_at: datetime, ends_at: datetime,
               description: str = "", location: str | None = None, recurrence_rule: str | None = None,
               recurrence_until=None, reminder_minutes: int | None = None) -> CalendarEvent | None:
        events = self.store.load()
        if not any(event.id == event_id for event in events):
            return None
        updated = CalendarEvent(event_id, title.strip(), starts_at, ends_at, description.strip(), location, {}, recurrence_rule, recurrence_until, reminder_minutes)
        conflicts = [event.id for event in events if event.id != event_id for left in updated.occurrences_between(starts_at, updated.recurrence_until and datetime.combine(updated.recurrence_until, datetime.max.time(), starts_at.tzinfo) or updated.ends_at) for right in event.occurrences_between(starts_at, updated.recurrence_until and datetime.combine(updated.recurrence_until, datetime.max.time(), starts_at.tzinfo) or updated.ends_at) if left.starts_at < right.ends_at and left.ends_at > right.starts_at]
        if conflicts:
            raise EventConflictError(f"事件时间冲突：{', '.join(conflicts)}")
        self.store.save((updated, *[event for event in events if event.id != event_id]))
        return updated

    @staticmethod
    def _ensure_aware_range(starts_at: datetime, ends_at: datetime) -> None:
        if any(value.tzinfo is None or value.utcoffset() is None for value in (starts_at, ends_at)):
            raise ValueError("查询时间必须包含时区")
