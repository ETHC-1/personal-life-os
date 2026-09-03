import unittest
import json
import tempfile
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_life_os.courses.models import Course, CourseSession
from personal_life_os.courses.school import _find_token, extract_classroom_names, extract_classroom_usage
from personal_life_os.courses.bridge import ClassroomBridge
from personal_life_os.courses.parser import parse_course_table
from personal_life_os.courses.service import CourseCatalog
from personal_life_os.courses.storage import FinalScheduleStore
from personal_life_os.courses.importers import parse_schedule_json
from personal_life_os.courses.periods import periods_for
from personal_life_os.web import _empty_room_payload


HTML = """
<table><tr><th>课程名称</th><th>教师</th><th>星期</th><th>节次</th><th>周次</th><th>教室</th></tr>
<tr><td>高等数学</td><td>张老师</td><td>周一</td><td>1-2</td><td>1-16</td><td>A101</td></tr></table>
"""


class CourseTests(unittest.TestCase):
    def test_summer_afternoon_periods_shift_and_regular_schedule_restores(self):
        self.assertEqual(periods_for(date(2026, 5, 1))[5:9], (("14:30", "15:10"), ("15:20", "16:00"), ("16:10", "16:50"), ("17:00", "17:40")))
        self.assertEqual(periods_for(date(2026, 7, 5))[5:9], periods_for(date(2026, 5, 1))[5:9])
        self.assertEqual(periods_for(date(2026, 7, 6))[5], ("14:00", "14:40"))
        self.assertEqual(periods_for(date(2026, 8, 31))[5], ("14:00", "14:40"))

    def test_parse_common_course_table(self):
        courses = parse_course_table(HTML, source="demo", period_times={1: (time(8), time(8, 45)), 2: (time(8, 55), time(9, 40))})
        self.assertEqual(courses[0].name, "高等数学")
        self.assertEqual(courses[0].sessions[0].weekday, 1)
        self.assertEqual(courses[0].sessions[0].weeks, tuple(range(1, 17)))
        self.assertEqual(courses[0].sessions[0].start_time, time(8))


    def test_catalog_import_is_idempotent(self):
        class Source:
            name = "demo"

            def fetch_courses(self):
                return parse_course_table(HTML, source="demo")

        catalog = CourseCatalog()
        self.assertEqual(len(catalog.import_from(Source()).added), 1)
        self.assertEqual(len(catalog.import_from(Source()).skipped), 1)


    def test_reminder_requires_timezone_and_generates_event(self):
        course = Course(id="1", name="高等数学", start_date=date(2026, 9, 7), end_date=date(2026, 12, 28),
                        sessions=(CourseSession(1, 1, 2, time(8, 0), time(9, 40), (1,), "A101"),))
        catalog = CourseCatalog([course])
        tz = ZoneInfo("Asia/Shanghai")
        result = catalog.reminders_between(datetime(2026, 9, 7, 0, 0, tzinfo=tz), datetime(2026, 9, 7, 9, 0, tzinfo=tz))
        self.assertEqual(result[0].remind_at.hour, 7)

        with self.assertRaises(ValueError):
            catalog.reminders_between(datetime(2026, 9, 7), datetime(2026, 9, 7, 9))

    def test_final_schedule_store_round_trips_json(self):
        course = Course(id="demo:1", name="高等数学", start_date=date(2026, 9, 1),
                        sessions=(CourseSession(1, 1, 2, time(8), time(9, 40), (1, 2), "A101"),))
        with tempfile.TemporaryDirectory() as directory:
            store = FinalScheduleStore(Path(directory) / "final_schedule.json")
            store.replace([course])
            loaded = store.load()
        self.assertEqual(loaded[0], course)

    def test_parse_hebmu_schedule_response_without_raw_identifiers(self):
        courses = parse_schedule_json({
            "code": 0,
            "data": [{
                "kcmc": "示例课程", "xq": "2", "ps": "1", "pe": "2",
                "qssj": "08:00:00", "jssj": "09:30:00", "zc": "1,3",
                "jxcdmc": "示例教室", "kcrwdm": "example-task",
            }],
        }, semester="202601")
        self.assertEqual(courses[0].sessions[0].weekday, 2)
        self.assertEqual(courses[0].sessions[0].weeks, (1, 3))
        self.assertNotIn("kcmc", courses[0].metadata)

    def test_extract_classroom_names_from_usage_response(self):
        names = extract_classroom_names({
            "msg": "app_retrun_success_public",
            "jsylist": [
                {"jxcdmc": "东教学楼5教室"},
                {"jxcdmc": "东教学楼5教室"},
                {"jxcdmc": "东教学楼10教室"},
            ],
        })
        self.assertEqual(names, ("东教学楼10教室", "东教学楼5教室"))

    def test_extract_classroom_usage_exposes_only_room_and_periods(self):
        usage = extract_classroom_usage({"jsylist": [
            {"jxcdmc": "东教学楼5教室", "jcdm2": "03,04", "kcmc": "不应返回"},
            {"jxcdmc": "东教学楼5教室", "jcdm2": "06"},
        ]})
        self.assertEqual(usage, ({"room": "东教学楼5教室", "occupied_periods": [3, 4, 6]},))

    def test_extract_classroom_usage_accepts_nested_data_response(self):
        usage = extract_classroom_usage({"data": {"jsylist": [
            {"jxcdmc": "东教学楼10教室", "jcdm2": "10,11"},
        ]}})
        self.assertEqual(usage, ({"room": "东教学楼10教室", "occupied_periods": [10, 11]},))

    def test_extract_classroom_usage_accepts_api_jxllist_field(self):
        usage = extract_classroom_usage({"jxllist": [
            {"jxcdmc": "东教学楼5教室", "jcdm2": "03,04"},
        ]})
        self.assertEqual(usage, ({"room": "东教学楼5教室", "occupied_periods": [3, 4]},))

    def test_extract_classroom_usage_accepts_string_encoded_nested_records(self):
        usage = extract_classroom_usage({"data": json.dumps({"result": json.dumps({
            "jsylist": [{"jxcdmc": "东教学楼6教室", "jcdm2": "06"}],
        })})})
        self.assertEqual(usage, ({"room": "东教学楼6教室", "occupied_periods": [6]},))

    def test_extract_classroom_usage_accepts_alternate_list_key(self):
        usage = extract_classroom_usage({"msg": "ok", "jsyzlist": [
            {"jxcdmc": "东教学楼7教室", "jcdm2": "01,02"},
        ]})
        self.assertEqual(usage, ({"room": "东教学楼7教室", "occupied_periods": [1, 2]},))

    def test_extract_classroom_usage_accepts_actual_jszylist_field(self):
        usage = extract_classroom_usage({"msg": "ok", "jszylist": [
            {"jxcdmc": "东教学楼5教室", "jcdm2": "03,04"},
        ]})
        self.assertEqual(usage, ({"room": "东教学楼5教室", "occupied_periods": [3, 4]},))

    def test_bridge_strips_raw_classroom_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            bridge = ClassroomBridge(output_path=Path(directory) / "empty-rooms.json")
            result = bridge.ingest({"jszylist": [
                {"jxcdmc": "东教学楼5教室", "jcdm2": "03,04", "kcmc": "private course"},
            ]})
            saved = json.loads((Path(directory) / "empty-rooms.json").read_text(encoding="utf-8"))
        self.assertEqual(result["occupied_periods"], 2)
        self.assertNotIn("kcmc", json.dumps(saved, ensure_ascii=False))

    def test_find_token_from_nested_token_response(self):
        self.assertEqual(_find_token({"data": {"token": "token-value-123456789"}}), "token-value-123456789")

    def test_web_reads_sanitized_bridge_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-rooms.json"
            path.write_text(json.dumps({"date": "2026-09-01", "updated_at": "2026-09-01T10:00:00+08:00", "usage": [{"room": "东教学楼5教室", "occupied_periods": [3, 99], "kcmc": "private"}]}), encoding="utf-8")
            payload = _empty_room_payload(path)
        self.assertEqual(payload["classroom_usage_by_date"]["2026-09-01"]["usage"][0]["occupied_periods"], [3])
        self.assertNotIn("private", json.dumps(payload, ensure_ascii=False))

    def test_web_sanitizes_multi_day_direct_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty-rooms.json"
            path.write_text(json.dumps({
                "updated_at": "2026-09-01T10:00:00+08:00",
                "building": "中山校区.东教学楼",
                "days": [{"date": "2026-09-01", "usage": [{
                    "room": "东教学楼5教室", "occupied_periods": [4, 3, 3, 14, True],
                    "course_name": "private",
                }]}],
            }), encoding="utf-8")
            payload = _empty_room_payload(path)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["building"], "中山校区.东教学楼")
        self.assertEqual(payload["classroom_usage_by_date"]["2026-09-01"]["usage"][0]["occupied_periods"], [3, 4])
        self.assertNotIn("private", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
