from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError("时间必须是有效的 ISO 8601 日期时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return parsed


@dataclass(frozen=True, slots=True)
class CalendarEvent:
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    description: str = ""
    location: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    recurrence_rule: str | None = None
    recurrence_until: date | None = None
    reminder_minutes: int | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.title.strip():
            raise ValueError("事件 id 和标题不能为空")
        for value, label in ((self.starts_at, "starts_at"), (self.ends_at, "ends_at")):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{label} 必须包含时区")
        if self.ends_at <= self.starts_at:
            raise ValueError("结束时间必须晚于开始时间")
        if self.recurrence_rule not in {None, "daily", "weekly", "weekdays"}:
            raise ValueError("重复规则必须是 daily、weekly、weekdays 或为空")
        if self.recurrence_rule and self.recurrence_until is None:
            raise ValueError("重复日程必须设置结束日期")
        if self.recurrence_until and self.recurrence_until < self.starts_at.date():
            raise ValueError("重复结束日期不能早于开始日期")
        if self.reminder_minutes is not None and not 0 <= self.reminder_minutes <= 10080:
            raise ValueError("提醒时间必须在 0 到 10080 分钟之间")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "description": self.description,
            "location": self.location,
            "metadata": self.metadata,
            "recurrence_rule": self.recurrence_rule,
            "recurrence_until": self.recurrence_until.isoformat() if self.recurrence_until else None,
            "reminder_minutes": self.reminder_minutes,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CalendarEvent":
        if not isinstance(value, dict):
            raise ValueError("日历事件必须是对象")
        recurrence_until = date.fromisoformat(value["recurrence_until"]) if value.get("recurrence_until") else None
        return cls(
            id=str(value["id"]),
            title=str(value["title"]),
            starts_at=_parse_datetime(value["starts_at"]),
            ends_at=_parse_datetime(value["ends_at"]),
            description=str(value.get("description", "")),
            location=value.get("location"),
            metadata=dict(value.get("metadata", {})),
            recurrence_rule=value.get("recurrence_rule"),
            recurrence_until=recurrence_until,
            reminder_minutes=int(value["reminder_minutes"]) if value.get("reminder_minutes") is not None else None,
        )

    def occurrences_between(self, starts_at: datetime, ends_at: datetime) -> tuple["CalendarEvent", ...]:
        """Expand the small supported recurrence set into displayable occurrences."""
        if self.recurrence_rule is None:
            return (self,) if self.starts_at < ends_at and self.ends_at > starts_at else ()
        duration = self.ends_at - self.starts_at
        cursor = self.starts_at
        result = []
        while cursor.date() <= self.recurrence_until and cursor < ends_at:
            allowed = self.recurrence_rule == "daily" or (self.recurrence_rule == "weekly" and cursor.weekday() == self.starts_at.weekday()) or (self.recurrence_rule == "weekdays" and cursor.weekday() < 5)
            if allowed and cursor + duration > starts_at:
                result.append(CalendarEvent(self.id, self.title, cursor, cursor + duration, self.description, self.location, self.metadata, self.recurrence_rule, self.recurrence_until, self.reminder_minutes))
            cursor += timedelta(days=1)
        return tuple(result)
