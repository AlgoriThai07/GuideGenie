"""Rest-stop discovery service (Sprint 5).

Finds nearby Places candidates suitable for a scheduled rest break. This
module contains no FastAPI dependencies and degrades to ``None`` results when
Google Places, persistence, or candidate data is unavailable.
"""

import math
import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.place import Place
from app.models.tool_call import ToolCall
from app.services.places_service import PlacesService

_NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_WALKING_METERS_PER_MINUTE = 80

SEATING_CONFIDENCE: dict[str, float] = {
    "cafe": 0.85,
    "food_court": 0.80,
    "shopping_mall": 0.75,
    "bakery": 0.70,
    "restaurant": 0.70,
    "convenience_store": 0.65,
    "library": 0.60,
    "park": 0.40,
}


def seating_confidence_score(api_result: dict[str, Any]) -> float:
    """Return seating confidence from Google Places types and rating."""
    types = api_result.get("types") or []
    if not isinstance(types, list):
        types = []
    base_prior = max((SEATING_CONFIDENCE.get(place_type, 0.0) for place_type in types), default=0.0)
    rating = api_result.get("rating")
    if not isinstance(rating, (int, float)):
        rating = 0.0
    rating_bonus = 0.10 if rating >= 4.5 else 0.05 if rating >= 4.2 else 0.0
    return min(1.0, base_prior + rating_bonus)


def nearby_search(
    lat: float,
    lng: float,
    radius_meters: int = 400,
    language: str = "en",
) -> list[dict[str, Any]]:
    """Return nearby Google Places results, or an empty list on failure."""
    try:
        response = requests.get(
            _NEARBY_SEARCH_URL,
            params={
                "location": f"{lat},{lng}",
                "radius": radius_meters,
                "language": language,
                "key": settings.GOOGLE_PLACES_API_KEY,
            },
            timeout=10,
        )
        data = response.json()
    except Exception:  # noqa: BLE001 - network/JSON errors degrade to empty list
        return []

    if data.get("status") != "OK":
        return []

    return data.get("results") or []


def _haversine_meters(
    origin: tuple[float, float], destination: tuple[float, float]
) -> float:
    """Return great-circle distance in meters. Pure helper."""
    lat1, lng1, lat2, lng2 = map(
        math.radians, (*origin, *destination)
    )
    lat_delta = lat2 - lat1
    lng_delta = lng2 - lng1
    value = (
        math.sin(lat_delta / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(lng_delta / 2) ** 2
    )
    return 6_371_000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def _log_nearby_search(
    db: Session,
    agent_run_id: int,
    midpoint_lat: float,
    midpoint_lng: float,
    candidate_count: int,
    latency_ms: int,
) -> None:
    """Commit one nearby-search ``ToolCall``. Logging failures never raise."""
    try:
        status = (
            AgentRunStatus.COMPLETED
            if candidate_count
            else AgentRunStatus.FAILED
        )
        db.add(
            ToolCall(
                agent_run_id=agent_run_id,
                tool_name="google_places_nearby_search",
                status=status,
                input_json={"lat": midpoint_lat, "lng": midpoint_lng, "radius": 400},
                output_json={"candidates": candidate_count},
                error_message=None if candidate_count else "No results from Google Places Nearby Search",
                latency_ms=latency_ms,
                cache_hit=False,
            )
        )
        db.commit()
    except Exception:  # noqa: BLE001 - logging must not abort rest-stop search
        db.rollback()


def find_rest_stop(
    db: Session,
    agent_run_id: int,
    midpoint_lat: float,
    midpoint_lng: float,
    origin_coord: tuple[float, float],
    dest_coord: tuple[float, float],
    original_travel_minutes: int,
    max_detour_minutes: int = 10,
    min_rating: float = 3.8,
) -> tuple[Place | None, float | None]:
    """Find, cache, and return best low-detour rest stop. Never raises."""
    t0 = time.perf_counter()
    try:
        results = nearby_search(midpoint_lat, midpoint_lng, radius_meters=400)
    except Exception:  # noqa: BLE001 - keep exactly one log attempt even if patched call fails
        results = []
    _log_nearby_search(
        db,
        agent_run_id,
        midpoint_lat,
        midpoint_lng,
        len(results),
        int((time.perf_counter() - t0) * 1000),
    )

    try:
        direct_meters = _haversine_meters(origin_coord, dest_coord)
        candidates: list[tuple[dict[str, Any], float]] = []
        for result in results:
            location = result.get("geometry", {}).get("location", {})
            candidate_lat = location.get("lat")
            candidate_lng = location.get("lng")
            rating = result.get("rating")
            types = result.get("types") or []
            if (
                not isinstance(types, list)
                or not (set(types) & SEATING_CONFIDENCE.keys())
                or not isinstance(rating, (int, float))
                or rating < min_rating
                or candidate_lat is None
                or candidate_lng is None
            ):
                continue

            detour_meters = (
                _haversine_meters(origin_coord, (candidate_lat, candidate_lng))
                + _haversine_meters((candidate_lat, candidate_lng), dest_coord)
                - direct_meters
            )
            if detour_meters / _WALKING_METERS_PER_MINUTE <= max_detour_minutes:
                candidates.append((result, seating_confidence_score(result)))

        if not candidates:
            return None, None

        winner, confidence = max(candidates, key=lambda candidate: candidate[1])
        google_place_id = winner.get("place_id")
        if not google_place_id:
            return None, None
        place = PlacesService.find_or_create_place(db, google_place_id, winner)
        return place, confidence
    except Exception:  # noqa: BLE001 - a bad candidate/upsert must not abort planning
        db.rollback()
        return None, None


class RestStopService:
    """Namespace compatible with other GuideGenie service classes."""

    seating_confidence_score = staticmethod(seating_confidence_score)
    nearby_search = staticmethod(nearby_search)
    find_rest_stop = staticmethod(find_rest_stop)
