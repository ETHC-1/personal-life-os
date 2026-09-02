from __future__ import annotations

import json
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .school import EmptyClassroomImporter, extract_classroom_usage


class WechatEmptyRoomWorker:
    """Poll empty-room usage with a persistent, manually authorized browser profile."""

    def __init__(self, *, user_data_dir: Path, login_url: str,
                 building_code: str, building_name: str, output_path: Path,
                 timezone: str = "Asia/Shanghai", headless: bool = False) -> None:
        if not building_code.strip() or not building_name.strip():
            raise ValueError("building_code and building_name are required")
        self.user_data_dir = user_data_dir
        self.login_url = login_url
        self.building_code = building_code
        self.building_name = building_name
        self.output_path = output_path
        self.timezone = ZoneInfo(timezone)
        self.headless = headless
        self._token: str | None = None
        self._playwright = None
        self._context = None
        self._page = None

    def __enter__(self) -> "WechatEmptyRoomWorker":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("empty-room-poll requires the optional 'browser' dependency") from exc
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        self._context = self._playwright.chromium.launch_persistent_context(
            str(self.user_data_dir), headless=self.headless,
        )
        self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        self._page.on("request", self._capture_token)
        self._page.goto(self.login_url, wait_until="domcontentloaded")
        self._page.wait_for_timeout(5_000)
        return self

    def _capture_token(self, request: Any) -> None:
        token = request.headers.get("token")
        if isinstance(token, str) and token.strip():
            self._token = token.strip()

    def fetch_day(self, query_date: date) -> dict[str, Any]:
        if self._page is None:
            raise RuntimeError("worker is not open")
        payload = self._page.evaluate(
            """
            async ({url, body, token}) => {
              const headers = {"Content-Type": "application/json"};
              if (token) headers.token = token;
              const response = await fetch(url, {
                method: "POST", credentials: "include", headers,
                body: JSON.stringify(body)
              });
              return {status: response.status, body: await response.json()};
            }
            """,
            {
                "url": EmptyClassroomImporter.classroom_url,
                "body": {"jzwdm": self.building_code, "jzwmc": self.building_name,
                         "rq": query_date.isoformat()},
                "token": self._token,
            },
        )
        if payload.get("status") != 200:
            raise RuntimeError(f"classroom request failed: HTTP {payload.get('status')}")
        response = payload.get("body")
        if isinstance(response, dict) and response.get("code") == 401:
            raise RuntimeError("微信授权会话已失效，请重新完成一次授权")
        usage = list(extract_classroom_usage(response if isinstance(response, dict) else {}))
        return {"date": query_date.isoformat(), "usage": usage}

    def poll(self, *, start_date: date | None = None, days_ahead: int = 1) -> dict[str, Any]:
        today = start_date or datetime.now(self.timezone).date()
        result = {
            "generated_at": datetime.now(self.timezone).isoformat(),
            "building_code": self.building_code,
            "building_name": self.building_name,
            "days": [self.fetch_day(today + timedelta(days=offset)) for offset in range(days_ahead + 1)],
        }
        self._write_result(result)
        return result

    def _write_result(self, result: dict[str, Any]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.output_path)

    def run_forever(self, *, start_hour: int = 6, end_hour: int = 21, days_ahead: int = 1) -> None:
        if not 0 <= start_hour <= end_hour <= 23:
            raise ValueError("polling hours must be between 0 and 23")
        while True:
            now = datetime.now(self.timezone)
            next_run = self._next_run(now, start_hour, end_hour)
            time.sleep(max(0, (next_run - now).total_seconds()))
            try:
                self.poll(days_ahead=days_ahead)
            except Exception as exc:
                print(f"[empty-room] 抓取失败：{exc}")
            time.sleep(1)

    def _next_run(self, now: datetime, start_hour: int, end_hour: int) -> datetime:
        current_hour = now.hour
        if start_hour <= current_hour <= end_hour and now.minute == 0 and now.second == 0:
            return now
        candidate = now.replace(minute=0, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(hours=1)
        if candidate.hour < start_hour or candidate.hour > end_hour:
            day = now.date() if candidate.hour < start_hour else now.date() + timedelta(days=1)
            candidate = datetime.combine(day, clock_time(start_hour), tzinfo=self.timezone)
        return candidate

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self._context is not None:
            self._context.close()
        if self._playwright is not None:
            self._playwright.stop()
