"""School bell schedule, including the summer afternoon adjustment."""
from __future__ import annotations

from datetime import date

BASE_PERIODS: tuple[tuple[str, str], ...] = (
    ("08:00", "08:40"), ("08:50", "09:30"), ("09:50", "10:30"),
    ("10:40", "11:20"), ("11:20", "12:00"), ("14:30", "15:10"),
    ("15:20", "16:00"), ("16:10", "16:50"), ("17:00", "17:40"),
    ("18:30", "19:10"), ("19:20", "20:00"), ("20:10", "20:50"),
    ("21:00", "21:40"),
)


def periods_for(query_date: date) -> tuple[tuple[str, str], ...]:
    """Return the 13 periods for a date in the Asia/Shanghai school calendar.

    The afternoon periods 6–9 run at 14:00 from May 1 through July 5.
    During all other dates they run at 14:30. Period 10 remains at 18:30.
    """
    if date(query_date.year, 5, 1) <= query_date <= date(query_date.year, 7, 5):
        periods = list(BASE_PERIODS)
        periods[5:9] = (("14:00", "14:40"), ("14:50", "15:30"), ("15:40", "16:20"), ("16:30", "17:10"))
        return tuple(periods)
    return BASE_PERIODS


def periods_payload(query_date: date) -> dict[str, object]:
    summer = date(query_date.year, 5, 1) <= query_date <= date(query_date.year, 7, 5)
    return {
        "date": query_date.isoformat(),
        "season": "may-july-afternoon-14:00" if summer else "regular-afternoon-14:30",
        "periods": [{"period": index, "start": start, "end": end} for index, (start, end) in enumerate(periods_for(query_date), 1)],
    }
