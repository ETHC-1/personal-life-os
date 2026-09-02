from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path
from typing import Any

from .models import Course, CourseSession
from .parser import parse_course_table


def _school_course(row: dict[str, Any], *, index: int, semester: str | None) -> Course:
    """Convert one Hebei Medical University schedule API row without retaining raw PII."""
    weekday = int(row["xq"])
    start_period = int(row.get("ps") or row.get("pe"))
    end_period = int(row.get("pe") or row.get("ps"))
    weeks = tuple(sorted({int(item) for item in str(row.get("zc", "")).replace("，", ",").split(",") if item.strip().isdigit()}))
    start_time = time.fromisoformat(row["qssj"]) if row.get("qssj") else None
    end_time = time.fromisoformat(row["jssj"]) if row.get("jssj") else None
    course_code = str(row.get("kcrwdm") or row.get("kcdm") or index)
    return Course(
        id=f"hebmu:{semester or 'unknown'}:{course_code}",
        name=str(row["kcmc"]),
        teacher=row.get("teaxms") or row.get("pkr"),
        semester=semester,
        sessions=(CourseSession(weekday, start_period, end_period, start_time, end_time, weeks, row.get("jxcdmc")),),
        source="hebmu_jw",
        source_id=course_code,
        metadata={"imported_from": "getCalendarWeekDatas"},
    )


def parse_schedule_json(payload: dict[str, Any], *, source: str = "file", semester: str | None = None) -> list[Course]:
    if isinstance(payload.get("courses"), list):
        return [Course.from_dict(item) for item in payload["courses"]]
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("schedule JSON must contain a courses or data list")
    if payload.get("code") not in (None, 0):
        raise ValueError(f"schedule API returned code {payload['code']}")
    if rows and all(isinstance(row, dict) and "kcmc" in row for row in rows):
        return [_school_course(row, index=index, semester=semester) for index, row in enumerate(rows, 1)]
    return [Course.from_dict(item) for item in rows]


def import_schedule_file(path: str | Path, *, source: str = "file", semester: str | None = None) -> list[Course]:
    """Import JSON or HTML into validated Course objects."""
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("schedule JSON root must be an object")
        courses = parse_schedule_json(payload, source=source, semester=semester)
    elif suffix in {".html", ".htm"}:
        courses = parse_course_table(file_path.read_text(encoding="utf-8"), source=source)
    else:
        raise ValueError("supported schedule files are .json, .html and .htm")
    if not courses:
        raise ValueError("no courses found in schedule file")
    return courses
