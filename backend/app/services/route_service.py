"""Route optimization service (Sprint 4).

Wraps the Google Distance Matrix API to compute real travel times between
stops, provides a pure nearest-neighbor ordering heuristic, and reorders a
day's flexible items (activities/events) around fixed anchors (hotel, meals,
rest, free time, transport). Pure service module — no FastAPI dependencies.
Every external call is logged as a ``ToolCall`` row. Never raises: any
failure degrades to an unmodified result so a single bad day never aborts
the itinerary generation run.
"""

import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.itinerary import ItineraryItem, ItineraryItemType
from app.models.place import Place
from app.models.tool_call import ToolCall

_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

_ANCHOR_TYPES = {
    ItineraryItemType.HOTEL,
    ItineraryItemType.MEAL,
    ItineraryItemType.REST,
    ItineraryItemType.FREE_TIME,
    ItineraryItemType.TRANSPORT,
}
_FLEXIBLE_TYPES = {ItineraryItemType.ACTIVITY, ItineraryItemType.EVENT}

_LARGE_COST = 9_999_999


class RouteService:
    """Wraps the Google Distance Matrix API and route ordering heuristics."""

    @staticmethod
    def _get_distance_matrix_full(
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
        mode: str,
    ) -> tuple[list[list[int | None]], list[list[int | None]]]:
        """Return ``(minutes_matrix, meters_matrix)`` for ``origins`` x ``destinations``.

        On any exception or non-``OK`` API response, both matrices are
        returned full of ``None``. Never raises.
        """
        n, m = len(origins), len(destinations)
        minutes_matrix: list[list[int | None]] = [[None] * m for _ in range(n)]
        meters_matrix: list[list[int | None]] = [[None] * m for _ in range(n)]

        try:
            response = requests.get(
                _DISTANCE_MATRIX_URL,
                params={
                    "origins": "|".join(f"{lat},{lng}" for lat, lng in origins),
                    "destinations": "|".join(
                        f"{lat},{lng}" for lat, lng in destinations
                    ),
                    "mode": mode,
                    "units": "metric",
                    "key": settings.GOOGLE_ROUTES_API_KEY,
                },
                timeout=10,
            )
            data = response.json()
        except Exception:  # noqa: BLE001 — network/JSON errors degrade to None matrix
            return minutes_matrix, meters_matrix

        if data.get("status") != "OK":
            return minutes_matrix, meters_matrix

        rows = data.get("rows") or []
        for i, row in enumerate(rows):
            elements = row.get("elements") or []
            for j, element in enumerate(elements):
                if element.get("status") != "OK":
                    continue
                duration = element.get("duration", {}).get("value")
                distance = element.get("distance", {}).get("value")
                if duration is not None:
                    minutes_matrix[i][j] = round(duration / 60)
                if distance is not None:
                    meters_matrix[i][j] = distance

        return minutes_matrix, meters_matrix

    @staticmethod
    def get_distance_matrix(
        origins: list[tuple[float, float]],
        destinations: list[tuple[float, float]],
        mode: str = "walking",
        agent_run_id: int | None = None,
        db: Session | None = None,
    ) -> list[list[int | None]]:
        """Return an N x M matrix of travel time in minutes, ``origins`` x ``destinations``.

        ``matrix[i][j]`` is ``None`` if the API returned no route for that
        pair. If ``agent_run_id`` and ``db`` are provided, logs a
        ``ToolCall`` row. Never raises.
        """
        t0 = time.perf_counter()
        n, m = len(origins), len(destinations)

        try:
            minutes_matrix, _ = RouteService._get_distance_matrix_full(
                origins, destinations, mode
            )
            latency_ms = int((time.perf_counter() - t0) * 1000)
            pairs_resolved = sum(
                1 for row in minutes_matrix for value in row if value is not None
            )
            status = (
                AgentRunStatus.COMPLETED if pairs_resolved > 0 else AgentRunStatus.FAILED
            )

            if agent_run_id is not None and db is not None:
                RouteService._log_tool_call(
                    db=db,
                    agent_run_id=agent_run_id,
                    status=status,
                    input_json={"origins": n, "destinations": m, "mode": mode},
                    output_json={"pairs_resolved": pairs_resolved},
                    error_message=None
                    if status == AgentRunStatus.COMPLETED
                    else "No routes resolved from Google Distance Matrix",
                    latency_ms=latency_ms,
                )

            return minutes_matrix

        except Exception as e:  # noqa: BLE001 — a bad request must not abort the run
            latency_ms = int((time.perf_counter() - t0) * 1000)
            if agent_run_id is not None and db is not None:
                RouteService._log_tool_call(
                    db=db,
                    agent_run_id=agent_run_id,
                    status=AgentRunStatus.FAILED,
                    input_json={"origins": n, "destinations": m, "mode": mode},
                    output_json=None,
                    error_message=f"Unexpected error: {e}",
                    latency_ms=latency_ms,
                )
            return [[None] * m for _ in range(n)]

    @staticmethod
    def _log_tool_call(
        db: Session,
        agent_run_id: int,
        status: AgentRunStatus,
        input_json: dict[str, Any] | None,
        output_json: dict[str, Any] | None,
        error_message: str | None,
        latency_ms: int | None,
    ) -> None:
        """Log a ``google_distance_matrix`` ``ToolCall`` row. Never raises."""
        try:
            db.add(
                ToolCall(
                    agent_run_id=agent_run_id,
                    tool_name="google_distance_matrix",
                    status=status,
                    input_json=input_json,
                    output_json=output_json,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    cache_hit=False,
                )
            )
            db.commit()
        except Exception:  # noqa: BLE001 — logging itself must not raise
            db.rollback()

    @staticmethod
    def nearest_neighbor_order(
        matrix: list[list[int | None]],
        start_index: int = 0,
    ) -> list[int]:
        """Return a visit order over ``range(len(matrix))`` via greedy nearest-neighbor.

        Pure function — no DB, no API calls. ``None`` entries are treated as
        a very large cost so a complete ordering is always produced.
        """
        n = len(matrix)
        visited = [False] * n
        order = [start_index]
        visited[start_index] = True
        current = start_index

        for _ in range(n - 1):
            best_index = None
            best_cost = None
            for candidate in range(n):
                if visited[candidate]:
                    continue
                cost = matrix[current][candidate]
                if cost is None:
                    cost = _LARGE_COST
                if best_cost is None or cost < best_cost:
                    best_cost = cost
                    best_index = candidate
            order.append(best_index)
            visited[best_index] = True
            current = best_index

        return order

    @staticmethod
    def optimize_day(
        db: Session,
        agent_run_id: int,
        items: list[ItineraryItem],
        places_map: dict[int, Place],
        travel_mode: str = "walking",
    ) -> list[ItineraryItem]:
        """Reorder a day's flexible items by nearest-neighbor travel time.

        Anchors (hotel, meal, rest, free_time, transport) and items without a
        resolved place keep their relative positions; only activity/event
        items with a resolved place are reordered. Populates
        ``travel_time_to_next_minutes``, ``distance_to_next_meters``, and
        ``travel_mode_to_next`` on the returned items. Never raises — any
        failure returns the original list unmodified.
        """
        try:
            return RouteService._optimize_day_inner(
                db, agent_run_id, items, places_map, travel_mode
            )
        except Exception:  # noqa: BLE001 — a bad day must not abort the run
            return items

    @staticmethod
    def _optimize_day_inner(
        db: Session,
        agent_run_id: int,
        items: list[ItineraryItem],
        places_map: dict[int, Place],
        travel_mode: str,
    ) -> list[ItineraryItem]:
        if not items:
            return items

        flexible_positions: list[int] = []
        for i, item in enumerate(items):
            is_flexible = item.type in _FLEXIBLE_TYPES and item.place_id is not None
            if is_flexible:
                flexible_positions.append(i)

        flexible_items = [items[i] for i in flexible_positions]

        # Matrix of minute costs between flexible items, indexed by position
        # within `flexible_items` (i.e. matrix[a][b] not matrix[orig_i][orig_j]).
        flex_minutes: list[list[int | None]] | None = None
        flex_meters: list[list[int | None]] | None = None

        if len(flexible_items) >= 2:
            coords = [
                (places_map[item.place_id].lat, places_map[item.place_id].lng)
                for item in flexible_items
            ]
            flex_minutes, flex_meters = RouteService._get_distance_matrix_full(
                coords, coords, travel_mode
            )
            RouteService._log_tool_call(
                db=db,
                agent_run_id=agent_run_id,
                status=AgentRunStatus.COMPLETED
                if any(
                    v is not None for row in flex_minutes for v in row
                )
                else AgentRunStatus.FAILED,
                input_json={
                    "origins": len(coords),
                    "destinations": len(coords),
                    "mode": travel_mode,
                },
                output_json={
                    "pairs_resolved": sum(
                        1 for row in flex_minutes for v in row if v is not None
                    )
                },
                error_message=None,
                latency_ms=None,
            )

            order = RouteService.nearest_neighbor_order(flex_minutes, start_index=0)
            reordered_flexible = [flexible_items[i] for i in order]

            # Re-stitch: fill original flexible slots with the new sequence.
            stitched = list(items)
            for slot, item in zip(flexible_positions, reordered_flexible):
                stitched[slot] = item

            # Map each stitched flexible item back to its index within
            # `flexible_items` so the flex_minutes/flex_meters matrix can be
            # reused for consecutive flexible-flexible pairs.
            flex_index_by_item_id = {
                id(item): i for i, item in enumerate(flexible_items)
            }
        else:
            stitched = list(items)
            flex_index_by_item_id = {}

        # Compute consecutive-pair travel times on the final stitched order.
        for k in range(len(stitched) - 1):
            current_item = stitched[k]
            next_item = stitched[k + 1]

            if current_item.place_id is None or next_item.place_id is None:
                continue

            current_flex_idx = flex_index_by_item_id.get(id(current_item))
            next_flex_idx = flex_index_by_item_id.get(id(next_item))

            if (
                flex_minutes is not None
                and current_flex_idx is not None
                and next_flex_idx is not None
            ):
                minutes = flex_minutes[current_flex_idx][next_flex_idx]
                meters = flex_meters[current_flex_idx][next_flex_idx]
            else:
                current_place = places_map[current_item.place_id]
                next_place = places_map[next_item.place_id]
                single_minutes, single_meters = RouteService._get_distance_matrix_full(
                    [(current_place.lat, current_place.lng)],
                    [(next_place.lat, next_place.lng)],
                    travel_mode,
                )
                RouteService._log_tool_call(
                    db=db,
                    agent_run_id=agent_run_id,
                    status=AgentRunStatus.COMPLETED
                    if single_minutes[0][0] is not None
                    else AgentRunStatus.FAILED,
                    input_json={"origins": 1, "destinations": 1, "mode": travel_mode},
                    output_json={
                        "pairs_resolved": 1 if single_minutes[0][0] is not None else 0
                    },
                    error_message=None,
                    latency_ms=None,
                )
                minutes = single_minutes[0][0]
                meters = single_meters[0][0]

            current_item.travel_time_to_next_minutes = minutes
            current_item.distance_to_next_meters = meters
            current_item.travel_mode_to_next = travel_mode

        stitched[-1].travel_time_to_next_minutes = None
        stitched[-1].distance_to_next_meters = None
        stitched[-1].travel_mode_to_next = None

        return stitched
