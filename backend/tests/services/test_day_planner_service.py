"""Tests for app.services.day_planner_service.

Focus areas:
  - geometry/time helpers (pure math)
  - clustering (_kmeans_labels / _balance_clusters / _order_clusters)
  - within-day sequencing, including the max-walk-minutes -> transit/driving
    fallback added for long gaps between consecutive stops
  - time-block scheduling (_build_day_items), including hours-aware
    lunch/dinner/activity handling
  - the plan_days entry point end-to-end, including graceful degradation
"""

import datetime
from decimal import Decimal

import pytest

from app.models.itinerary import ItineraryItemPriority, ItineraryItemType
from app.services import day_planner_service as dps
from app.services.day_planner_service import DayPlannerService
from app.services.route_service import RouteService


# --- geometry / time helpers --------------------------------------------------


def test_haversine_zero_distance():
    assert dps._haversine_meters((0.0, 0.0), (0.0, 0.0)) == 0.0


def test_haversine_one_degree_longitude_at_equator():
    meters = dps._haversine_meters((0.0, 0.0), (0.0, 1.0))
    assert 110_000 < meters < 112_000  # ~111.32 km per degree at the equator


def test_midpoint_uses_arithmetic_average():
    assert dps._midpoint((10.0, 20.0), (14.0, 28.0)) == (12.0, 24.0)


def test_ceil5_rounds_up_to_next_multiple_of_five():
    assert dps._ceil5(0) == 0
    assert dps._ceil5(1) == 5
    assert dps._ceil5(5) == 5
    assert dps._ceil5(6) == 10


def test_fmt_time_formats_and_wraps_past_midnight():
    assert dps._fmt_time(9 * 60) == "09:00"
    assert dps._fmt_time(9 * 60 + 5) == "09:05"
    assert dps._fmt_time(25 * 60) == "01:00"  # wraps modulo 24h


# --- clustering ----------------------------------------------------------------


def test_kmeans_labels_splits_two_tight_groups_into_two_clusters():
    points = [
        (0.0, 0.0), (0.0, 0.001), (0.001, 0.0),  # cluster A
        (10.0, 10.0), (10.0, 10.001), (10.001, 10.0),  # cluster B
    ]
    labels = dps._kmeans_labels(points, k=2)
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]


def test_kmeans_labels_k_greater_equal_n_returns_identity():
    points = [(0.0, 0.0), (1.0, 1.0)]
    assert dps._kmeans_labels(points, k=5) == [0, 1]


def test_balance_clusters_caps_every_cluster_at_ceil_n_over_k():
    points = [(0.0, i * 0.001) for i in range(6)]  # all near each other
    labels = [0] * 6  # everything dumped in cluster 0 on purpose
    balanced = dps._balance_clusters(labels, points, k=2)
    sizes = [balanced.count(c) for c in range(2)]
    assert max(sizes) <= 3  # ceil(6/2)
    assert sum(sizes) == 6


def test_order_clusters_visits_nearest_centroid_first_from_hotel():
    # cluster 0 centroid far from hotel, cluster 1 centroid near hotel
    points = [(0.0, 0.0), (0.0, 0.001), (5.0, 5.0), (5.0, 5.001)]
    labels = [1, 1, 0, 0]
    order = dps._order_clusters(labels, points, k=2, hotel_coord=(0.0, 0.0))
    assert order == [1, 0]


# --- within-day sequencing: max-walk-minutes -> alt-mode fallback -------------


def _walking_matrix(activities, slow_pairs):
    """Build a fake walking-mode distance matrix: 10 min/1km between every
    pair, except `slow_pairs` (set of index-pairs into `activities`), which
    get 50 min/8km so they exceed the default 30-min threshold."""
    n = len(activities)
    minutes = [[0] * n for _ in range(n)]
    meters = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            slow = (i, j) in slow_pairs or (j, i) in slow_pairs
            minutes[i][j] = 50 if slow else 10
            meters[i][j] = 8000 if slow else 1000
    return minutes, meters


def test_sequence_single_activity_returns_empty_travel_lists(db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    ordered, minutes, meters, modes = dps._sequence_day_activities(
        db, 1, [a], hotel_coord=(0.0, 0.0), travel_mode="walking"
    )
    assert ordered == [a]
    assert minutes == meters == modes == []


def test_sequence_all_gaps_under_threshold_stay_walking(monkeypatch, db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    b = make_activity(1, "B", 0.0, 0.001)
    c = make_activity(2, "C", 0.0, 0.002)

    def fake_matrix(origins, destinations, mode):
        assert mode == "walking"
        return _walking_matrix([a, b, c], slow_pairs=set())

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    _, minutes, _, modes = dps._sequence_day_activities(
        db, 1, [a, b, c], hotel_coord=(0.0, 0.0), travel_mode="walking"
    )
    assert modes == ["walking", "walking"]
    assert minutes == [10, 10]


def test_sequence_long_gap_switches_to_transit(monkeypatch, db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    b = make_activity(1, "B", 0.0, 0.001)
    c = make_activity(2, "C (far)", 1.0, 1.0)

    calls = []

    def fake_matrix(origins, destinations, mode):
        calls.append(mode)
        if mode == "walking":
            return _walking_matrix([a, b, c], slow_pairs={(1, 2)})
        if mode == "transit":
            # sparse call: only the flagged pair is queried, diagonal used
            n = len(origins)
            minutes = [[None] * n for _ in range(n)]
            meters = [[None] * n for _ in range(n)]
            for i in range(n):
                minutes[i][i] = 18
                meters[i][i] = 6000
            return minutes, meters
        raise AssertionError(f"unexpected mode queried: {mode}")

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    ordered, minutes, meters, modes = dps._sequence_day_activities(
        db, 1, [a, b, c], hotel_coord=(0.0, 0.0), travel_mode="walking", max_walk_minutes=30
    )
    assert [x.name for x in ordered] == ["A", "B", "C (far)"]
    assert modes == ["walking", "transit"]
    assert minutes == [10, 18]
    assert meters == [1000, 6000]
    assert "transit" in calls  # alt-mode lookup actually fired


def test_sequence_long_gap_falls_back_to_driving_when_transit_unresolved(monkeypatch, db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    b = make_activity(1, "B", 1.0, 1.0)

    def fake_matrix(origins, destinations, mode):
        if mode == "walking":
            return _walking_matrix([a, b], slow_pairs={(0, 1)})
        if mode == "transit":
            n = len(origins)
            return [[None] * n for _ in range(n)], [[None] * n for _ in range(n)]
        if mode == "driving":
            n = len(origins)
            minutes = [[None] * n for _ in range(n)]
            meters = [[None] * n for _ in range(n)]
            for i in range(n):
                minutes[i][i] = 25
                meters[i][i] = 9000
            return minutes, meters
        raise AssertionError(mode)

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    _, minutes, meters, modes = dps._sequence_day_activities(
        db, 1, [a, b], hotel_coord=(0.0, 0.0), travel_mode="walking"
    )
    assert modes == ["driving"]
    assert minutes == [25]
    assert meters == [9000]


def test_sequence_long_gap_keeps_walking_when_no_alternative_resolves(monkeypatch, db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    b = make_activity(1, "B", 1.0, 1.0)

    def fake_matrix(origins, destinations, mode):
        if mode == "walking":
            return _walking_matrix([a, b], slow_pairs={(0, 1)})
        # both transit and driving fail to resolve
        n = len(origins)
        return [[None] * n for _ in range(n)], [[None] * n for _ in range(n)]

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    _, minutes, meters, modes = dps._sequence_day_activities(
        db, 1, [a, b], hotel_coord=(0.0, 0.0), travel_mode="walking"
    )
    # last-resort: keeps the original (long) walking value rather than dropping it
    assert modes == ["walking"]
    assert minutes == [50]
    assert meters == [8000]


def test_sequence_skips_alt_mode_lookup_when_base_mode_is_not_walking(monkeypatch, db, make_activity):
    a = make_activity(0, "A", 0.0, 0.0)
    b = make_activity(1, "B", 1.0, 1.0)
    calls = []

    def fake_matrix(origins, destinations, mode):
        calls.append(mode)
        return _walking_matrix([a, b], slow_pairs={(0, 1)})

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    _, minutes, _, modes = dps._sequence_day_activities(
        db, 1, [a, b], hotel_coord=(0.0, 0.0), travel_mode="driving"
    )
    assert modes == ["driving"]
    assert minutes == [50]  # the fake matrix returns the same values regardless of mode
    assert calls == ["driving"]  # no extra transit/driving lookup triggered


def test_insert_rest_stops_splits_long_walking_segment(monkeypatch, db, make_activity, make_place):
    origin = make_activity(0, "Origin", 0.0, 0.0)
    destination = make_activity(1, "Destination", 0.0, 0.016)
    rest_place = make_place(0.0, 0.008, place_id=50)
    rest_place.name = "Midway Cafe"

    def fake_find_rest_stop(*args, **kwargs):
        assert args[2:4] == pytest.approx((0.0, 0.008))
        assert kwargs["original_travel_minutes"] == 40
        assert kwargs["max_detour_minutes"] == 10
        return rest_place, 0.9

    monkeypatch.setattr(dps.RestStopService, "find_rest_stop", staticmethod(fake_find_rest_stop))

    ordered, minutes, meters, modes, inserted = dps._insert_rest_stops(
        db, 1, [origin, destination], [40], [1800], ["walking"], 30
    )

    assert [activity.name for activity in ordered] == ["Origin", "Midway Cafe", "Destination"]
    assert ordered[1].type == ItineraryItemType.REST
    assert ordered[1].place is rest_place
    assert "walking segment was 40 min" in ordered[1].description
    assert "Seating confidence: 90%" in ordered[1].description
    assert minutes == [11, 11]
    assert meters[0] + meters[1] == pytest.approx(1779, abs=2)
    assert modes == ["walking", "walking"]
    assert inserted == 1


def test_insert_rest_stops_returns_original_inputs_when_search_raises(monkeypatch, db, make_activity):
    origin = make_activity(0, "Origin", 0.0, 0.0)
    destination = make_activity(1, "Destination", 0.0, 0.016)
    ordered = [origin, destination]
    minutes = [40]
    meters = [1800]
    modes = ["walking"]

    monkeypatch.setattr(
        dps.RestStopService,
        "find_rest_stop",
        staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))),
    )

    result = dps._insert_rest_stops(db, 1, ordered, minutes, meters, modes, 30)
    assert result == (ordered, minutes, meters, modes, 0)
    assert result[0] is ordered
    assert result[1] is minutes


def test_sequence_reorders_long_excursion_to_start_of_day(monkeypatch, db, make_activity):
    quick1 = make_activity(0, "Quick 1", 0.0, 0.0, duration_minutes=60)
    excursion = make_activity(1, "Excursion", 0.0, 0.001, duration_minutes=dps._LONG_EXCURSION_MIN)
    quick2 = make_activity(2, "Quick 2", 0.0, 0.002, duration_minutes=60)

    def fake_matrix(origins, destinations, mode):
        return _walking_matrix([quick1, excursion, quick2], slow_pairs=set())

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    ordered, *_ = dps._sequence_day_activities(
        db, 1, [quick1, excursion, quick2], hotel_coord=(0.0, 0.0), travel_mode="walking"
    )
    assert ordered[0].name == "Excursion"


# --- _resolve_alt_travel -------------------------------------------------------


def test_resolve_alt_travel_reads_only_the_diagonal(monkeypatch, db):
    def fake_matrix(origins, destinations, mode):
        assert mode == "transit"
        n = len(origins)
        minutes = [[999] * n for _ in range(n)]  # off-diagonal noise
        meters = [[999] * n for _ in range(n)]
        for i in range(n):
            minutes[i][i] = i * 10
            meters[i][i] = i * 100
        return minutes, meters

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    pairs = [((0.0, 0.0), (1.0, 1.0)), ((2.0, 2.0), (3.0, 3.0))]
    minutes, meters = dps._resolve_alt_travel(db, 1, pairs, "transit")
    assert minutes == [0, 10]
    assert meters == [0, 100]


# --- time-block scheduling: _build_day_items -----------------------------------


def test_build_day_items_applies_per_segment_travel_mode(hotel, make_activity):
    a = make_activity(0, "A", 0.0, 0.0, duration_minutes=60)
    b = make_activity(1, "B", 0.0, 0.001, duration_minutes=60)
    c = make_activity(2, "C", 1.0, 1.0, duration_minutes=60)

    items, scheduled, dropped, segments, _hours_warnings = dps._build_day_items(
        ordered_activities=[a, b, c],
        travel_minutes=[10, 18],
        travel_meters=[1000, 6000],
        unresolved_activities=[],
        lunch=None,
        dinner=None,
        hotel=hotel,
        travel_modes=["walking", "transit"],
        is_first_day=True,
        is_last_day=True,
    )
    assert scheduled == 3
    assert dropped == 0
    assert segments == 2
    assert not any(item.type == ItineraryItemType.REST for item in items)

    activity_items = [i for i in items if i.title in ("A", "B", "C")]
    assert activity_items[0].travel_mode_to_next == "walking"
    assert activity_items[0].travel_time_to_next_minutes == 10
    assert activity_items[1].travel_mode_to_next == "transit"
    assert activity_items[1].travel_time_to_next_minutes == 18
    assert activity_items[2].travel_mode_to_next is None  # nothing after the last stop


def test_build_day_items_includes_checkin_and_checkout_only_on_bookend_days(hotel, make_activity):
    a = make_activity(0, "A", 0.0, 0.0, duration_minutes=60)

    items_first = dps._build_day_items(
        [a], [], [], [], None, None, hotel, [], is_first_day=True, is_last_day=False
    )[0]
    items_middle = dps._build_day_items(
        [a], [], [], [], None, None, hotel, [], is_first_day=False, is_last_day=False
    )[0]
    items_last = dps._build_day_items(
        [a], [], [], [], None, None, hotel, [], is_first_day=False, is_last_day=True
    )[0]

    assert any(i.title == "Hotel check-in" for i in items_first)
    assert not any(i.title == "Hotel check-in" for i in items_middle)
    assert not any(i.title == "Hotel check-out" for i in items_middle)
    assert any(i.title == "Hotel check-out" for i in items_last)


def test_build_day_items_drops_optional_overflow_past_hard_stop(hotel, make_activity):
    # Three required activities fit comfortably; the trailing optional one
    # is long enough to overflow past the hard stop and should be dropped
    # without dragging the required activities down with it.
    required = [
        make_activity(i, f"Required {i}", 0.0, i * 0.001, duration_minutes=90)
        for i in range(3)
    ]
    optional = make_activity(
        99, "Optional extra", 0.0, 0.05, duration_minutes=400, priority=ItineraryItemPriority.OPTIONAL
    )
    ordered = required + [optional]
    travel_minutes = [0] * (len(ordered) - 1)
    travel_meters = [0] * (len(ordered) - 1)
    travel_modes = ["walking"] * (len(ordered) - 1)

    items, scheduled, dropped, _segments, _hours_warnings = dps._build_day_items(
        ordered, travel_minutes, travel_meters, [], None, None, hotel, travel_modes,
        is_first_day=False, is_last_day=False,
    )
    assert dropped == 1
    assert scheduled == 3
    assert not any(i.title == "Optional extra" for i in items)
    for i in range(3):
        assert any(item.title == f"Required {i}" for item in items)


def test_build_day_items_uses_custom_activity_start(hotel, make_activity):
    activity = make_activity(0, "Late start", 0.0, 0.0, duration_minutes=60)

    items = dps._build_day_items(
        [activity], [], [], [], None, None, hotel, [],
        is_first_day=False,
        is_last_day=False,
        activity_start_min=11 * 60,
    )[0]

    scheduled = next(item for item in items if item.title == "Late start")
    assert scheduled.start_time == "11:00"


def test_build_day_items_uses_custom_hard_stop_and_required_grace(hotel, make_activity):
    optional = make_activity(
        0,
        "Optional overflow",
        0.0,
        0.0,
        duration_minutes=150,
        priority=ItineraryItemPriority.OPTIONAL,
    )
    required = make_activity(
        1,
        "Required overflow",
        0.0,
        0.001,
        duration_minutes=150,
        priority=ItineraryItemPriority.REQUIRED,
    )

    optional_result = dps._build_day_items(
        [optional], [], [], [], None, None, hotel, [],
        is_first_day=False,
        is_last_day=False,
        hard_stop_min=10 * 60 + 30,
    )
    required_result = dps._build_day_items(
        [required], [], [], [], None, None, hotel, [],
        is_first_day=False,
        is_last_day=False,
        hard_stop_min=10 * 60 + 30,
    )

    assert optional_result[1:3] == (0, 1)
    assert not any(item.title == "Optional overflow" for item in optional_result[0])
    assert required_result[1:3] == (1, 0)
    required_item = next(item for item in required_result[0] if item.title == "Required overflow")
    assert required_item.end_time == "11:30"


def test_fallback_plan_uses_custom_activity_window(hotel, make_activity):
    activity = make_activity(0, "Fallback activity", 0.0, 0.0, duration_minutes=60)

    result = DayPlannerService._fallback_plan(
        1,
        hotel,
        [activity],
        [],
        "test fallback",
        activity_start_min=11 * 60,
        hard_stop_min=12 * 60,
    )

    scheduled = next(item for item in result.days[0].items if item.title == "Fallback activity")
    assert scheduled.start_time == "11:00"
    assert scheduled.end_time == "12:00"


# --- plan_days end-to-end -------------------------------------------------------


def test_plan_days_populates_total_transit_minutes_when_a_segment_uses_transit(
    monkeypatch, db, hotel, make_activity, make_restaurant
):
    activities = [
        make_activity(0, "Near A", 0.0, 0.0),
        make_activity(1, "Near B", 0.0, 0.001),
        make_activity(2, "Far C", 1.0, 1.0),
    ]
    restaurants = [
        make_restaurant(0, "Lunch Spot", "lunch"),
        make_restaurant(1, "Dinner Spot", "dinner"),
    ]

    def fake_matrix(origins, destinations, mode):
        n = len(origins)
        if mode == "walking":
            minutes, meters = _walking_matrix(activities, slow_pairs={(1, 2)})
            return minutes, meters
        if mode == "transit":
            minutes = [[None] * n for _ in range(n)]
            meters = [[None] * n for _ in range(n)]
            for i in range(n):
                minutes[i][i] = 15
                meters[i][i] = 5000
            return minutes, meters
        return [[None] * n for _ in range(n)], [[None] * n for _ in range(n)]

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))

    result = DayPlannerService.plan_days(
        db, agent_run_id=1, num_days=1, hotel=hotel, activities=activities,
        restaurants=restaurants, travel_mode="walking", max_walk_minutes=30,
    )
    assert not result.degraded
    day = result.days[0]
    assert day.route_optimized
    assert day.total_transit_minutes == 15
    transit_items = [
        i for i in day.items if i.travel_mode_to_next == "transit"
    ]
    assert len(transit_items) == 1


def test_plan_days_accumulates_inserted_rest_stops(monkeypatch, db, hotel, make_activity, make_place):
    activities = [
        make_activity(0, "Origin", 0.0, 0.0, duration_minutes=60),
        make_activity(1, "Destination", 0.0, 0.016, duration_minutes=60),
    ]
    rest_place = make_place(0.0, 0.008, place_id=50)
    rest_place.name = "Midway Cafe"

    def fake_matrix(origins, destinations, mode):
        n = len(origins)
        if mode == "walking":
            return [[0, 40], [40, 0]], [[0, 1800], [1800, 0]]
        return [[None] * n for _ in range(n)], [[None] * n for _ in range(n)]

    monkeypatch.setattr(RouteService, "_get_distance_matrix_full", staticmethod(fake_matrix))
    monkeypatch.setattr(
        dps.RestStopService,
        "find_rest_stop",
        staticmethod(lambda *args, **kwargs: (rest_place, 0.9)),
    )

    result = DayPlannerService.plan_days(
        db,
        agent_run_id=1,
        num_days=1,
        hotel=hotel,
        activities=activities,
        restaurants=[],
        travel_mode="walking",
        max_walk_minutes=30,
    )

    inserted_items = [item for item in result.days[0].items if item.title == "Midway Cafe"]
    assert result.rest_stops_inserted == 1
    assert len(inserted_items) == 1
    assert inserted_items[0].type == ItineraryItemType.REST
    assert inserted_items[0].place_id == 50
    assert "walking segment was 40 min" in inserted_items[0].description


def test_plan_days_falls_back_gracefully_on_internal_failure(monkeypatch, db, hotel, make_activity):
    activities = [make_activity(i, f"A{i}", 0.0, i * 0.01) for i in range(4)]

    def boom(*args, **kwargs):
        raise RuntimeError("clustering exploded")

    monkeypatch.setattr(dps, "_kmeans_labels", boom)

    result = DayPlannerService.plan_days(
        db, agent_run_id=1, num_days=2, hotel=hotel, activities=activities,
        restaurants=[], travel_mode="walking", activity_start_min=11 * 60,
        hard_stop_min=14 * 60,
    )
    assert result.degraded
    assert "clustering exploded" in result.degraded_reason
    assert result.segments_with_routes == 0
    assert sum(len(d.items) for d in result.days) > 0  # still produced a usable plan
    for day in result.days:
        assert day.route_optimized is False
        assert all(i.travel_mode_to_next is None for i in day.items)
        activity_items = [i for i in day.items if i.type == ItineraryItemType.ACTIVITY]
        assert all(i.start_time >= "11:00" for i in activity_items)


def test_fallback_plan_round_robins_activities_across_days(hotel, make_activity):
    activities = [make_activity(i, f"A{i}", 0.0, i * 0.01) for i in range(4)]
    result = DayPlannerService._fallback_plan(
        num_days=2, hotel=hotel, activities=activities, restaurants=[], reason="test"
    )
    assert result.degraded
    assert len(result.days) == 2
    names_by_day = [
        {i.title for i in day.items if i.type == ItineraryItemType.ACTIVITY}
        for day in result.days
    ]
    all_scheduled = names_by_day[0] | names_by_day[1]
    assert all_scheduled == {"A0", "A1", "A2", "A3"}


# --- _pick_restaurant (module-level, hours-aware) -------------------------------

_MONDAY = 1


def test_pick_restaurant_prefers_open_over_closer_closed(make_restaurant, weekly_hours):
    closed_nearer = make_restaurant(0, "Closed Nearer", "dinner", 0.0, 0.001, opening_hours=weekly_hours({0: (9 * 60, 17 * 60)}))
    open_farther = make_restaurant(1, "Open Farther", "dinner", 0.0, 0.01, opening_hours=weekly_hours({_MONDAY: (9 * 60, 22 * 60)}))
    chosen = dps._pick_restaurant(
        [closed_nearer, open_farther], set(), near=(0.0, 0.0), weekday=_MONDAY,
        window_start_min=19 * 60, window_end_min=21 * 60,
    )
    assert chosen.name == "Open Farther"


def test_pick_restaurant_treats_unknown_hours_as_open(make_restaurant, weekly_hours):
    unknown_nearer = make_restaurant(0, "Unknown Nearer", "dinner", 0.0, 0.001, opening_hours=None)
    closed_farther = make_restaurant(1, "Closed Farther", "dinner", 0.0, 0.01, opening_hours=weekly_hours({0: (9 * 60, 17 * 60)}))
    chosen = dps._pick_restaurant(
        [unknown_nearer, closed_farther], set(), near=(0.0, 0.0), weekday=_MONDAY,
        window_start_min=19 * 60, window_end_min=21 * 60,
    )
    assert chosen.name == "Unknown Nearer"


def test_pick_restaurant_returns_nearest_when_all_closed(make_restaurant, weekly_hours):
    closed_nearer = make_restaurant(0, "Closed Nearer", "dinner", 0.0, 0.001, opening_hours=weekly_hours({0: (9 * 60, 17 * 60)}))
    closed_farther = make_restaurant(1, "Closed Farther", "dinner", 0.0, 0.01, opening_hours=weekly_hours({0: (9 * 60, 17 * 60)}))
    chosen = dps._pick_restaurant(
        [closed_nearer, closed_farther], set(), near=(0.0, 0.0), weekday=_MONDAY,
        window_start_min=19 * 60, window_end_min=21 * 60,
    )
    assert chosen is not None
    assert chosen.name == "Closed Nearer"  # nearest wins when nothing is open


# --- _build_day_items: hours-aware lunch/dinner/activity handling --------------


def test_build_day_items_lunch_warns_when_closed_at_placed_time(hotel, make_restaurant, weekly_hours):
    lunch = make_restaurant(0, "Lunch Place", "lunch", opening_hours=weekly_hours({_MONDAY: (13 * 60, 15 * 60)}))
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [], [], [], [], lunch, None, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    lunch_item = next(i for i in items if i.title == "Lunch")
    assert lunch_item.start_time == "12:00"
    assert "may be closed" in lunch_item.description
    assert hours_warnings == 1


def test_build_day_items_lunch_no_warning_when_open(hotel, make_restaurant, weekly_hours):
    lunch = make_restaurant(0, "Lunch Place", "lunch", opening_hours=weekly_hours({_MONDAY: (11 * 60, 15 * 60)}))
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [], [], [], [], lunch, None, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    lunch_item = next(i for i in items if i.title == "Lunch")
    assert lunch_item.description == lunch.description
    assert hours_warnings == 0


def test_build_day_items_dinner_shifts_into_open_window(hotel, make_restaurant, weekly_hours):
    dinner = make_restaurant(0, "Dinner Place", "dinner", opening_hours=weekly_hours({_MONDAY: (20 * 60, 22 * 60)}))
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [], [], [], [], None, dinner, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    dinner_item = next(i for i in items if i.title == "Dinner")
    assert dinner_item.start_time == "20:00"
    assert not (dinner_item.description or "")
    assert hours_warnings == 0


def test_build_day_items_dinner_stays_and_warns_when_reopen_past_window(hotel, make_restaurant, weekly_hours):
    dinner = make_restaurant(0, "Dinner Place", "dinner", opening_hours=weekly_hours({_MONDAY: (22 * 60, 23 * 60)}))
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [], [], [], [], None, dinner, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    dinner_item = next(i for i in items if i.title == "Dinner")
    assert dinner_item.start_time == "19:30"
    assert "may be closed" in dinner_item.description
    assert hours_warnings == 1


def test_build_day_items_defers_activity_until_it_reopens(hotel, make_activity, weekly_hours):
    act = make_activity(0, "Late Museum", 0.0, 0.0, duration_minutes=60, opening_hours=weekly_hours({_MONDAY: (14 * 60, 18 * 60)}))
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [act], [], [], [], None, None, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    scheduled_item = next(i for i in items if i.title == "Late Museum")
    assert scheduled_item.start_time == "14:00"
    assert dropped == 0
    assert scheduled == 1


def test_build_day_items_activity_closed_all_day_gets_warning_not_dropped(hotel, make_activity, weekly_hours):
    act = make_activity(
        0, "Weekend Only Shop", 0.0, 0.0, duration_minutes=60,
        opening_hours=weekly_hours({(_MONDAY + 1) % 7: (9 * 60, 17 * 60)}),
    )
    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [act], [], [], [], None, None, hotel, [], is_first_day=False, is_last_day=False, weekday=_MONDAY,
    )
    scheduled_item = next(i for i in items if i.title == "Weekend Only Shop")
    assert scheduled_item.start_time == "09:00"
    assert "may be closed" in scheduled_item.description
    assert dropped == 0
    assert scheduled == 1
    assert hours_warnings >= 1


def test_build_day_items_weekday_none_ignores_hours_data(hotel, make_activity, make_restaurant, weekly_hours):
    """Regression guard: with no start_date (weekday=None), hours data must
    never influence scheduling — byte-identical to pre-Sprint-6 behavior."""
    act = make_activity(0, "Evening Bar", 0.0, 0.0, duration_minutes=60, opening_hours=weekly_hours({_MONDAY: (20 * 60, 23 * 60)}))
    lunch = make_restaurant(0, "L", "lunch", opening_hours=weekly_hours({_MONDAY: (13 * 60, 15 * 60)}))
    dinner = make_restaurant(1, "D", "dinner", opening_hours=weekly_hours({_MONDAY: (22 * 60, 23 * 60)}))

    items, scheduled, dropped, segments, hours_warnings = dps._build_day_items(
        [act], [], [], [], lunch, dinner, hotel, [], is_first_day=False, is_last_day=False, weekday=None,
    )
    assert hours_warnings == 0
    assert dropped == 0
    assert scheduled == 1

    act_item = next(i for i in items if i.title == "Evening Bar")
    assert act_item.start_time == "09:00"
    dinner_item = next(i for i in items if i.title == "Dinner")
    assert dinner_item.start_time == "19:30"
    assert dinner_item.description is None


def test_fallback_plan_applies_weekday_and_accumulates_hours_warnings(hotel, make_activity):
    act = make_activity(
        0, "Weekend Only Shop", 0.0, 0.0, duration_minutes=60,
        opening_hours={"periods": [{"open": {"day": (_MONDAY + 1) % 7, "hour": 9}, "close": {"day": (_MONDAY + 1) % 7, "hour": 17}}]},
    )
    result = DayPlannerService._fallback_plan(
        num_days=1, hotel=hotel, activities=[act], restaurants=[], reason="test",
        start_date=datetime.date(2026, 8, 24),  # a Monday
    )
    assert result.degraded
    assert result.hours_warnings_added >= 1
    item = next(i for i in result.days[0].items if i.title == "Weekend Only Shop")
    assert "may be closed" in item.description
