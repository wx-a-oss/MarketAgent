from __future__ import annotations

from datetime import date, timedelta

WEEK_START_DAY = 5  # Saturday; Python weekday(): 0=Mon … 6=Sun


def week_boundaries(d: date) -> tuple[date, date]:
    """Return (start, end) of the week containing *d*.

    The week starts on WEEK_START_DAY (default Saturday) and spans 7 days.
    """
    offset = (d.weekday() - WEEK_START_DAY) % 7
    start = d - timedelta(days=offset)
    end = start + timedelta(days=6)
    return start, end
