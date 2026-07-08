"""Google Places lookup service (Sprint 3).

Resolves LLM-proposed location names into real Places records via the Google
Places Text Search API, caches them in the ``places`` table, and logs every
external call as a ``ToolCall`` row. Pure service module — no FastAPI
dependencies. Never raises: a failed lookup returns ``None`` so a single bad
item never aborts the itinerary generation run.
"""

import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.place import Place
from app.models.tool_call import ToolCall

_TEXT_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"


class PlacesService:
    """Wraps the Google Places Text Search API."""

    @staticmethod
    def text_search(query: str, language: str = "en") -> dict[str, Any] | None:
        """Return the first Text Search result for ``query``, or ``None``."""
        try:
            response = requests.get(
                _TEXT_SEARCH_URL,
                params={
                    "query": query,
                    "language": language,
                    "key": settings.GOOGLE_PLACES_API_KEY,
                },
                timeout=10,
            )
            data = response.json()
        except Exception:  # noqa: BLE001 — network/JSON errors degrade to None
            return None

        if data.get("status") != "OK":
            return None

        results = data.get("results") or []
        if not results:
            return None
        return results[0]

    @staticmethod
    def find_or_create_place(
        db: Session,
        google_place_id: str,
        api_result: dict[str, Any],
    ) -> Place:
        """Return the cached ``Place`` for ``google_place_id``, creating it if new."""
        existing = (
            db.query(Place).filter_by(google_place_id=google_place_id).first()
        )
        if existing is not None:
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
    def resolve_item_place(
        db: Session,
        agent_run_id: int,
        location_name: str,
        destination: str,
    ) -> Place | None:
        """Resolve ``location_name`` in ``destination`` to a real ``Place``.

        Logs a ``ToolCall`` row for the attempt and never raises — any
        failure is recorded as a failed ``ToolCall`` and returns ``None``.
        """
        query = f"{location_name}, {destination}"
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
                        input_json={"query": query},
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
                    input_json={"query": query},
                    output_json={
                        "place_id": place.google_place_id,
                        "name": place.name,
                        "rating": place.rating,
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
                        input_json={"query": query},
                        error_message=f"Unexpected error: {e}",
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                        cache_hit=False,
                    )
                )
                db.commit()
            except Exception:  # noqa: BLE001 — logging itself must not raise
                db.rollback()
            return None
