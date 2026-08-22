"""Google Places lookup service (Sprint 3, migrated to Places API (New) v1 in Sprint 6).

Resolves LLM-proposed location names into real Places records via the Google
Places API (New) Text Search endpoint, caches them in the ``places`` table,
and logs every external call as a ``ToolCall`` row. Pure service module — no
FastAPI dependencies. Never raises: a failed lookup returns ``None`` so a
single bad item never aborts the itinerary generation run.
"""

import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.place import Place
from app.models.tool_call import ToolCall

_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"

# Requested for both Text Search and Nearby Search (rest_stop_service reuses
# this constant) so opening hours arrive in the same call as everything else
# — no extra Place Details request per venue.
PLACE_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.rating,places.priceLevel,places.types,places.regularOpeningHours"
)

# v1 returns a string enum; the rest of the codebase (Place.price_level is an
# Integer column, PlaceRead.price_level: int) expects the legacy 0-4 scale.
_PRICE_LEVEL_MAP: dict[str, int] = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


def normalize_v1_place(v1_place: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Places API (New) place object to the legacy result shape the
    rest of the codebase consumes (``place_id``, ``name``,
    ``formatted_address``, ``geometry.location``, ``rating``, ``price_level``,
    ``types``, ``opening_hours``).

    Returns ``None`` if the place is missing an id or a display name (
    ``Place.name`` is non-nullable).
    """
    place_id = v1_place.get("id")
    display_name = v1_place.get("displayName")
    name = display_name.get("text") if isinstance(display_name, dict) else None
    if not place_id or not name:
        return None

    location = v1_place.get("location") or {}
    price_level = _PRICE_LEVEL_MAP.get(v1_place.get("priceLevel"))

    return {
        "place_id": place_id,
        "name": name,
        "formatted_address": v1_place.get("formattedAddress"),
        "geometry": {
            "location": {
                "lat": location.get("latitude"),
                "lng": location.get("longitude"),
            }
        },
        "rating": v1_place.get("rating"),
        "price_level": price_level,
        "types": v1_place.get("types") or [],
        "opening_hours": v1_place.get("regularOpeningHours"),
    }


class PlacesService:
    """Wraps the Google Places API (New) Text Search endpoint."""

    @staticmethod
    def text_search(query: str, language: str = "en") -> dict[str, Any] | None:
        """Return the first Text Search result for ``query`` (normalized to
        the legacy result shape), or ``None``."""
        try:
            response = requests.post(
                _TEXT_SEARCH_URL,
                json={"textQuery": query, "languageCode": language, "pageSize": 1},
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
                    "X-Goog-FieldMask": PLACE_FIELD_MASK,
                },
                timeout=10,
            )
        except Exception:  # noqa: BLE001 — network errors degrade to None
            return None

        if response.status_code != 200:
            return None

        try:
            data = response.json()
        except Exception:  # noqa: BLE001 — malformed JSON degrades to None
            return None

        places = data.get("places") or []
        if not places:
            return None
        return normalize_v1_place(places[0])

    @staticmethod
    def find_or_create_place(
        db: Session,
        google_place_id: str,
        api_result: dict[str, Any],
    ) -> Place:
        """Return the cached ``Place`` for ``google_place_id``, creating it if
        new. If the cached row predates hours data (legacy ``{"open_now":
        ...}`` or ``None``) and the fresh result has real periods, enrich it
        in place so old rows self-heal on the next generation run."""
        existing = (
            db.query(Place).filter_by(google_place_id=google_place_id).first()
        )
        if existing is not None:
            fresh_hours = api_result.get("opening_hours")
            existing_periods = (existing.opening_hours or {}).get("periods") if isinstance(existing.opening_hours, dict) else None
            if isinstance(fresh_hours, dict) and fresh_hours.get("periods") and not existing_periods:
                existing.opening_hours = fresh_hours
                if api_result.get("rating") is not None:
                    existing.rating = api_result["rating"]
                if api_result.get("price_level") is not None:
                    existing.price_level = api_result["price_level"]
                db.commit()
                db.refresh(existing)
            return existing

        location = api_result.get("geometry", {}).get("location", {})
        place = Place(
            google_place_id=api_result["place_id"],
            name=api_result["name"],
            address=api_result.get("formatted_address"),
            lat=location.get("lat"),
            lng=location.get("lng"),
            rating=api_result.get("rating"),
            price_level=api_result.get("price_level"),
            types=api_result.get("types", []),
            opening_hours=api_result.get("opening_hours"),
        )
        db.add(place)
        db.commit()
        db.refresh(place)
        return place

    @staticmethod
    def _attempt_text_search(
        db: Session, agent_run_id: int, query: str
    ) -> Place | None:
        """Run one Text Search attempt for ``query``, logging a ``ToolCall``.

        Never raises — any failure is recorded as a failed ``ToolCall`` and
        returns ``None``.
        """
        t0 = time.perf_counter()
        try:
            result = PlacesService.text_search(query)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            if result is None:
                db.add(
                    ToolCall(
                        agent_run_id=agent_run_id,
                        tool_name="google_places_text_search",
                        status=AgentRunStatus.FAILED,
                        input_json={"query": query, "api_version": "v1"},
                        error_message="No results from Google Places Text Search",
                        latency_ms=latency_ms,
                        cache_hit=False,
                    )
                )
                db.commit()
                return None

            google_place_id = result["place_id"]
            cache_hit = (
                db.query(Place).filter_by(google_place_id=google_place_id).first()
                is not None
            )
            place = PlacesService.find_or_create_place(db, google_place_id, result)

            db.add(
                ToolCall(
                    agent_run_id=agent_run_id,
                    tool_name="google_places_text_search",
                    status=AgentRunStatus.COMPLETED,
                    input_json={"query": query, "api_version": "v1"},
                    output_json={
                        "place_id": place.google_place_id,
                        "name": place.name,
                        "rating": place.rating,
                        "has_hours": bool((place.opening_hours or {}).get("periods")) if isinstance(place.opening_hours, dict) else False,
                    },
                    latency_ms=latency_ms,
                    cache_hit=cache_hit,
                )
            )
            db.commit()
            return place

        except Exception as e:  # noqa: BLE001 — a bad item must not abort the run
            db.rollback()
            try:
                db.add(
                    ToolCall(
                        agent_run_id=agent_run_id,
                        tool_name="google_places_text_search",
                        status=AgentRunStatus.FAILED,
                        input_json={"query": query, "api_version": "v1"},
                        error_message=f"Unexpected error: {e}",
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        cache_hit=False,
                    )
                )
                db.commit()
            except Exception:  # noqa: BLE001 — logging itself must not raise
                db.rollback()
            return None

    @staticmethod
    def resolve_item_place(
        db: Session,
        agent_run_id: int,
        location_name: str,
        destination: str,
    ) -> Place | None:
        """Resolve ``location_name`` in ``destination`` to a real ``Place``.

        Tries ``"{location_name}, {destination}"`` first, then falls back to
        ``location_name`` alone if that returns no results — some venue
        names are specific enough that appending the destination causes a
        zero-result Text Search response. Each attempt logs its own
        ``ToolCall`` row. Never raises.
        """
        queries = [f"{location_name}, {destination}", location_name]
        for query in queries:
            place = PlacesService._attempt_text_search(db, agent_run_id, query)
            if place is not None:
                return place
        return None
