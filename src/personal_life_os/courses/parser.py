from __future__ import annotations

import re
from datetime import date, time
from html.parser import HTMLParser
from typing import Iterable

from .models import Course, CourseSession

_ALIASES = {
    "name": {"课程", "课程名称", "course", "course name"},
    "teacher": {"教师", "老师", "任课教师", "teacher", "instructor"},
    "location": {"地点", "教室", "上课地点", "location", "room"},
    "weekday": {"星期", "周几", "上课星期", "weekday", "day"},
    "period": {"节次", "上课节次", "时间", "period", "periods"},
    "weeks": {"周次", "上课周次", "weeks", "week"},
    "credits": {"学分", "credits", "credit"},
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row:
            self.rows.append(self._row)
            self._row = None


def _field(header: str) -> str | None:
    normalized = header.strip().lower()
    for name, aliases in _ALIASES.items():
        if normalized in aliases:
            return name
    return None


def _weekday(value: str) -> int:
    match = re.search(r"(?:星期|周)\s*([一二三四五六日天1-7])|\b(mon|tue|wed|thu|fri|sat|sun)", value.lower())
    if not match:
        raise ValueError(f"cannot parse weekday: {value}")
    token = next(part for part in match.groups() if part)
    return {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
            "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
            "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6, "sun": 7}[token]


def _period(value: str) -> tuple[int, int]:
    numbers = [int(item) for item in re.findall(r"\d+", value)]
    if len(numbers) < 1:
        raise ValueError(f"cannot parse period: {value}")
    return numbers[0], numbers[1] if len(numbers) > 1 else numbers[0]


def _weeks(value: str) -> tuple[int, ...]:
    result: set[int] = set()
    for part in re.split(r"[,，、;；\s]+", value):
        match = re.fullmatch(r"(\d+)\s*[-~至]\s*(\d+)", part)
        if match:
            result.update(range(int(match.group(1)), int(match.group(2)) + 1))
        elif part.isdigit():
            result.add(int(part))
    return tuple(sorted(result))


def parse_course_table(html: str, *, source: str = "html", period_times: dict[int, tuple[time, time]] | None = None) -> list[Course]:
    """Parse a table whose headers use common Chinese or English course labels."""
    parser = _TableParser()
    parser.feed(html)
    if len(parser.rows) < 2:
        return []
    headers = [_field(cell) for cell in parser.rows[0]]
    required = {"name", "weekday", "period"}
    if not required.issubset(set(headers)):
        raise ValueError("course table must contain name, weekday and period columns")
    courses: list[Course] = []
    for index, row in enumerate(parser.rows[1:], start=1):
        values = {key: row[pos] for pos, key in enumerate(headers) if key and pos < len(row) and row[pos]}
        if not values.get("name"):
            continue
        start_period, end_period = _period(values["period"])
        start_time = period_times.get(start_period, (None, None))[0] if period_times else None
        end_time = period_times.get(end_period, (None, None))[1] if period_times else None
        session = CourseSession(
            weekday=_weekday(values["weekday"]),
            start_period=start_period,
            end_period=end_period,
            start_time=start_time,
            end_time=end_time,
            weeks=_weeks(values.get("weeks", "")),
            location=values.get("location"),
        )
        credits = float(values["credits"]) if values.get("credits") and re.fullmatch(r"\d+(?:\.\d+)?", values["credits"]) else None
        courses.append(Course(id=f"{source}:{index}", name=values["name"], teacher=values.get("teacher"), credits=credits,
                              sessions=(session,), source=source, source_id=str(index), metadata={"raw": values}))
    return courses
