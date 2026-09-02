from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Iterable, Protocol

from .models import Course, ImportResult, Reminder


class CourseSource(Protocol):
    """Integration boundary for a school portal, API, file or test fixture."""

    name: str

    def fetch_courses(self) -> Iterable[Course]: ...


class CourseCatalog:
    def __init__(self, courses: Iterable[Course] = ()) -> None:
        self._courses: dict[str, Course] = {course.id: course for course in courses}

    def import_from(self, source: CourseSource) -> ImportResult:
        added: list[Course] = []
        updated: list[Course] = []
        skipped: list[str] = []
        for course in source.fetch_courses():
            if course.source != source.name:
                course = replace(course, source=source.name)
            old = self._courses.get(course.id)
            if old == course:
                skipped.append(course.id)
            elif old is None:
                self._courses[course.id] = course
                added.append(course)
            else:
                self._courses[course.id] = course
                updated.append(course)
        return ImportResult(tuple(added), tuple(updated), tuple(skipped))

    def all(self) -> tuple[Course, ...]:
        return tuple(self._courses.values())

    def reminders_between(self, start: datetime, end: datetime, *, minutes_before: int = 30) -> list[Reminder]:
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError("start and end must be timezone-aware")
        if end < start or minutes_before < 0:
            raise ValueError("invalid reminder range")
        reminders: list[Reminder] = []
        cursor = start.date()
        while cursor <= end.date():
            for course in self._courses.values():
                if not course.start_date or not course.end_date or not (course.start_date <= cursor <= course.end_date):
                    continue
                semester_week_start = course.start_date - timedelta(days=course.start_date.isoweekday() - 1)
                for session in course.sessions:
                    week_number = ((cursor - semester_week_start).days // 7) + 1
                    if cursor.isoweekday() != session.weekday or (session.weeks and week_number not in session.weeks):
                        continue
                    if not session.start_time:
                        continue
                    starts_at = datetime.combine(cursor, session.start_time, tzinfo=start.tzinfo)
                    if start <= starts_at <= end:
                        reminders.append(Reminder(course.id, course.name, starts_at, starts_at - timedelta(minutes=minutes_before),
                                                  f"即将开始：{course.name}", session.location))
            cursor += timedelta(days=1)
        return sorted(reminders, key=lambda item: item.starts_at)
