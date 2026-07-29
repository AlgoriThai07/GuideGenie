"""Tests for app.services.route_service.

No real network calls: `requests.get` is monkeypatched everywhere. Verifies
Google Distance Matrix response parsing, the `mode` param is forwarded
correctly, graceful degradation to a None-filled matrix on failure, and the
pure nearest-neighbor ordering heuristic.
"""

from unittest.mock import MagicMock

import pytest

from app.models.agent import AgentRunStatus
from app.services.route_service import RouteService


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _ok_payload(rows):
    return {"status": "OK", "rows": rows}


def _row(*elements):
    return {"elements": [
        {"status": "OK", "duration": {"value": d}, "distance": {"value": m}}
        if d is not None else {"status": "ZERO_RESULTS"}
        for d, m in elements
    ]}


# --- _get_distance_matrix_full ---------------------------------------------


def test_get_distance_matrix_full_parses_durations_and_distances(monkeypatch):
    payload = _ok_payload([_row((600, 800), (1200, 1600))])
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse(payload),
    )
    minutes, meters = RouteService._get_distance_matrix_full(
        [(0.0, 0.0)], [(0.0, 0.0), (1.0, 1.0)], "walking"
    )
    assert minutes == [[10, 20]]
    assert meters == [[800, 1600]]


def test_get_distance_matrix_full_forwards_mode_param(monkeypatch):
    captured = {}

    def fake_get(url, params, timeout):
        captured["mode"] = params["mode"]
        return FakeResponse(_ok_payload([_row((60, 100))]))

    monkeypatch.setattr("app.services.route_service.requests.get", fake_get)
    RouteService._get_distance_matrix_full([(0.0, 0.0)], [(0.0, 0.0)], "transit")
    assert captured["mode"] == "transit"


def test_get_distance_matrix_full_marks_unresolved_elements_as_none(monkeypatch):
    payload = _ok_payload([_row((None, None), (300, 400))])
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse(payload),
    )
    minutes, meters = RouteService._get_distance_matrix_full(
        [(0.0, 0.0)], [(0.0, 0.0), (1.0, 1.0)], "walking"
    )
    assert minutes == [[None, 5]]
    assert meters == [[None, 400]]


def test_get_distance_matrix_full_degrades_to_none_matrix_on_non_ok_status(monkeypatch):
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse({"status": "REQUEST_DENIED"}),
    )
    minutes, meters = RouteService._get_distance_matrix_full(
        [(0.0, 0.0)], [(1.0, 1.0)], "walking"
    )
    assert minutes == [[None]]
    assert meters == [[None]]


def test_get_distance_matrix_full_degrades_to_none_matrix_on_network_exception(monkeypatch):
    def raise_error(*a, **kw):
        raise ConnectionError("network down")

    monkeypatch.setattr("app.services.route_service.requests.get", raise_error)
    minutes, meters = RouteService._get_distance_matrix_full(
        [(0.0, 0.0)], [(1.0, 1.0)], "walking"
    )
    assert minutes == [[None]]
    assert meters == [[None]]


# --- get_distance_matrix (public wrapper + ToolCall logging) ----------------


def test_get_distance_matrix_returns_minutes_only(monkeypatch):
    payload = _ok_payload([_row((600, 800))])
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse(payload),
    )
    matrix = RouteService.get_distance_matrix([(0.0, 0.0)], [(1.0, 1.0)])
    assert matrix == [[10]]


def test_get_distance_matrix_logs_tool_call_with_completed_status_on_success(monkeypatch):
    payload = _ok_payload([_row((600, 800))])
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse(payload),
    )
    logged = {}
    monkeypatch.setattr(
        RouteService,
        "_log_tool_call",
        staticmethod(lambda **kwargs: logged.update(kwargs)),
    )
    db = MagicMock()
    RouteService.get_distance_matrix([(0.0, 0.0)], [(1.0, 1.0)], agent_run_id=42, db=db)
    assert logged["status"] == AgentRunStatus.COMPLETED
    assert logged["agent_run_id"] == 42
    assert logged["error_message"] is None


def test_get_distance_matrix_logs_failed_status_when_nothing_resolves(monkeypatch):
    monkeypatch.setattr(
        "app.services.route_service.requests.get",
        lambda *a, **kw: FakeResponse({"status": "REQUEST_DENIED"}),
    )
    logged = {}
    monkeypatch.setattr(
        RouteService,
        "_log_tool_call",
        staticmethod(lambda **kwargs: logged.update(kwargs)),
    )
    db = MagicMock()
    RouteService.get_distance_matrix([(0.0, 0.0)], [(1.0, 1.0)], agent_run_id=42, db=db)
    assert logged["status"] == AgentRunStatus.FAILED
    assert logged["error_message"] is not None


# --- nearest_neighbor_order (pure) ------------------------------------------


def test_nearest_neighbor_order_visits_closest_unvisited_each_step():
    # 0 -> 2 (cost 1) -> 1 (cost 1) -> 3, skipping the direct 0->1 cost-10 edge
    matrix = [
        [0, 10, 1, 100],
        [10, 0, 1, 100],
        [1, 1, 0, 100],
        [100, 100, 100, 0],
    ]
    order = RouteService.nearest_neighbor_order(matrix, start_index=0)
    assert order[0] == 0
    assert set(order) == {0, 1, 2, 3}
    assert order[-1] == 3  # only reachable via the large-cost edges last


def test_nearest_neighbor_order_treats_none_as_very_large_cost():
    matrix = [
        [0, None, 5],
        [None, 0, 1],
        [5, 1, 0],
    ]
    order = RouteService.nearest_neighbor_order(matrix, start_index=0)
    # from 0, the only known cost is to 2 (5); None is worse than any real cost
    assert order == [0, 2, 1]
