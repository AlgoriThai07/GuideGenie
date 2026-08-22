"""Shared fixtures for the day-planner / route-service test suite.

Everything here is a pure in-memory stand-in — no DB session, no network.
`Place` and `PoolActivity`/`PoolRestaurant`/`HotelInfo` are real dataclasses/
ORM objects (SQLAlchemy models can be instantiated without a session), so
tests exercise the real shapes the service code expects.
"""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.models.itinerary import ItineraryItemPriority, ItineraryItemType, WalkingIntensity
from app.models.place import Place
from app.services import day_planner_service as dps
from app.services.route_service import RouteService

_UNSET = object()


@pytest.fixture
def db():
    """Opaque session stand-in. Real code only ever passes it through to
    ``RouteService._log_tool_call`` (add/commit), which tests stub out."""
    return MagicMock()


@pytest.fixture(autouse=True)
def stub_log_tool_call(monkeypatch):
    """Silence ToolCall logging in every test — it would otherwise call
    ``db.add``/``db.commit`` on our MagicMock db for no reason."""
    monkeypatch.setattr(RouteService, "_log_tool_call", staticmethod(lambda **kwargs: None))


@pytest.fixture
def make_place():
    def _make(lat: float, lng: float, place_id: int = 1, *, opening_hours: dict | None = None) -> Place:
        return Place(
            id=place_id,
            google_place_id=f"place-{place_id}",
            name=f"Place {place_id}",
            lat=lat,
            lng=lng,
            opening_hours=opening_hours,
        )

    return _make


@pytest.fixture
def make_activity(make_place):
    def _make(
        index: int,
        name: str,
        lat: float,
        lng: float,
        *,
        duration_minutes: int = 90,
        priority: ItineraryItemPriority = ItineraryItemPriority.REQUIRED,
        item_type: ItineraryItemType = ItineraryItemType.ACTIVITY,
        place=_UNSET,
        opening_hours: dict | None = None,
        best_time_of_day: str = "any",
    ) -> dps.PoolActivity:
        resolved_place = (
            make_place(lat, lng, place_id=index + 1, opening_hours=opening_hours)
            if place is _UNSET
            else place
        )
        return dps.PoolActivity(
            index=index,
            name=name,
            type=item_type,
            duration_minutes=duration_minutes,
            priority=priority,
            walking_intensity=WalkingIntensity.MEDIUM,
            description=None,
            estimated_cost=None,
            verified_cost=None,
            price_source=None,
            place=resolved_place,
            best_time_of_day=best_time_of_day,
        )

    return _make


@pytest.fixture
def make_restaurant(make_place):
    def _make(
        index: int,
        name: str,
        meal_type: str,
        lat: float = 0.0,
        lng: float = 0.0,
        *,
        opening_hours: dict | None = None,
    ) -> dps.PoolRestaurant:
        return dps.PoolRestaurant(
            index=index,
            name=name,
            meal_type=meal_type,
            description=None,
            estimated_cost=None,
            verified_cost=None,
            price_source=None,
            place=make_place(lat, lng, place_id=100 + index, opening_hours=opening_hours),
        )

    return _make


@pytest.fixture
def weekly_hours():
    """Build a v1-shaped ``regularOpeningHours`` dict from
    ``{google_weekday: (open_minute, close_minute)}`` (close on the same day
    as open; use ``day_planner_service`` / ``opening_hours`` helpers directly
    for overnight/24h test cases)."""

    def _make(day_windows: dict[int, tuple[int, int]]) -> dict:
        periods = []
        for day, (open_min, close_min) in day_windows.items():
            periods.append(
                {
                    "open": {"day": day, "hour": open_min // 60, "minute": open_min % 60},
                    "close": {"day": day, "hour": close_min // 60, "minute": close_min % 60},
                }
            )
        return {"periods": periods}

    return _make


@pytest.fixture
def hotel(make_place):
    return dps.HotelInfo(
        name="Test Hotel",
        description="A hotel",
        estimated_cost_per_night=Decimal("100.00"),
        place=make_place(0.0, 0.0, place_id=0),
    )
