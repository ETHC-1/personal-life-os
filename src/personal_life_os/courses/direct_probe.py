"""Safe diagnostic for testing direct classroom API access."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .school import EmptyClassroomImporter, _find_token, extract_classroom_usage


def _request(url: str, *, method: str, body: bytes | None, cookie: str, token: str | None = None,
             referer: str | None = None) -> tuple[int, Any]:
    headers = {
        "Accept": "application/json, text/plain, */*", "Cookie": cookie,
        "Origin": "https://jwweb.hebmu.edu.cn",
        "User-Agent": "Mozilla/5.0",
    }
    if referer:
        headers["Referer"] = referer
    if token:
        headers["token"] = token
    if body is not None:
        headers["Content-Type"] = "application/json;charset=UTF-8"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, {"response_type": "non_json", "response_bytes": len(raw)}


def probe_direct_classroom(*, building_code: str, building_name: str, query_date: date) -> dict[str, Any]:
    cookie = os.environ.get("HEBMU_COOKIE", "").strip()
    supplied_token = os.environ.get("HEBMU_TOKEN", "").strip() or None
    referer = os.environ.get("HEBMU_REFERER", "").strip() or None
    if not cookie:
        raise ValueError("请先设置 HEBMU_COOKIE 环境变量；不要把 Cookie 写入代码或文件")
    token_status, token_payload = _request(
        "https://jwweb.hebmu.edu.cn/dev-api/appapi/getIstoken", method="GET", body=None,
        cookie=cookie, token=supplied_token, referer=referer,
    )
    token = supplied_token or _find_token(token_payload)
    body = json.dumps({"jzwdm": building_code, "jzwmc": building_name, "rq": query_date.isoformat()}).encode("utf-8")
    classroom_status, classroom_payload = _request(
        EmptyClassroomImporter.classroom_url, method="POST", body=body, cookie=cookie,
        token=token, referer=referer,
    )
    payload = classroom_payload if isinstance(classroom_payload, dict) else {}
    usage = list(extract_classroom_usage(payload)) if payload else []
    return {
        "token_endpoint": {"http_status": token_status, "has_token": bool(token)},
        "classroom_endpoint": {
            "http_status": classroom_status, "payload_type": type(classroom_payload).__name__,
            "payload_keys": sorted(payload.keys()), "msg": payload.get("msg"),
            "usage_rooms": len(usage),
            "occupied_periods": sum(len(item["occupied_periods"]) for item in usage),
        },
    }


class DirectEmptyRoomWorker:
    """Fetch classroom usage without a browser or proxy, using temporary env credentials."""

    def __init__(self, *, building_code: str, building_name: str, output_path: Path,
                 timezone: str = "Asia/Shanghai") -> None:
        if not building_code.strip() or not building_name.strip():
            raise ValueError("building_code and building_name are required")
        self.building_code = building_code
        self.building_name = building_name
        self.output_path = output_path
        self.timezone = ZoneInfo(timezone)

    def fetch_day(self, query_date: date) -> dict[str, Any]:
        cookie = os.environ.get("HEBMU_COOKIE", "").strip()
        supplied_token = os.environ.get("HEBMU_TOKEN", "").strip() or None
        referer = os.environ.get("HEBMU_REFERER", "").strip() or None
        if not cookie:
            raise ValueError("请设置 HEBMU_COOKIE 环境变量")
        _, token_payload = _request(
            "https://jwweb.hebmu.edu.cn/dev-api/appapi/getIstoken", method="GET", body=None,
            cookie=cookie, token=supplied_token, referer=referer,
        )
        token = supplied_token or _find_token(token_payload)
        body = json.dumps({"jzwdm": self.building_code, "jzwmc": self.building_name,
                           "rq": query_date.isoformat()}).encode("utf-8")
        status, response = _request(
            EmptyClassroomImporter.classroom_url, method="POST", body=body, cookie=cookie,
            token=token, referer=referer,
        )
        payload = response if isinstance(response, dict) else {}
        if status != 200 or payload.get("msg") != "app_retrun_success_public":
            raise RuntimeError(f"classroom API 未通过认证或返回异常：HTTP {status}，msg={payload.get('msg')}")
        return {"date": query_date.isoformat(), "usage": list(extract_classroom_usage(payload))}

    def poll(self, *, start_date: date | None = None, days_ahead: int = 1) -> dict[str, Any]:
        if not 0 <= days_ahead <= 2:
            raise ValueError("days_ahead must be between 0 and 2")
        today = start_date or datetime.now(self.timezone).date()
        result = {
            "updated_at": datetime.now(self.timezone).isoformat(),
            "building": self.building_name,
            "days": [self.fetch_day(today + timedelta(days=offset)) for offset in range(days_ahead + 1)],
        }
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.output_path)
        return result
