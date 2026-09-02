from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from .school import extract_classroom_usage


class ClassroomBridge:
    """Receive raw local proxy responses and retain only safe classroom usage data."""

    def __init__(self, *, output_path: Path, remote_url: str | None = None) -> None:
        self.output_path = output_path
        self.remote_url = remote_url
        self.last_result: dict[str, Any] | None = None
        self.received_count = 0
        self.last_diagnostic: dict[str, Any] = {}
        self.last_error: str | None = None

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.last_diagnostic = {
            "payload_type": type(payload).__name__,
            "payload_keys": sorted(payload.keys()),
            "record_count": len(_records(payload)),
        }
        usage = list(extract_classroom_usage(payload))
        if not usage:
            self.last_result = {"accepted": False, "usage_rooms": 0, "occupied_periods": 0}
            self.last_diagnostic["usage_rooms"] = 0
            return self.last_result
        dates = sorted({str(item.get("rq")) for item in _records(payload) if item.get("rq")})
        query_date = dates[0] if dates else datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        result = {
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "date": query_date,
            "building": "东教学楼",
            "usage": usage,
        }
        self._write(result)
        if self.remote_url:
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(self.remote_url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=10):
                pass
        self.last_result = {"accepted": True, "usage_rooms": len(usage), "occupied_periods": sum(len(item["occupied_periods"]) for item in usage)}
        self.last_diagnostic["usage_rooms"] = len(usage)
        return self.last_result

    def _write(self, result: dict[str, Any]) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.output_path)


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("jszylist", "jsylist", "jsyzlist", "jxllist"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def serve_bridge(*, host: str = "127.0.0.1", port: int = 8765, output_path: Path,
                 remote_url: str | None = None) -> None:
    bridge = ClassroomBridge(output_path=output_path, remote_url=remote_url)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path != "/":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            result = bridge.last_result or {"accepted": False, "usage_rooms": 0, "occupied_periods": 0}
            body = json.dumps({"service": "empty-room-bridge", "ready": True, "received_count": bridge.received_count, "last_result": result, "last_diagnostic": bridge.last_diagnostic, "last_error": bridge.last_error}, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            if self.path != "/ingest":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                bridge.received_count += 1
                length = int(self.headers.get("Content-Length", "0"))
                if length > 5 * 1024 * 1024:
                    raise ValueError("payload too large")
                raw_body = self.rfile.read(length)
                try:
                    text_body = raw_body.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text_body = raw_body.decode("gb18030")
                payload = json.loads(text_body)
                result = bridge.ingest(payload)
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                print(f"[bridge] accepted={result['accepted']} usage_rooms={result['usage_rooms']} occupied_periods={result['occupied_periods']}")
            except Exception as exc:
                bridge.last_error = f"{type(exc).__name__}: {exc}"
                print(f"[bridge] request rejected: {type(exc).__name__}")
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    print(f"空教室本地采集桥：http://{host}:{port}/ingest")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n采集桥已停止")
    finally:
        server.server_close()
