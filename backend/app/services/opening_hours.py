"""Pure opening-hours helpers for Google Places API (New) v1 ``regularOpeningHours``.

No FastAPI/SQLAlchemy imports. Every function is defensive: malformed or
missing hours data returns the "unknown" sentinel instead of raising, so a
scheduling bug here can never abort itinerary generation.
"""

import datetime

WEEK_MINUTES = 7 * 24 * 60  # 10080


def google_weekday(d: datetime.date) -> int:
    """Convert a Python date to the Google Places convention (0=Sunday..6=Saturday)."""
    return (d.weekday() + 1) % 7


def _period_open_minute(period: dict) -> int | None:
    open_point = period.get("open")
    if not isinstance(open_point, dict) or "day" not in open_point:
        return None
    try:
        day = int(open_point["day"])
        hour = int(open_point.get("hour", 0) or 0)
        minute = int(open_point.get("minute", 0) or 0)
    except (TypeError, ValueError):
        return None
    return day * 1440 + hour * 60 + minute


def _period_close_minute(period: dict, open_minute: int) -> int | None:
    """Return the close instant in week-absolute minutes, or ``None`` for a
    close-less (24-hour) period. Wraps past the open instant so overnight
    windows and the Saturday-night-into-Sunday week wrap both resolve."""
    close_point = period.get("close")
    if not isinstance(close_point, dict):
        return None
    try:
        day = int(close_point.get("day", 0) or 0)
        hour = int(close_point.get("hour", 0) or 0)
        minute = int(close_point.get("minute", 0) or 0)
    except (TypeError, ValueError):
        return None
    close_minute = day * 1440 + hour * 60 + minute
    if close_minute <= open_minute:
        close_minute += WEEK_MINUTES
    return close_minute


def is_open_at(opening_hours: dict | None, weekday: int, minute_of_day: int) -> bool | None:
    """Return ``True``/``False`` when hours are known, ``None`` when unknown
    or malformed (legacy ``{"open_now": ...}`` rows, missing data, garbage).

    ``weekday`` uses the Google convention (0=Sunday..6=Saturday); see
    :func:`google_weekday`.
    """
    try:
        if not isinstance(opening_hours, dict):
            return None
        periods = opening_hours.get("periods")
        if not isinstance(periods, list) or not periods:
            return None

        t = weekday * 1440 + minute_of_day

        for period in periods:
            if not isinstance(period, dict):
                continue
            open_minute = _period_open_minute(period)
            if open_minute is None:
                continue
            close_minute = _period_close_minute(period, open_minute)
            if close_minute is None:
                # No close point emitted -> always open (24/7 place).
                return True
            if open_minute <= t < close_minute or open_minute <= t + WEEK_MINUTES < close_minute:
                return True

        return False
    except Exception:  # noqa: BLE001 - never let malformed hours data raise
        return None


def next_open_minute(
    opening_hours: dict | None,
    weekday: int,
    from_minute: int,
    until_minute: int,
) -> int | None:
    """Return the earliest minute in ``[from_minute, until_minute]`` on
    ``weekday`` at which the venue is open, or ``None`` if it never opens in
    that window or hours are unknown. Returns ``from_minute`` if already open.
    """
    try:
        if is_open_at(opening_hours, weekday, from_minute) is True:
            return from_minute
        if not isinstance(opening_hours, dict):
            return None
        periods = opening_hours.get("periods")
        if not isinstance(periods, list) or not periods:
            return None
        if from_minute > until_minute:
            return None

        t_from = weekday * 1440 + from_minute
        t_until = weekday * 1440 + until_minute
        candidates: list[int] = []

        for period in periods:
            if not isinstance(period, dict):
                continue
            open_minute = _period_open_minute(period)
            if open_minute is None:
                continue
            # Consider the period's open instant both in this week and the
            # following week (in case it wraps from the prior day into this
            # window), reduced back to a clock-minute-of-day candidate.
            for candidate in (open_minute, open_minute + WEEK_MINUTES, open_minute - WEEK_MINUTES):
                if t_from <= candidate <= t_until:
                    candidates.append(candidate - weekday * 1440)

        if not candidates:
            return None
        return min(candidates)
    except Exception:  # noqa: BLE001 - never let malformed hours data raise
        return None
