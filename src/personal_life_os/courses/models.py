from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Any


@dataclass(frozen=True, slots=True)
class CourseSession:
    """A weekly class rule. All concrete occurrences are generated later."""

    weekday: int  # ISO weekday: Monday=1 ... Sunday=7
    start_period: int
    end_period: int
    start_time: time | None = None
    end_time: time | None = None
    weeks: tuple[int, ...] = ()
    location: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.weekday <= 7:
            raise ValueError("weekday must be between 1 and 7")
        if self.start_period < 1 or self.end_period < self.start_period:
            raise ValueError("invalid class period range")
        if any(week < 1 or week > 60 for week in self.weeks):
            raise ValueError("week numbers must be between 1 and 60")
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("start_time and end_time must be provided together")


@dataclass(frozen=True, slots=True)
class Course:
    id: str
    name: str
    teacher: str | None = None
    credits: float | None = None
    semester: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    sessions: tuple[CourseSession, ...] = ()
    source: str = "unknown"
    source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("course id and name are required")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["start_date"] = self.start_date.isoformat() if self.start_date else None
        value["end_date"] = self.end_date.isoformat() if self.end_date else None
        for session, serialized in zip(self.sessions, value["sessions"]):
            serialized["start_time"] = session.start_time.isoformat() if session.start_time else None
            serialized["end_time"] = session.end_time.isoformat() if session.end_time else None
            serialized["weeks"] = list(session.weeks)
        return value

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Course":
        """Build a validated course from the persisted JSON representation."""
        sessions = tuple(
            CourseSession(
                weekday=int(item["weekday"]),
                start_period=int(item["start_period"]),
                end_period=int(item["end_period"]),
                start_time=time.fromisoformat(item["start_time"]) if item.get("start_time") else None,
                end_time=time.fromisoformat(item["end_time"]) if item.get("end_time") else None,
                weeks=tuple(int(week) for week in item.get("weeks", [])),
                location=item.get("location"),
            )
            for item in value.get("sessions", [])
        )
        return cls(
            id=str(value["id"]),
            name=str(value["name"]),
            teacher=value.get("teacher"),
            credits=float(value["credits"]) if value.get("credits") is not None else None,
            semester=value.get("semester"),
            start_date=date.fromisoformat(value["start_date"]) if value.get("start_date") else None,
            end_date=date.fromisoformat(value["end_date"]) if value.get("end_date") else None,
            sessions=sessions,
            source=str(value.get("source", "unknown")),
            source_id=value.get("source_id"),
            metadata=dict(value.get("metadata", {})),
        )


@dataclass(frozen=True, slots=True)
class Reminder:
    course_id: str
    course_name: str
    starts_at: datetime
    remind_at: datetime
    title: str
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ImportResult:
    added: tuple[Course, ...]
    updated: tuple[Course, ...]
    skipped: tuple[str, ...]
