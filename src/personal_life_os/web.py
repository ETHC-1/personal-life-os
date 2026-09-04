from __future__ import annotations

import argparse
import json
import mimetypes
import os
import tempfile
from datetime import date, datetime, time, timedelta
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from .calendar import CalendarService, CalendarStore
from .courses.models import Course
from .courses.importers import import_schedule_file
from .courses.school import (
    HebmuBrowserImporter,
    extract_classroom_names,
    extract_classroom_usage,
    fetch_courses_and_classroom_usage,
)
from .courses.storage import FinalScheduleStore
from .courses.periods import periods_payload
from .system_time import read_system_time
from .todos import TodoItem, TodoPriority, TodoService, TodoStore


WEB_ROOT = Path(__file__).resolve().parent / "web"


def _store_path() -> Path:
    configured = os.environ.get("PERSONAL_LIFE_OS_SCHEDULE_PATH")
    return Path(configured) if configured else Path.home() / ".personal-life-os" / "final_schedule.json"


def _empty_room_path() -> Path:
    configured = os.environ.get("PERSONAL_LIFE_OS_EMPTY_ROOM_PATH")
    return Path(configured) if configured else Path.home() / ".personal-life-os" / "empty-rooms.json"


def _calendar_path() -> Path:
    configured = os.environ.get("PERSONAL_LIFE_OS_CALENDAR_PATH")
    return Path(configured) if configured else Path.home() / ".personal-life-os" / "calendar.json"


def _todo_path() -> Path:
    configured = os.environ.get("PERSONAL_LIFE_OS_TODO_PATH")
    return Path(configured) if configured else Path.home() / ".personal-life-os" / "todos.json"


def _parse_aware_datetime(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是有效的 ISO 8601 日期时间") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} 必须包含时区")
    return parsed


def _parse_optional_date(value: object, field: str):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"{field} 必须是有效的日期") from exc


def _calendar_payload(calendar_path: Path, query: dict[str, list[str]]) -> dict:
    service = CalendarService(CalendarStore(calendar_path))
    current = read_system_time(query.get("timezone", [None])[0])
    day = current["now"][:10]
    zone = ZoneInfo(current["timezone"])
    default_start = datetime.combine(date.fromisoformat(day), time.min, tzinfo=zone).isoformat()
    default_end = datetime.combine(date.fromisoformat(day), time.max, tzinfo=zone).isoformat()
    starts_at = _parse_aware_datetime(query.get("start", [default_start])[0], "start")
    ends_at = _parse_aware_datetime(query.get("end", [default_end])[0], "end")
    events = service.list_between(starts_at, ends_at)
    return {"events": [event.to_dict() for event in events], "start": starts_at.isoformat(), "end": ends_at.isoformat(), "store_path": str(calendar_path)}


def _todo_payload(todo_path: Path, query: dict[str, list[str]]) -> dict:
    items = TodoStore(todo_path).load()
    completed = query.get("completed", [None])[0]
    if completed in {"true", "false"}:
        items = tuple(item for item in items if item.completed == (completed == "true"))
    return {"todos": [item.to_dict() for item in items], "store_path": str(todo_path)}


def _overview_payload(calendar_path: Path, todo_path: Path, timezone_name: str | None = None) -> dict:
    current = read_system_time(timezone_name)
    zone = ZoneInfo(current["timezone"])
    today = date.fromisoformat(current["now"][:10])
    starts_at = datetime.combine(today, time.min, tzinfo=zone)
    ends_at = datetime.combine(today, time.max, tzinfo=zone)
    calendar_events = CalendarService(CalendarStore(calendar_path)).list_between(starts_at, ends_at)
    todos = TodoStore(todo_path).load()
    due_today = tuple(item for item in todos if not item.completed and item.due_at and item.due_at.astimezone(zone).date() == today)
    return {"system_time": current, "date": today.isoformat(), "calendar_events": [event.to_dict() for event in calendar_events],
            "todos_due_today": [item.to_dict() for item in due_today], "todo_open_count": sum(not item.completed for item in todos),
            "todo_total_count": len(todos)}


def _reminder_payload(calendar_path: Path, query: dict[str, list[str]]) -> dict:
    current = read_system_time(query.get("timezone", [None])[0])
    now = _parse_aware_datetime(current["now"], "now")
    starts_at = _parse_aware_datetime(query.get("start", [now.isoformat()])[0], "start")
    ends_at = _parse_aware_datetime(query.get("end", [(now + timedelta(days=1)).isoformat()])[0], "end")
    events = CalendarService(CalendarStore(calendar_path)).list_between(starts_at, ends_at)
    reminders = []
    for event in events:
        if event.reminder_minutes is None:
            continue
        reminder_at = event.starts_at - timedelta(minutes=event.reminder_minutes)
        if starts_at <= reminder_at < ends_at:
            reminders.append({"event_id": event.id, "title": event.title, "starts_at": event.starts_at.isoformat(), "remind_at": reminder_at.isoformat(), "minutes_before": event.reminder_minutes, "location": event.location})
    return {"reminders": reminders, "start": starts_at.isoformat(), "end": ends_at.isoformat()}


def _empty_room_payload(path: Path) -> dict:
    """Read the bridge's sanitized snapshot without exposing raw proxy data."""
    if not path.exists():
        return {"classroom_usage_by_date": {}, "updated_at": None, "building": None, "status": "waiting"}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("空教室快照格式无效")

    def safe_usage(items: object) -> list[dict]:
        if not isinstance(items, list):
            return []
        sanitized = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("room"), str):
                continue
            room = item["room"].strip()
            periods = item.get("occupied_periods", [])
            if not room or not isinstance(periods, list):
                continue
            sanitized.append({
                "room": room,
                "occupied_periods": sorted(set(
                    period for period in periods
                    if isinstance(period, int) and not isinstance(period, bool) and 1 <= period <= 13
                )),
            })
        return sanitized

    if isinstance(payload.get("buildings"), list):
        buildings = []
        for item in payload["buildings"]:
            if not isinstance(item, dict) or not isinstance(item.get("days"), list):
                continue
            by_date = {}
            for day in item["days"]:
                if isinstance(day, dict) and day.get("date") and isinstance(day.get("usage"), list):
                    rooms = [str(room).strip() for room in day.get("rooms", []) if isinstance(room, str) and room.strip()]
                    by_date[date.fromisoformat(str(day["date"])).isoformat()] = {"rooms": rooms, "usage": safe_usage(day["usage"])}
            if by_date:
                buildings.append({"campus": str(item.get("campus") or ""), "building": str(item.get("building") or ""), "building_code": str(item.get("building_code") or ""), "classroom_usage_by_date": by_date})
        return {"buildings": buildings, "updated_at": payload.get("updated_at"), "status": "ready" if buildings else "waiting"}

    query_date = str(payload.get("date", "")).strip()
    usage = payload.get("usage", [])
    if not query_date and isinstance(payload.get("days"), list):
        by_date = {}
        for day in payload["days"]:
            if isinstance(day, dict) and day.get("date") and isinstance(day.get("usage"), list):
                day_date = date.fromisoformat(str(day["date"]))
                by_date[day_date.isoformat()] = {"rooms": [], "usage": safe_usage(day["usage"])}
        return {
            "classroom_usage_by_date": by_date,
            "updated_at": payload.get("updated_at") or payload.get("generated_at"),
            "building": payload.get("building") or payload.get("building_name"),
            "status": "ready" if by_date else "waiting",
        }
    if not query_date or not isinstance(usage, list):
        raise ValueError("空教室快照缺少日期或使用记录")
    query_date = date.fromisoformat(query_date).isoformat()
    return {
        "classroom_usage_by_date": {query_date: {"rooms": [], "usage": safe_usage(usage)}},
        "updated_at": payload.get("updated_at"),
        "building": payload.get("building"),
        "status": "ready",
    }


def _demo_courses() -> tuple[Course, ...]:
    """Small fixture used when no local schedule exists, so the UI is easy to preview."""
    from .courses.models import CourseSession

    return (
        Course(
            id="demo:math",
            name="高等数学",
            teacher="张老师",
            credits=4,
            semester="202601",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            sessions=(CourseSession(1, 1, 2, time(8, 0), time(9, 40), tuple(range(1, 17)), "A101"),),
            source="demo",
        ),
        Course(
            id="demo:english",
            name="大学英语",
            teacher="李老师",
            credits=2,
            semester="202601",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            sessions=(CourseSession(3, 3, 4, time(10, 0), time(11, 40), tuple(range(1, 17)), "B203"),),
            source="demo",
        ),
        Course(
            id="demo:biology",
            name="生理学实验",
            teacher="王老师",
            credits=1,
            semester="202601",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
            sessions=(CourseSession(5, 5, 6, time(14, 0), time(15, 40), tuple(range(2, 17)), "实验楼 302"),),
            source="demo",
        ),
    )


def _serialize_course(course: Course) -> dict:
    value = course.to_dict()
    value["session_count"] = len(course.sessions)
    return value


def _schedule_payload(store_path: Path) -> dict:
    demo = not store_path.exists()
    courses = _demo_courses() if demo else FinalScheduleStore(store_path).load()
    return {
        "courses": [_serialize_course(course) for course in courses],
        "demo": demo,
        "store_path": str(store_path),
        "updated_at": datetime.now().astimezone().isoformat(),
    }


class WebHandler(SimpleHTTPRequestHandler):
    server_version = "PersonalLifeOS/0.1"

    def __init__(self, *args, directory: str | None = None, store_path: Path, empty_room_path: Path, calendar_path: Path, todo_path: Path, **kwargs):
        self.store_path = store_path
        self.empty_room_path = empty_room_path
        self.calendar_path = calendar_path
        self.todo_path = todo_path
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._json({"status": "ok", "service": "personal-life-os"})
            return
        if parsed.path == "/api/time":
            try:
                from urllib.parse import parse_qs
                self._json(read_system_time(parse_qs(parsed.query).get("timezone", [None])[0]))
            except ValueError as error:
                self._json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/periods":
            try:
                from urllib.parse import parse_qs
                value = parse_qs(parsed.query).get("date", [None])[0]
                query_date = date.fromisoformat(value) if value else datetime.now().date()
                self._json(periods_payload(query_date))
            except (TypeError, ValueError) as error:
                self._json({"error": f"作息日期无效：{error}"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/overview":
            try:
                from urllib.parse import parse_qs
                query = parse_qs(parsed.query)
                self._json(_overview_payload(self.calendar_path, self.todo_path, query.get("timezone", [None])[0]))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json({"error": f"今日总览读取失败：{error}"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/reminders":
            try:
                from urllib.parse import parse_qs
                self._json(_reminder_payload(self.calendar_path, parse_qs(parsed.query)))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json({"error": f"提醒读取失败：{error}"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/calendar":
            try:
                from urllib.parse import parse_qs
                self._json(_calendar_payload(self.calendar_path, parse_qs(parsed.query)))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json({"error": f"日历读取失败：{error}"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/todos":
            try:
                from urllib.parse import parse_qs
                self._json(_todo_payload(self.todo_path, parse_qs(parsed.query)))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json({"error": f"待办读取失败：{error}"}, HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/courses":
            try:
                self._json(_schedule_payload(self.store_path))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self._json({"error": f"课表读取失败：{error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/api/empty-rooms":
            try:
                self._json(_empty_room_payload(self.empty_room_path))
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json({"error": f"空教室数据读取失败：{error}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/import/file":
                self._import_file()
                return
            if parsed.path == "/api/import/hebmu":
                self._import_hebmu()
                return
            if parsed.path == "/api/import/hebmu-all":
                self._import_hebmu_all()
                return
            if parsed.path == "/api/calendar":
                self._create_calendar_event()
                return
            if parsed.path == "/api/todos":
                self._create_todo()
                return
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            # Keep API failures JSON-shaped so the browser can show a useful message.
            self._json({"error": str(error) or "导入失败"}, HTTPStatus.BAD_REQUEST)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/todos":
            from urllib.parse import parse_qs
            todo_id = parse_qs(parsed.query).get("id", [""])[0].strip()
            if not todo_id:
                self._json({"error": "缺少待办 id"}, HTTPStatus.BAD_REQUEST)
                return
            deleted = TodoService(TodoStore(self.todo_path)).delete(todo_id)
            self._json({"deleted": deleted}, HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND)
            return
        if parsed.path != "/api/calendar":
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        from urllib.parse import parse_qs
        event_id = parse_qs(parsed.query).get("id", [""])[0].strip()
        if not event_id:
            self._json({"error": "缺少事件 id"}, HTTPStatus.BAD_REQUEST)
            return
        deleted = CalendarService(CalendarStore(self.calendar_path)).delete(event_id)
        self._json({"deleted": deleted}, HTTPStatus.OK if deleted else HTTPStatus.NOT_FOUND)

    def do_PUT(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        try:
            from urllib.parse import parse_qs
            item_id = parse_qs(parsed.query).get("id", [""])[0].strip()
            body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
            if not item_id or not isinstance(body, dict):
                raise ValueError("请提供 id 和 JSON 对象请求体")
            if parsed.path == "/api/calendar":
                title = str(body.get("title", "")).strip()
                if not title or len(title) > 200:
                    raise ValueError("事件标题不能为空且不能超过 200 个字符")
                event = CalendarService(CalendarStore(self.calendar_path)).update(
                    item_id, title=title, starts_at=_parse_aware_datetime(body.get("starts_at"), "starts_at"),
                    ends_at=_parse_aware_datetime(body.get("ends_at"), "ends_at"),
                    location=str(body["location"]) if body.get("location") is not None else None,
                    description=str(body.get("description", "")),
                    recurrence_rule=body.get("recurrence_rule") or None,
                    recurrence_until=_parse_optional_date(body.get("recurrence_until"), "recurrence_until"),
                    reminder_minutes=int(body["reminder_minutes"]) if body.get("reminder_minutes") not in (None, "") else None,
                )
                self._json({"event": event.to_dict()}, HTTPStatus.OK) if event else self._json({"error": "日历事件不存在"}, HTTPStatus.NOT_FOUND)
                return
            if parsed.path == "/api/todos":
                title = str(body.get("title", "")).strip()
                if not title or len(title) > 200:
                    raise ValueError("待办标题不能为空且不能超过 200 个字符")
                priority = TodoPriority(str(body.get("priority", TodoPriority.MEDIUM)))
                due_at = _parse_aware_datetime(body["due_at"], "due_at") if body.get("due_at") else None
                todo = TodoService(TodoStore(self.todo_path)).update(
                    item_id, title=title, priority=priority, due_at=due_at, description=str(body.get("description", "")),
                )
                self._json({"todo": todo.to_dict()}, HTTPStatus.OK) if todo else self._json({"error": "待办不存在"}, HTTPStatus.NOT_FOUND)
                return
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self._json({"error": str(error) or "更新失败"}, HTTPStatus.BAD_REQUEST)

    def _create_calendar_event(self) -> None:
        body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("日历事件必须是 JSON 对象")
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 200:
            raise ValueError("事件标题不能为空且不能超过 200 个字符")
        event = CalendarService(CalendarStore(self.calendar_path)).create(
            title=title,
            starts_at=_parse_aware_datetime(body.get("starts_at"), "starts_at"),
            ends_at=_parse_aware_datetime(body.get("ends_at"), "ends_at"),
            description=str(body.get("description", "")),
            location=str(body["location"]) if body.get("location") is not None else None,
            event_id=str(body["id"]).strip() if body.get("id") else None,
            metadata=body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
            recurrence_rule=body.get("recurrence_rule") or None,
            recurrence_until=_parse_optional_date(body.get("recurrence_until"), "recurrence_until"),
            reminder_minutes=int(body["reminder_minutes"]) if body.get("reminder_minutes") not in (None, "") else None,
        )
        self._json({"event": event.to_dict()}, HTTPStatus.CREATED)

    def do_PATCH(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        if parsed.path != "/api/todos":
            self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            return
        try:
            from urllib.parse import parse_qs
            todo_id = parse_qs(parsed.query).get("id", [""])[0].strip()
            body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
            if not todo_id or not isinstance(body, dict) or not isinstance(body.get("completed"), bool):
                raise ValueError("请提供待办 id 和布尔类型 completed")
            item = TodoService(TodoStore(self.todo_path)).set_completed(todo_id, body["completed"])
            self._json({"todo": item.to_dict()}, HTTPStatus.OK) if item else self._json({"error": "待办不存在"}, HTTPStatus.NOT_FOUND)
        except Exception as error:
            self._json({"error": str(error) or "待办更新失败"}, HTTPStatus.BAD_REQUEST)

    def _create_todo(self) -> None:
        body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("待办必须是 JSON 对象")
        title = str(body.get("title", "")).strip()
        if not title or len(title) > 200:
            raise ValueError("待办标题不能为空且不能超过 200 个字符")
        priority = TodoPriority(str(body.get("priority", TodoPriority.MEDIUM)))
        due_at = _parse_aware_datetime(body["due_at"], "due_at") if body.get("due_at") else None
        item = TodoService(TodoStore(self.todo_path)).create(title=title, priority=priority, due_at=due_at, description=str(body.get("description", "")), todo_id=str(body["id"]).strip() if body.get("id") else None)
        self._json({"todo": item.to_dict()}, HTTPStatus.CREATED)

    def _read_body(self, *, limit: int = 10 * 1024 * 1024) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("无效的请求长度") from exc
        if length <= 0 or length > limit:
            raise ValueError("请求体为空或超过 10 MB 限制")
        return self.rfile.read(length)

    def _import_file(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("文件导入必须使用 multipart/form-data")
        message = BytesParser(policy=default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + self._read_body()
        )
        upload = next((part for part in message.walk() if part.get_filename()), None)
        if upload is None:
            raise ValueError("请选择 JSON、HTML 或 HTM 课表文件")
        filename = Path(upload.get_filename()).name
        if Path(filename).suffix.lower() not in {".json", ".html", ".htm"}:
            raise ValueError("仅支持 .json、.html 和 .htm 文件")
        payload = upload.get_payload(decode=True) or b""
        semester = self.headers.get("X-Semester") or None
        with tempfile.NamedTemporaryFile("wb", suffix=Path(filename).suffix, delete=False) as handle:
            temporary_path = Path(handle.name)
            handle.write(payload)
        try:
            courses = import_schedule_file(temporary_path, semester=semester)
            FinalScheduleStore(self.store_path).replace(courses)
        finally:
            temporary_path.unlink(missing_ok=True)
        self._json({"message": f"已导入 {len(courses)} 门课程", "count": len(courses), "demo": False})

    def _import_hebmu(self) -> None:
        body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
        semester = str(body.get("semester", "")).strip()
        start = date.fromisoformat(str(body.get("start", "")))
        end = date.fromisoformat(str(body.get("end", "")))
        week = str(body.get("week", "")).strip()
        if not semester or len(semester) > 32 or end < start:
            raise ValueError("请填写有效的学期、开始日期和结束日期")
        courses = HebmuBrowserImporter().fetch_courses(semester=semester, start=start, end=end, week=week)
        FinalScheduleStore(self.store_path).replace(courses)
        self._json({"message": f"已抓取并保存 {len(courses)} 门课程", "count": len(courses), "demo": False})

    def _import_hebmu_all(self) -> None:
        body = json.loads(self._read_body(limit=64 * 1024).decode("utf-8"))
        semester = str(body.get("semester", "")).strip()
        start = date.fromisoformat(str(body.get("start", "")))
        end = date.fromisoformat(str(body.get("end", "")))
        raw_dates = body.get("query_dates") or [body.get("query_date", "")]
        if not isinstance(raw_dates, list) or not raw_dates or len(raw_dates) > 2:
            raise ValueError("query_dates must contain one or two dates")
        query_dates = [date.fromisoformat(str(value)) for value in raw_dates]
        week = str(body.get("week", "")).strip()
        building_code = str(body.get("building_code", "")).strip()
        building_name = str(body.get("building_name", "")).strip()
        login_url = str(body.get("login_url", "")).strip() or None
        if login_url:
            parsed_login_url = urlparse(login_url)
            if parsed_login_url.scheme != "https" or parsed_login_url.hostname != "jwweb.hebmu.edu.cn" or "/app/" not in parsed_login_url.path:
                raise ValueError("微信授权链接必须是 jwweb.hebmu.edu.cn/app/ 下的 HTTPS 链接")
        if not semester or len(semester) > 32 or end < start:
            raise ValueError("请填写有效的学期、开始日期和结束日期")
        courses, classroom_payloads = fetch_courses_and_classroom_usage(
            semester=semester, start=start, end=end, week=week,
            building_code=building_code, building_name=building_name, query_dates=query_dates,
            login_url=login_url,
        )
        FinalScheduleStore(self.store_path).replace(courses)
        usage_by_date = {
            query_date: {
                "rooms": list(extract_classroom_names(payload)),
                "usage": list(extract_classroom_usage(payload)),
            }
            for query_date, payload in classroom_payloads.items()
        }
        for query_date, item in usage_by_date.items():
            payload = classroom_payloads[query_date]
            shape = f"keys={sorted(payload.keys())}" if isinstance(payload, dict) else f"type={type(payload).__name__}"
            api_status = f", code={payload.get('code')}, msg={payload.get('msg')}" if isinstance(payload, dict) else ""
            print(f"[hebmu] classroom {query_date}: {shape}{api_status}, rooms={len(item['rooms'])}, usage_rooms={len(item['usage'])}, occupied_periods={sum(len(room['occupied_periods']) for room in item['usage'])}")
        rooms = {room for item in usage_by_date.values() for room in item["rooms"]}
        self._json({
            "message": f"已登录一次并完成抓取：{len(courses)} 门课程，{len(rooms)} 个有使用记录的教室",
            "course_count": len(courses), "usage_room_count": len(rooms),
            "classroom_api_status": {
                query_date: {"code": payload.get("code"), "msg": payload.get("msg")}
                for query_date, payload in classroom_payloads.items()
                if isinstance(payload, dict) and ("code" in payload or "msg" in payload)
            },
            "classroom_usage_by_date": usage_by_date, "demo": False,
        })

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        print(f"[web] {self.address_string()} - {format % args}")


def serve(host: str = "127.0.0.1", port: int = 8000, store_path: Path | None = None,
          empty_room_path: Path | None = None, calendar_path: Path | None = None, todo_path: Path | None = None) -> None:
    selected_store = store_path or _store_path()
    selected_empty_room_path = empty_room_path or _empty_room_path()
    selected_calendar_path = calendar_path or _calendar_path()
    selected_todo_path = todo_path or _todo_path()
    handler = lambda *args, **kwargs: WebHandler(
        *args, directory=str(WEB_ROOT), store_path=selected_store,
        empty_room_path=selected_empty_room_path, calendar_path=selected_calendar_path, todo_path=selected_todo_path, **kwargs
    )
    server = ThreadingHTTPServer((host, port), handler)
    print(f"个人生活 OS 前端：http://{host}:{port}")
    print(f"课表文件：{selected_store}")
    print(f"空教室文件：{selected_empty_room_path}")
    print(f"日历文件：{selected_calendar_path}")
    print(f"待办文件：{selected_todo_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the personal-life-os demo web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--store", type=Path, default=_store_path())
    parser.add_argument("--empty-room-store", type=Path, default=_empty_room_path())
    parser.add_argument("--calendar-store", type=Path, default=_calendar_path())
    parser.add_argument("--todo-store", type=Path, default=_todo_path())
    args = parser.parse_args()
    serve(args.host, args.port, args.store, args.empty_room_store, args.calendar_store, args.todo_store)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
