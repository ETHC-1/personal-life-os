from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def read_system_time(timezone_name: str | None = None) -> dict[str, str]:
    """Return the server clock in a requested zone and UTC, always as ISO 8601."""
    requested = timezone_name or "Asia/Shanghai"
    try:
        zone = ZoneInfo(requested)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("无效的时区") from exc
    now_utc = datetime.now(timezone.utc)
    return {
        "timezone": requested,
        "now": now_utc.astimezone(zone).isoformat(),
        "utc": now_utc.isoformat(),
    }
