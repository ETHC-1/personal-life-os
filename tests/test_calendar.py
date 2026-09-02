import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_life_os.calendar import CalendarService, CalendarStore, EventConflictError
from personal_life_os.system_time import read_system_time
from personal_life_os.web import _calendar_payload, _overview_payload, _reminder_payload
from personal_life_os.todos import TodoService, TodoStore


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = CalendarStore(Path(self.directory.name) / "calendar.json")
        self.service = CalendarService(self.store)
        self.zone = ZoneInfo("Asia/Shanghai")

    def tearDown(self):
        self.directory.cleanup()

    def test_create_and_query_event(self):
        event = self.service.create(
            title="项目评审",
            starts_at=datetime(2026, 9, 1, 9, tzinfo=self.zone),
            ends_at=datetime(2026, 9, 1, 10, tzinfo=self.zone),
        )
        result = self.service.list_between(
            datetime(2026, 9, 1, 9, 30, tzinfo=self.zone),
            datetime(2026, 9, 1, 11, tzinfo=self.zone),
        )
        self.assertEqual(result, (event,))
        self.assertEqual(self.store.load(), (event,))

    def test_rejects_naive_and_overlapping_events(self):
        with self.assertRaises(ValueError):
            self.service.create(title="无时区", starts_at=datetime(2026, 9, 1, 9), ends_at=datetime(2026, 9, 1, 10))
        self.service.create(title="已有安排", starts_at=datetime(2026, 9, 1, 9, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 10, tzinfo=self.zone))
        with self.assertRaises(EventConflictError):
            self.service.create(title="冲突安排", starts_at=datetime(2026, 9, 1, 9, 59, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 11, tzinfo=self.zone))

    def test_update_preserves_event_id_and_rejects_conflict_without_overwriting(self):
        first = self.service.create(title="原安排", starts_at=datetime(2026, 9, 1, 9, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 10, tzinfo=self.zone))
        other = self.service.create(title="其他安排", starts_at=datetime(2026, 9, 1, 14, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 15, tzinfo=self.zone))
        updated = self.service.update(first.id, title="新安排", starts_at=datetime(2026, 9, 1, 10, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 11, tzinfo=self.zone))
        self.assertEqual(updated.title, "新安排")
        with self.assertRaises(ValueError):
            self.service.update(first.id, title="冲突", starts_at=other.starts_at, ends_at=other.ends_at)
        self.assertEqual(self.store.load()[0].title, "新安排")

    def test_system_time_is_timezone_aware(self):
        payload = read_system_time()
        self.assertEqual(payload["timezone"], "Asia/Shanghai")
        self.assertIn("+08:00", payload["now"])
        with self.assertRaises(ValueError):
            read_system_time("Not/A_Timezone")

    def test_calendar_api_payload_supports_timezone_query(self):
        self.service.create(
            title="UTC 会议",
            starts_at=datetime(2026, 9, 1, 1, tzinfo=ZoneInfo("UTC")),
            ends_at=datetime(2026, 9, 1, 2, tzinfo=ZoneInfo("UTC")),
        )
        payload = _calendar_payload(self.store.path, {"start": ["2026-09-01T08:00:00+08:00"], "end": ["2026-09-01T11:00:00+08:00"]})
        self.assertEqual(payload["events"][0]["title"], "UTC 会议")

    def test_overview_combines_today_events_and_open_todos(self):
        today = datetime.now(self.zone).replace(hour=9, minute=0, second=0, microsecond=0)
        self.service.create(title="今日会议", starts_at=today, ends_at=today.replace(hour=10))
        todo_service = TodoService(TodoStore(Path(self.directory.name) / "todos.json"))
        todo_service.create(title="今日截止", due_at=today.replace(hour=18))
        todo_service.create(title="明日截止", due_at=today + timedelta(days=1, hours=9))
        payload = _overview_payload(self.store.path, todo_service.store.path, "Asia/Shanghai")
        self.assertEqual(payload["date"], today.date().isoformat())
        self.assertEqual(payload["todo_open_count"], 2)
        self.assertEqual([item["title"] for item in payload["todos_due_today"]], ["今日截止"])

    def test_recurring_event_expands_and_reminder_is_calculated(self):
        event = self.service.create(title="每日计划", starts_at=datetime(2026, 9, 1, 9, tzinfo=self.zone), ends_at=datetime(2026, 9, 1, 10, tzinfo=self.zone), recurrence_rule="daily", recurrence_until=datetime(2026, 9, 3, tzinfo=self.zone).date(), reminder_minutes=30)
        events = self.service.list_between(datetime(2026, 9, 1, tzinfo=self.zone), datetime(2026, 9, 4, tzinfo=self.zone))
        self.assertEqual(len(events), 3)
        self.assertEqual(events[1].starts_at.date().isoformat(), "2026-09-02")
        reminders = _reminder_payload(self.store.path, {"start": ["2026-09-01T08:00:00+08:00"], "end": ["2026-09-01T10:00:00+08:00"]})
        self.assertEqual(reminders["reminders"][0]["minutes_before"], 30)


if __name__ == "__main__":
    unittest.main()
