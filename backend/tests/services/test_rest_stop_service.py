"""Tests for the weekday-aware preference added to RestStopService.find_rest_stop
in Sprint 6. Candidate discovery itself (nearby_search/seating confidence) is
covered indirectly here by monkeypatching nearby_search; HTTP-shape testing
for the v1 migration lives in test_places_service.py (normalize_v1_place is
shared by both services).
"""

from app.services import rest_stop_service as rss


def _candidate(name: str, place_id: str, lat: float, lng: float, rating: float, opening_hours=None):
    return {
        "place_id": place_id,
        "name": name,
        "geometry": {"location": {"lat": lat, "lng": lng}},
        "rating": rating,
        "types": ["cafe"],
        "opening_hours": opening_hours,
    }


def _hours_closed_all_day(day: int):
    # A period on a different day than the one under test -> confirmed closed.
    other_day = (day + 1) % 7
    return {"periods": [{"open": {"day": other_day, "hour": 9, "minute": 0}, "close": {"day": other_day, "hour": 17, "minute": 0}}]}


def _hours_open_at_15(day: int):
    return {"periods": [{"open": {"day": day, "hour": 9, "minute": 0}, "close": {"day": day, "hour": 22, "minute": 0}}]}


def _no_cached_place(db):
    """The shared `db` fixture is a bare MagicMock, whose `.query(...).first()`
    would otherwise return a truthy MagicMock instead of None — steering
    `find_or_create_place` into its "existing" branch and returning a mock
    object instead of a real `Place`. Force the cache-miss path so a real
    `Place` gets constructed from the candidate dict."""
    db.query.return_value.filter_by.return_value.first.return_value = None


def test_find_rest_stop_prefers_open_candidate_over_higher_confidence_closed(monkeypatch, db):
    _no_cached_place(db)
    weekday = 1  # Monday
    closed_but_better = _candidate(
        "Fancy Cafe", "closed-1", 0.0, 0.001, rating=4.8, opening_hours=_hours_closed_all_day(weekday)
    )
    open_but_worse = _candidate(
        "Plain Park", "open-1", 0.0, 0.0011, rating=3.9, opening_hours=_hours_open_at_15(weekday)
    )
    # seating_confidence_score prefers cafe (0.85+bonus) over park (0.40), so
    # without hours-awareness the closed cafe would win.
    monkeypatch.setattr(rss, "nearby_search", lambda *_args, **_kwargs: [closed_but_better, open_but_worse])

    place, confidence = rss.find_rest_stop(
        db, 1, 0.0, 0.001,
        origin_coord=(0.0, 0.0), dest_coord=(0.0, 0.002),
        original_travel_minutes=40, weekday=weekday, check_minute=15 * 60,
    )
    assert place is not None
    assert place.google_place_id == "open-1"


def test_find_rest_stop_returns_best_confidence_when_all_closed(monkeypatch, db):
    _no_cached_place(db)
    weekday = 1
    cafe_a = _candidate("Cafe A", "a", 0.0, 0.001, rating=4.8, opening_hours=_hours_closed_all_day(weekday))
    cafe_b = _candidate("Cafe B", "b", 0.0, 0.0011, rating=3.9, opening_hours=_hours_closed_all_day(weekday))
    monkeypatch.setattr(rss, "nearby_search", lambda *_args, **_kwargs: [cafe_a, cafe_b])

    place, confidence = rss.find_rest_stop(
        db, 1, 0.0, 0.001,
        origin_coord=(0.0, 0.0), dest_coord=(0.0, 0.002),
        original_travel_minutes=40, weekday=weekday, check_minute=15 * 60,
    )
    assert place is not None
    assert place.google_place_id == "a"  # higher confidence, since nothing is open


def test_find_rest_stop_ignores_weekday_when_not_provided(monkeypatch, db):
    _no_cached_place(db)
    weekday = 1
    closed = _candidate("Cafe A", "a", 0.0, 0.001, rating=4.8, opening_hours=_hours_closed_all_day(weekday))
    monkeypatch.setattr(rss, "nearby_search", lambda *_args, **_kwargs: [closed])

    place, confidence = rss.find_rest_stop(
        db, 1, 0.0, 0.001,
        origin_coord=(0.0, 0.0), dest_coord=(0.0, 0.002),
        original_travel_minutes=40,
    )
    assert place is not None
    assert place.google_place_id == "a"
