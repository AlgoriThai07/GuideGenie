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
    def _make(lat: float, lng: float, place_id: int = 1) -> Place:
        return Place(
            id=place_id,
            google_place_id=f"place-{place_id}",
            name=f"Place {place_id}",
            lat=lat,
            lng=lng,
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
    ) -> dps.PoolActivity:
        resolved_place = make_place(lat, lng, place_id=index + 1) if place is _UNSET else place
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
        )

    return _make


@pytest.fixture
def make_restaurant(make_place):
    def _make(index: int, name: str, meal_type: str, lat: float = 0.0, lng: float = 0.0) -> dps.PoolRestaurant:
        return dps.PoolRestaurant(
            index=index,
            name=name,
            meal_type=meal_type,
            description=None,
            estimated_cost=None,
            verified_cost=None,
            price_source=None,
            place=make_place(lat, lng, place_id=100 + index),
        )

    return _make


@pytest.fixture
def hotel(make_place):
    return dps.HotelInfo(
        name="Test Hotel",
        description="A hotel",
        estimated_cost_per_night=Decimal("100.00"),
        place=make_place(0.0, 0.0, place_id=0),
    )
