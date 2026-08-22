"""Tests for the pure opening-hours helpers (Places API v1 regularOpeningHours)."""

import datetime

from app.services import opening_hours as oh


def hours(periods: list[dict]) -> dict:
    return {"periods": periods}


def point(day: int, hour: int = 0, minute: int = 0) -> dict:
    return {"day": day, "hour": hour, "minute": minute}


# --- google_weekday --------------------------------------------------------


def test_google_weekday_monday():
    assert oh.google_weekday(datetime.date(2026, 8, 24)) == 1  # a Monday


def test_google_weekday_sunday():
    assert oh.google_weekday(datetime.date(2026, 8, 23)) == 0  # a Sunday


# --- is_open_at: simple window ----------------------------------------------


def _simple_window():
    return hours([{"open": point(1, 11, 30), "close": point(1, 22, 0)}])


def test_is_open_at_within_window():
    assert oh.is_open_at(_simple_window(), 1, 12 * 60) is True


def test_is_open_at_before_window():
    assert oh.is_open_at(_simple_window(), 1, 9 * 60) is False


def test_is_open_at_at_close_boundary_is_closed():
    assert oh.is_open_at(_simple_window(), 1, 22 * 60) is False  # half-open close


def test_is_open_at_one_minute_before_close_is_open():
    assert oh.is_open_at(_simple_window(), 1, 22 * 60 - 1) is True


def test_is_open_at_closed_weekday_returns_false_not_none():
    assert oh.is_open_at(_simple_window(), 2, 12 * 60) is False


# --- is_open_at: overnight and week wrap ------------------------------------


def _overnight_window():
    # Friday 20:00 -> Saturday 02:00
    return hours([{"open": point(5, 20, 0), "close": point(6, 2, 0)}])


def test_is_open_at_overnight_friday_evening():
    assert oh.is_open_at(_overnight_window(), 5, 23 * 60) is True


def test_is_open_at_overnight_saturday_early_morning():
    assert oh.is_open_at(_overnight_window(), 6, 60) is True


def test_is_open_at_overnight_saturday_after_close():
    assert oh.is_open_at(_overnight_window(), 6, 3 * 60) is False


def test_is_open_at_saturday_into_sunday_week_wrap():
    week_wrap = hours([{"open": point(6, 22, 0), "close": point(0, 2, 0)}])
    assert oh.is_open_at(week_wrap, 0, 60) is True


# --- is_open_at: 24h open ----------------------------------------------------


def test_is_open_at_24h_open_place():
    always_open = hours([{"open": point(0, 0, 0)}])
    assert oh.is_open_at(always_open, 3, 0) is True
    assert oh.is_open_at(always_open, 6, 23 * 60 + 59) is True


# --- is_open_at: unknown / malformed -----------------------------------------


def test_is_open_at_none_hours_is_unknown():
    assert oh.is_open_at(None, 1, 720) is None


def test_is_open_at_empty_dict_is_unknown():
    assert oh.is_open_at({}, 1, 720) is None


def test_is_open_at_legacy_open_now_row_is_unknown():
    assert oh.is_open_at({"open_now": True}, 1, 720) is None


def test_is_open_at_empty_periods_list_is_unknown():
    assert oh.is_open_at({"periods": []}, 1, 720) is None


def test_is_open_at_garbage_periods_is_unknown():
    assert oh.is_open_at({"periods": "garbage"}, 1, 720) is None


def test_is_open_at_skips_period_missing_open():
    malformed = hours([{"close": point(1, 22, 0)}])
    assert oh.is_open_at(malformed, 1, 12 * 60) is False


# --- next_open_minute --------------------------------------------------------


def test_next_open_minute_already_open_returns_from_minute():
    assert oh.next_open_minute(_simple_window(), 1, 12 * 60, 20 * 60) == 12 * 60


def test_next_open_minute_opens_later_same_day():
    result = oh.next_open_minute(_simple_window(), 1, 9 * 60, 20 * 60)
    assert result == 11 * 60 + 30


def test_next_open_minute_opens_only_past_until_minute_returns_none():
    result = oh.next_open_minute(_simple_window(), 1, 9 * 60, 10 * 60)
    assert result is None


def test_next_open_minute_unknown_hours_returns_none():
    assert oh.next_open_minute(None, 1, 9 * 60, 20 * 60) is None
    assert oh.next_open_minute({"open_now": True}, 1, 9 * 60, 20 * 60) is None
