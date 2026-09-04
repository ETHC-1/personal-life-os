from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any

from .importers import parse_schedule_json
from .models import Course


class HebmuBrowserSession:
    """One visible, user-authenticated browser session for multiple queries."""

    login_url = "https://jwweb.hebmu.edu.cn/"

    def __init__(self, *, login_url: str | None = None, login_timeout_ms: int = 300_000) -> None:
        self.login_url = login_url or self.login_url
        self.login_timeout_ms = login_timeout_ms
        self._playwright = None
        self._browser = None
        self.context = None
        self.page = None
        self._token = None

    istoken_url = "https://jwweb.hebmu.edu.cn/dev-api/appapi/getIstoken"

    def __enter__(self) -> "HebmuBrowserSession":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("browser import requires the optional 'browser' dependency") from exc
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=False)
        self.context = self._browser.new_context()
        self.page = self.context.new_page()
        self.page.on("request", self._capture_request_token)
        self.page.goto(self.login_url, wait_until="domcontentloaded")
        if "/app/" in self.login_url:
            self.page.wait_for_load_state("networkidle", timeout=self.login_timeout_ms)
        else:
            self.page.wait_for_url("**/new/welcome.page", timeout=self.login_timeout_ms)
        return self

    def _capture_request_token(self, request: Any) -> None:
        """Keep a page-issued token in memory without logging or persisting it."""
        token = request.headers.get("token")
        if isinstance(token, str) and token.strip():
            self._token = token.strip()

    def _ensure_token(self) -> None:
        if self._token or self.page is None:
            return
        response = self.page.evaluate(
            """
            async (url) => {
              const response = await fetch(url, {method: "GET", credentials: "include"});
              return {status: response.status, body: await response.json()};
            }
            """,
            self.istoken_url,
        )
        if response.get("status") == 200:
            self._token = _find_token(response.get("body"))

    def post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        if self.page is None:
            raise RuntimeError("browser session is not open")
        self._ensure_token()
        return self.page.evaluate(
            """
            async ({url, body, token}) => {
              const headers = {"Content-Type": "application/json"};
              if (token) headers.token = token;
              const response = await fetch(url, {
                method: "POST",
                credentials: "include",
                headers,
                body: JSON.stringify(body)
              });
              if (!response.ok) throw new Error(`request failed: ${response.status}`);
              return await response.json();
            }
            """,
            {"url": url, "body": body, "token": self._token},
        )

    def post_form(self, url: str, body: dict[str, str]) -> dict[str, Any]:
        if self.page is None:
            raise RuntimeError("browser session is not open")
        self._ensure_token()
        return self.page.evaluate(
            """
            async ({url, body, token}) => {
              const headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest"
              };
              if (token) headers.token = token;
              const response = await fetch(url, {
                method: "POST",
                credentials: "include",
                headers,
                body: new URLSearchParams(body)
              });
              if (!response.ok) throw new Error(`request failed: ${response.status}`);
              return await response.json();
            }
            """,
            {"url": url, "body": body, "token": self._token},
        )

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.context is not None:
            self.context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()


class HebmuBrowserImporter:
    """Open a visible browser for user-led campus login, then fetch the schedule.

    Playwright is optional. The user completes the campus password and CAPTCHA flow in the
    browser; this class never receives credentials and never exports browser cookies.
    """

    login_url = "https://jwweb.hebmu.edu.cn/"
    api_url = "https://jwweb.hebmu.edu.cn/new/student/xsgrkb/getCalendarWeekDatas"

    def __init__(self, *, login_url: str | None = None, api_url: str | None = None, login_timeout_ms: int = 300_000) -> None:
        self.login_url = login_url or self.login_url
        self.api_url = api_url or self.api_url
        self.login_timeout_ms = login_timeout_ms

    def fetch_courses(self, *, semester: str, start: date, end: date, week: str = "") -> list[Course]:
        with HebmuBrowserSession(login_url=self.login_url, login_timeout_ms=self.login_timeout_ms) as session:
            payload = session.post_form(self.api_url, {
                "xnxqdm": semester, "zc": week,
                "d1": f"{start.isoformat()} 00:00:00", "d2": f"{end.isoformat()} 00:00:00",
            })
            return parse_schedule_json(payload, source="hebmu_jw", semester=semester)


class EmptyClassroomImporter:
    """Fetch classroom usage records for one building and date.

    This is intentionally independent from the course importer. It opens a visible
    browser and lets the user complete the campus login, then calls the appkxjs
    endpoint in the same authenticated page context. The endpoint response is
    usage data; calculating truly empty rooms requires a complete room inventory.
    """

    login_url = "https://jwweb.hebmu.edu.cn/"
    classroom_url = "https://jwweb.hebmu.edu.cn/dev-api/appapi/appkxjs/classroom"

    def __init__(self, *, login_url: str | None = None, classroom_url: str | None = None,
                 login_timeout_ms: int = 300_000) -> None:
        self.login_url = login_url or self.login_url
        self.classroom_url = classroom_url or self.classroom_url
        self.login_timeout_ms = login_timeout_ms

    def fetch_usage(self, *, building_code: str, building_name: str, query_date: date) -> dict[str, Any]:
        if not building_code.strip() or not building_name.strip():
            raise ValueError("building_code and building_name are required")
        with HebmuBrowserSession(login_url=self.login_url, login_timeout_ms=self.login_timeout_ms) as session:
            return session.post_json(self.classroom_url, {
                "jzwdm": building_code, "jzwmc": building_name, "rq": query_date.isoformat()
            })

    def fetch_classroom_names(self, *, building_code: str, building_name: str, query_date: date) -> tuple[str, ...]:
        """Return classroom names observed in the usage response."""
        payload = self.fetch_usage(building_code=building_code, building_name=building_name, query_date=query_date)
        return extract_classroom_names(payload)


def extract_classroom_names(payload: dict[str, Any]) -> tuple[str, ...]:
    """Extract unique classroom names from a classroom API response."""
    # jxcdxxList is the complete room catalog. jszylist only contains rooms
    # with usage, which is especially important for future dates.
    records = _find_named_records(payload, {"jxcdxxList", "jxcdxxlist"}) or _classroom_records(payload)
    if not isinstance(records, list):
        raise ValueError("classroom response jsylist must be a list")
    names: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get("jxcdmc") or record.get("jsmc") or record.get("classroom")
        if isinstance(value, str) and value.strip():
            names.add(value.strip())
    return tuple(sorted(names))


def extract_classroom_usage(payload: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    """Return only room names and occupied periods from a usage response."""
    # Usage periods come from jszylist; the catalog has no period field.
    records = _find_named_records(payload, {"jszylist", "jsylist", "jsyzlist"}) or _classroom_records(payload)
    if not isinstance(records, list):
        raise ValueError("classroom response jsylist must be a list")
    usage: dict[str, set[int]] = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        room = record.get("jxcdmc") or record.get("jsmc") or record.get("classroom")
        if not isinstance(room, str) or not room.strip():
            continue
        raw_periods = str(record.get("jcdm2") or record.get("periods") or record.get("jcdm") or "")
        periods = {int(value) for value in re.findall(r"(?<!\d)(?:0?[1-9]|1[0-3])(?!\d)", raw_periods)}
        usage.setdefault(re.sub(r"\s+", "", room.strip()), set()).update(periods)
    return tuple({"room": room, "occupied_periods": sorted(periods)} for room, periods in sorted(usage.items()))


def _find_named_records(value: Any, keys: set[str]) -> list[dict[str, Any]]:
    """Find the first named list of object records in a nested API payload."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in keys:
                return [item for item in nested if isinstance(item, dict)] if isinstance(nested, list) else []
        for nested in value.values():
            found = _find_named_records(nested, keys)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_named_records(nested, keys)
            if found:
                return found
    return []


def _classroom_records(payload: dict[str, Any]) -> Any:
    """Accept nested/string response shapes and select actual classroom records."""
    def decode(value: Any) -> Any:
        for _ in range(2):
            if not isinstance(value, str):
                break
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return []
        return value

    def find(value: Any) -> list[dict[str, Any]]:
        value = decode(value)
        if isinstance(value, list):
            records = [item for item in value if isinstance(item, dict)]
            if any(item.get("jxcdmc") or item.get("jsmc") or item.get("classroom") for item in records):
                return records
            for item in value:
                found = find(item)
                if found:
                    return found
        elif isinstance(value, dict):
            for key in ("jxllist", "jsylist", "jsyzlist", "jszylist", "data", "result", "rows"):
                if key in value:
                    found = find(value[key])
                    if found:
                        return found
            for nested in value.values():
                found = find(nested)
                if found:
                    return found
        return []

    return find(payload)


def _find_token(value: Any) -> str | None:
    """Find a token in a token endpoint response without exposing its value."""
    if isinstance(value, dict):
        for key in ("token", "access_token", "istoken", "data"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        for nested in value.values():
            found = _find_token(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_token(nested)
            if found:
                return found
    return None


def fetch_courses_and_classroom_usage(*, semester: str, start: date, end: date, week: str,
                                      building_code: str, building_name: str, query_dates: list[date],
                                      login_url: str | None = None,
                                      login_timeout_ms: int = 300_000) -> tuple[list[Course], dict[str, dict[str, Any]]]:
    """Fetch courses and classroom usage for multiple dates after one manual login."""
    if not building_code.strip() or not building_name.strip():
        raise ValueError("building_code and building_name are required")
    with HebmuBrowserSession(login_url=login_url, login_timeout_ms=login_timeout_ms) as session:
        course_payload = session.post_form(HebmuBrowserImporter.api_url, {
            "xnxqdm": semester, "zc": week,
            "d1": f"{start.isoformat()} 00:00:00", "d2": f"{end.isoformat()} 00:00:00",
        })
        classroom_payloads = {}
        for query_date in query_dates:
            classroom_payloads[query_date.isoformat()] = session.post_json(EmptyClassroomImporter.classroom_url, {
                "jzwdm": building_code, "jzwmc": building_name, "rq": query_date.isoformat()
            })
        return parse_schedule_json(course_payload, source="hebmu_jw", semester=semester), classroom_payloads
