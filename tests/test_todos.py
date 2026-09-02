import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from personal_life_os.todos import TodoPriority, TodoService, TodoStore


class TodoTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.service = TodoService(TodoStore(Path(self.directory.name) / "todos.json"))
        self.zone = ZoneInfo("Asia/Shanghai")

    def tearDown(self):
        self.directory.cleanup()

    def test_create_and_round_trip_todo(self):
        item = self.service.create(title="完成报告", priority=TodoPriority.HIGH,
                                   due_at=datetime(2026, 9, 1, 18, tzinfo=self.zone), description="提交 PDF")
        self.assertEqual(self.service.store.load(), (item,))
        self.assertEqual(item.to_dict()["priority"], "high")

    def test_complete_and_restore_todo(self):
        item = self.service.create(title="阅读资料")
        completed = self.service.set_completed(item.id, True)
        self.assertTrue(completed.completed)
        self.assertIsNotNone(completed.completed_at)
        restored = self.service.set_completed(item.id, False)
        self.assertFalse(restored.completed)
        self.assertIsNone(restored.completed_at)

    def test_rejects_invalid_due_time_and_duplicate_id(self):
        with self.assertRaises(ValueError):
            self.service.create(title="无时区", due_at=datetime(2026, 9, 1, 10))
        self.service.create(title="已有", todo_id="fixed")
        with self.assertRaises(ValueError):
            self.service.create(title="重复", todo_id="fixed")

    def test_update_changes_fields_but_preserves_completion_state(self):
        item = self.service.create(title="旧内容")
        self.service.set_completed(item.id, True)
        updated = self.service.update(item.id, title="新内容", priority=TodoPriority.HIGH, description="新备注")
        self.assertEqual(updated.title, "新内容")
        self.assertEqual(updated.priority, TodoPriority.HIGH)
        self.assertTrue(updated.completed)
        self.assertIsNotNone(updated.completed_at)


if __name__ == "__main__":
    unittest.main()
