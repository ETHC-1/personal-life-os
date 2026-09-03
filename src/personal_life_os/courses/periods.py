"""School bell schedule, including the summer afternoon adjustment."""
from __future__ import annotations

from datetime import date

BASE_PERIODS: tuple[tuple[str, str], ...] = (
    ("08:00", "08:40"), ("08:50", "09:30"), ("09:50", "10:30"),
    ("10:40", "11:20"), ("11:20", "12:00"), ("14:00", "14:40"),
    ("14:50", "15:30"), ("15:40", "16:20"), ("16:30", "17:10"),
    ("18:30", "19:10"), ("19:20", "20:00"), ("20:10", "20:50"),
    ("21:00", "21:40"),
)


def periods_for(query_date: date) -> tuple[tuple[str, str], ...]:
    """Return the 13 periods for a date in the Asia/Shanghai school calendar.

    The afternoon periods 6–9 move 30 minutes later from May 1 through July 5.
    July 6 onward, including the August 31 semester start, uses the base schedule.
    """
    if date(query_date.year, 5, 1) <= query_date <= date(query_date.year, 7, 5):
        periods = list(BASE_PERIODS)
        for index in range(5, 9):
            start, end = periods[index]
            periods[index] = (f"{int(start[:2]) + (int(start[3:]) + 30) // 60:02d}:{(int(start[3:]) + 30) % 60:02d}",
                              f"{int(end[:2]) + (int(end[3:]) + 30) // 60:02d}:{(int(end[3:]) + 30) % 60:02d}")
        return tuple(periods)
    return BASE_PERIODS


def periods_payload(query_date: date) -> dict[str, object]:
    summer = date(query_date.year, 5, 1) <= query_date <= date(query_date.year, 7, 5)
    return {
        "date": query_date.isoformat(),
        "season": "summer-afternoon-shift" if summer else "regular",
        "periods": [{"period": index, "start": start, "end": end} for index, (start, end) in enumerate(periods_for(query_date), 1)],
    }
