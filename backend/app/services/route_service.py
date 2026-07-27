"""Route optimization service (Sprint 4).

Wraps the Google Distance Matrix API to compute real travel times between
stops and provides a pure nearest-neighbor ordering heuristic. Pure service
module — no FastAPI dependencies. Every external call is logged as a
``ToolCall`` row. Never raises: any failure degrades to a ``None``-filled
matrix so a single bad request never aborts the itinerary generation run.

Day clustering, meal assignment, and time-block scheduling live in
``app.services.day_planner_service``, which calls into this module for
travel-time matrices and ordering.
"""

import time
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRunStatus
from app.models.tool_call import ToolCall

_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

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
