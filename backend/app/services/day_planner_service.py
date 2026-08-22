"""Day clustering and scheduling service (Sprint 4 redesign).

The LLM proposes a flat *pool* of places (one hotel, many activities/events,
many restaurant options) with no day assignment or timing. This module turns
that pool into a day-by-day plan:

1. Cluster resolved activities into ``num_days`` geographically tight groups
   (a capacity-balanced k-means over an equirectangular projection of
   lat/lng, no external dependencies, no randomness — deterministic so runs
   are reproducible).
2. Order the day-clusters by nearest-neighbor over their centroids, starting
   from the hotel.
3. Sequence each day's activities by nearest-neighbor travel time (Google
   Distance Matrix via :class:`RouteService`), assign the nearest unused
   lunch/dinner restaurant, and lay out a fixed daily time-block template
   (breakfast, activities, lunch, rest, dinner, check-in/out).
4. Build the ``ItineraryItem`` ORM objects directly, with travel fields
   populated between consecutive scheduled activities.

Pure/deterministic except for the Distance Matrix calls, which are logged as
``ToolCall`` rows via :class:`RouteService`. Never raises: any failure in the
clustering/scheduling path falls back to a naive round-robin day assignment
with template times and no travel data, so a bad trip never aborts the run.
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.agent import AgentRunStatus
from app.models.itinerary import (
    ItineraryItem,
    ItineraryItemPriority,
    ItineraryItemType,
    WalkingIntensity,
)
from app.models.place import Place
from app.services.opening_hours import google_weekday, is_open_at, next_open_minute
from app.services.rest_stop_service import RestStopService
from app.services.route_service import RouteService

_EARTH_RADIUS_M = 6_371_000.0

_DEFAULT_ACTIVITY_START_MIN = 9 * 60  # 09:00
_LUNCH_TRIGGER_MIN = 12 * 60  # 12:00
_LATE_LUNCH_CUTOFF_MIN = 15 * 60 + 30  # 15:30
_DINNER_MIN = 19 * 60 + 30  # 19:30
_DEFAULT_HARD_STOP_MIN = 20 * 60 + 30  # 20:30; optional overflow is dropped immediately.
# required/recommended overflow is deferred and retried at the end of the day
# (see `_build_day_items`) before being dropped as a last resort.
_LONG_EXCURSION_MIN = 240  # 4+ hours — scheduled first in its day (see `_sequence_day_activities`)
_DEFAULT_MAX_WALK_MINUTES = 30  # gaps beyond this get a transit/driving alternative instead
_ALT_TRAVEL_MODES = ("transit", "driving")  # tried in order for gaps over the max-walk threshold

_LUNCH_WINDOW = (12 * 60, 14 * 60)  # nominal lunch window used for restaurant selection
_DINNER_WINDOW_END = 21 * 60 + 30  # latest dinner start considered when shifting for hours
_GOOGLE_DAY_NAMES = (
    "Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
)  # Google Places weekday convention (0=Sunday)


@dataclass
class HotelInfo:
    name: str
    description: str | None
    estimated_cost_per_night: Decimal | None
    place: Place | None


@dataclass
class PoolActivity:
    index: int
    name: str
    type: ItineraryItemType  # ACTIVITY or EVENT
    duration_minutes: int
    priority: ItineraryItemPriority
    walking_intensity: WalkingIntensity | None
    description: str | None
    estimated_cost: Decimal | None
    verified_cost: Decimal | None
    price_source: str | None
    place: Place | None
    best_time_of_day: str = "any"


@dataclass
class PoolRestaurant:
    index: int
    name: str
    meal_type: str  # "lunch" or "dinner"
    description: str | None
    estimated_cost: Decimal | None
    verified_cost: Decimal | None
    price_source: str | None
    place: Place | None


@dataclass
class DayPlan:
    day_number: int
    items: list[ItineraryItem]
    route_optimized: bool
    total_walking_minutes: int | None
    total_transit_minutes: int | None
    total_distance_meters: int | None


@dataclass
class PlanResult:
    days: list[DayPlan]
    activities_scheduled: int
    activities_dropped: int
    segments_with_routes: int
    degraded: bool
    rest_stops_inserted: int = 0
    hours_warnings_added: int = 0
    degraded_reason: str | None = None


# --- Geometry helpers --------------------------------------------------------


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def _midpoint(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """Return the arithmetic midpoint of two nearby latitude/longitude pairs."""
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _project_xy(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Equirectangular projection to meters, centered on the point set's mean
    latitude, so clustering isn't distorted by longitude compression at high
    latitudes."""
    if not points:
        return []
    mean_lat_rad = math.radians(sum(p[0] for p in points) / len(points))
    return [
        (
            math.radians(lng) * math.cos(mean_lat_rad) * _EARTH_RADIUS_M,
            math.radians(lat) * _EARTH_RADIUS_M,
        )
        for lat, lng in points
    ]


def _ceil5(minutes: int) -> int:
    return int(math.ceil(minutes / 5.0)) * 5


def _fmt_time(total_minutes: int) -> str:
    total_minutes = max(0, total_minutes) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def _hours_warning(name: str, start_min: int, weekday: int) -> str:
    return (
        f"Heads up: {name} may be closed around {_fmt_time(start_min)} "
        f"on {_GOOGLE_DAY_NAMES[weekday]} - double-check opening hours."
    )


def _append_warning(description: str | None, warning: str) -> str:
    return f"{description} {warning}" if description else warning


# --- Clustering ---------------------------------------------------------------


def _kmeans_labels(points: list[tuple[float, float]], k: int, max_iters: int = 25) -> list[int]:
    """Assign each point a cluster label in ``range(k)``.

    Deterministic — no randomness — so identical input always produces
    identical clusters (reproducible runs, unit-testable). Centroids are
    seeded from evenly spaced picks along the x-sorted projected points
    rather than a random init.
    """
    n = len(points)
    if k <= 0 or n == 0:
        return []
    if k >= n:
        return list(range(n))

    xy = _project_xy(points)
    order = sorted(range(n), key=lambda i: xy[i][0])
    centroids = [xy[order[int(i * n / k)]] for i in range(k)]

    labels = [0] * n
    for _ in range(max_iters):
        changed = False
        for i, p in enumerate(xy):
            best_k, best_d = 0, None
            for c_idx, c in enumerate(centroids):
                d = (p[0] - c[0]) ** 2 + (p[1] - c[1]) ** 2
                if best_d is None or d < best_d:
                    best_d, best_k = d, c_idx
            if labels[i] != best_k:
                labels[i] = best_k
                changed = True

        sums = [[0.0, 0.0, 0] for _ in range(k)]
        for i, p in enumerate(xy):
            s = sums[labels[i]]
            s[0] += p[0]
            s[1] += p[1]
            s[2] += 1
        for c_idx in range(k):
            if sums[c_idx][2] > 0:
                centroids[c_idx] = (sums[c_idx][0] / sums[c_idx][2], sums[c_idx][1] / sums[c_idx][2])

        if not changed:
            break

    return labels


def _balance_clusters(labels: list[int], points: list[tuple[float, float]], k: int) -> list[int]:
    """Cap every cluster at ``ceil(n/k)`` by moving each overflowing
    cluster's farthest-from-centroid point into the nearest under-capacity
    cluster. Bounded iterations (at most ``n`` moves)."""
    n = len(points)
    if n == 0 or k <= 0:
        return labels

    max_size = math.ceil(n / k)
    labels = list(labels)
    xy = _project_xy(points)

    def members_of(c: int) -> list[int]:
        return [i for i in range(n) if labels[i] == c]

    def centroid_of(members: list[int]) -> tuple[float, float] | None:
        if not members:
            return None
        return (
            sum(xy[i][0] for i in members) / len(members),
            sum(xy[i][1] for i in members) / len(members),
        )

    for _ in range(n):
        sizes = [len(members_of(c)) for c in range(k)]
        overflowing = [c for c in range(k) if sizes[c] > max_size]
        if not overflowing:
            break

        c = overflowing[0]
        members = members_of(c)
        c_centroid = centroid_of(members)
        farthest_i = max(
            members,
            key=lambda i: (xy[i][0] - c_centroid[0]) ** 2 + (xy[i][1] - c_centroid[1]) ** 2,
        )

        best_c, best_d = None, None
        for other in range(k):
            if other == c or sizes[other] >= max_size:
                continue
            other_centroid = centroid_of(members_of(other))
            d = (
                0.0
                if other_centroid is None
                else (xy[farthest_i][0] - other_centroid[0]) ** 2
                + (xy[farthest_i][1] - other_centroid[1]) ** 2
            )
            if best_d is None or d < best_d:
                best_d, best_c = d, other

        if best_c is None:
            break
        labels[farthest_i] = best_c

    return labels


def _order_clusters(
    labels: list[int],
    points: list[tuple[float, float]],
    k: int,
    hotel_coord: tuple[float, float] | None,
) -> list[int]:
    """Return cluster ids in day-visit order via nearest-neighbor over
    centroids, starting from the hotel."""
    centroids: list[tuple[float, float] | None] = []
    for c in range(k):
        members = [i for i in range(len(points)) if labels[i] == c]
        if members:
            centroids.append(
                (
                    sum(points[i][0] for i in members) / len(members),
                    sum(points[i][1] for i in members) / len(members),
                )
            )
        else:
            centroids.append(None)

    remaining = set(range(k))
    order: list[int] = []
    current = hotel_coord

    while remaining:
        candidates = [c for c in remaining if centroids[c] is not None]
        if current is None or not candidates:
            next_c = min(remaining)
        else:
            next_c = min(candidates, key=lambda c: _haversine_meters(current, centroids[c]))
        order.append(next_c)
        remaining.discard(next_c)
        if centroids[next_c] is not None:
            current = centroids[next_c]

    return order


# --- Within-day sequencing ----------------------------------------------------


def _resolve_alt_travel(
    db: Session,
    agent_run_id: int,
    pairs: list[tuple[tuple[float, float], tuple[float, float]]],
    mode: str,
) -> tuple[list[int | None], list[int | None]]:
    """Look up travel time/distance for specific origin->destination pairs
    (not a full cross-product matrix) in a single Distance Matrix call,
    reading back only the diagonal. Returns parallel lists aligned with
    ``pairs``. Never raises."""
    origins = [p[0] for p in pairs]
    destinations = [p[1] for p in pairs]
    minutes, meters = RouteService._get_distance_matrix_full(origins, destinations, mode)
    n = len(pairs)
    diag_minutes = [minutes[i][i] for i in range(n)]
    diag_meters = [meters[i][i] for i in range(n)]
    pairs_resolved = sum(1 for v in diag_minutes if v is not None)
    RouteService._log_tool_call(
        db=db,
        agent_run_id=agent_run_id,
        status=AgentRunStatus.COMPLETED if pairs_resolved > 0 else AgentRunStatus.FAILED,
        input_json={"pairs": n, "mode": mode},
        output_json={"pairs_resolved": pairs_resolved},
        error_message=None if pairs_resolved > 0 else "No routes resolved from Google Distance Matrix",
        latency_ms=None,
    )
    return diag_minutes, diag_meters


def _sequence_day_activities(
    db: Session,
    agent_run_id: int,
    activities: list[PoolActivity],
    hotel_coord: tuple[float, float] | None,
    travel_mode: str,
    max_walk_minutes: int = _DEFAULT_MAX_WALK_MINUTES,
) -> tuple[list[PoolActivity], list[int | None], list[int | None], list[str]]:
    """Order ``activities`` (all with a resolved place) by nearest-neighbor
    travel time. Returns ``(ordered, travel_minutes, travel_meters,
    travel_modes)`` where the travel lists have length
    ``len(activities) - 1`` (gap i is between ordered[i] and ordered[i+1]).

    When ``travel_mode`` is ``"walking"``, any gap whose walking time exceeds
    ``max_walk_minutes`` is re-queried with an alternative mode (transit,
    then driving) and swapped in if resolved — the walking time is kept as a
    last resort if neither alternative resolves."""
    n = len(activities)
    if n == 0:
        return [], [], [], []
    if n == 1:
        return list(activities), [], [], []

    coords = [(a.place.lat, a.place.lng) for a in activities]
    minutes, meters = RouteService._get_distance_matrix_full(coords, coords, travel_mode)
    pairs_resolved = sum(1 for row in minutes for v in row if v is not None)
    RouteService._log_tool_call(
        db=db,
        agent_run_id=agent_run_id,
        status=AgentRunStatus.COMPLETED if pairs_resolved > 0 else AgentRunStatus.FAILED,
        input_json={"origins": n, "destinations": n, "mode": travel_mode},
        output_json={"pairs_resolved": pairs_resolved},
        error_message=None if pairs_resolved > 0 else "No routes resolved from Google Distance Matrix",
        latency_ms=None,
    )

    start_index = 0
    if hotel_coord is not None:
        start_index = min(range(n), key=lambda i: _haversine_meters(hotel_coord, coords[i]))

    order = RouteService.nearest_neighbor_order(minutes, start_index=start_index)

    # Full/half-day excursions get the day's morning start budget instead of
    # wherever nearest-neighbor placed them — otherwise faster in-city stops
    # consume the morning and push a long excursion past the hard stop.
    long_positions = [
        p for p, i in enumerate(order)
        if (activities[i].duration_minutes or 0) >= _LONG_EXCURSION_MIN
    ]
    if long_positions and long_positions != list(range(len(long_positions))):
        long_slice = [order[p] for p in long_positions]
        rest_slice = [order[p] for p in range(len(order)) if p not in long_positions]
        order = long_slice + rest_slice

    ordered = [activities[i] for i in order]
    travel_minutes = [minutes[order[i]][order[i + 1]] for i in range(n - 1)]
    travel_meters = [meters[order[i]][order[i + 1]] for i in range(n - 1)]
    travel_modes = [travel_mode] * (n - 1)

    if travel_mode == "walking":
        flagged = [
            i for i in range(n - 1)
            if travel_minutes[i] is not None and travel_minutes[i] > max_walk_minutes
        ]
        for alt_mode in _ALT_TRAVEL_MODES:
            if not flagged:
                break
            pairs = [(coords[order[i]], coords[order[i + 1]]) for i in flagged]
            alt_minutes, alt_meters = _resolve_alt_travel(db, agent_run_id, pairs, alt_mode)
            still_flagged = []
            for pos, i in enumerate(flagged):
                if alt_minutes[pos] is not None:
                    travel_minutes[i] = alt_minutes[pos]
                    travel_meters[i] = alt_meters[pos]
                    travel_modes[i] = alt_mode
                else:
                    still_flagged.append(i)
            flagged = still_flagged

    return ordered, travel_minutes, travel_meters, travel_modes


def _insert_rest_stops(
    db: Session,
    agent_run_id: int,
    ordered: list[PoolActivity],
    travel_minutes: list[int | None],
    travel_meters: list[int | None],
    travel_modes: list[str],
    max_walk_minutes: int,
    weekday: int | None = None,
) -> tuple[list[PoolActivity], list[int | None], list[int | None], list[str], int]:
    """Insert real rest stops into long walking segments. Never raises."""
    try:
        if not ordered:
            return [], [], [], [], 0

        new_ordered = [ordered[0]]
        new_travel_minutes: list[int | None] = []
        new_travel_meters: list[int | None] = []
        new_travel_modes: list[str] = []
        rest_stops_inserted = 0

        for i in range(len(ordered) - 1):
            origin = ordered[i]
            destination = ordered[i + 1]
            minutes = travel_minutes[i]
            should_search = (
                travel_modes[i] == "walking"
                and minutes is not None
                and minutes > max_walk_minutes
                and origin.place is not None
                and destination.place is not None
            )

            if should_search:
                origin_coord = (origin.place.lat, origin.place.lng)
                dest_coord = (destination.place.lat, destination.place.lng)
                midpoint_lat, midpoint_lng = _midpoint(origin_coord, dest_coord)
                place, confidence = RestStopService.find_rest_stop(
                    db,
                    agent_run_id,
                    midpoint_lat,
                    midpoint_lng,
                    origin_coord=origin_coord,
                    dest_coord=dest_coord,
                    original_travel_minutes=minutes,
                    max_detour_minutes=10,
                    weekday=weekday,
                )
                if place is not None and confidence is not None:
                    stop_coord = (place.lat, place.lng)
                    to_stop_distance = _haversine_meters(origin_coord, stop_coord)
                    from_stop_distance = _haversine_meters(stop_coord, dest_coord)
                    to_stop_meters = round(to_stop_distance)
                    from_stop_meters = round(from_stop_distance)
                    rest_stop = PoolActivity(
                        index=-1,
                        name=place.name,
                        type=ItineraryItemType.REST,
                        duration_minutes=20,
                        priority=ItineraryItemPriority.OPTIONAL,
                        walking_intensity=WalkingIntensity.LOW,
                        description=(
                            f"Rest stop added: {place.name}. "
                            f"The walking segment was {minutes} min. "
                            f"Seating confidence: {confidence:.0%}."
                        ),
                        estimated_cost=None,
                        verified_cost=None,
                        price_source=None,
                        place=place,
                        best_time_of_day="any",
                    )
                    new_travel_minutes.extend(
                        [round(to_stop_distance / 80), round(from_stop_distance / 80)]
                    )
                    new_travel_meters.extend([to_stop_meters, from_stop_meters])
                    new_travel_modes.extend(["walking", "walking"])
                    new_ordered.extend([rest_stop, destination])
                    rest_stops_inserted += 1
                    continue

            new_travel_minutes.append(minutes)
            new_travel_meters.append(travel_meters[i])
            new_travel_modes.append(travel_modes[i])
            new_ordered.append(destination)

        return (
            new_ordered,
            new_travel_minutes,
            new_travel_meters,
            new_travel_modes,
            rest_stops_inserted,
        )
    except Exception:  # noqa: BLE001 - rest-stop insertion must not abort planning
        return ordered, travel_minutes, travel_meters, travel_modes, 0


def _pick_restaurant(
    options: list[PoolRestaurant],
    used: set[int],
    near: tuple[float, float] | None,
    weekday: int | None,
    window_start_min: int,
    window_end_min: int,
) -> PoolRestaurant | None:
    """Pick the nearest unused restaurant, preferring one that is open (or of
    unknown hours, or due to reopen) during the meal window on ``weekday``.
    Falls back to the nearest candidate regardless of hours if every option
    is confirmed closed for the whole window — the actual scheduled minute
    decides later whether a warning is added."""
    available = [r for r in options if r.index not in used]
    if not available:
        available = options
    if not available:
        return None
    with_place = [r for r in available if r.place is not None]

    pool = with_place
    if weekday is not None and with_place:
        def open_or_reopens(r: PoolRestaurant) -> bool:
            try:
                hours = r.place.opening_hours
                if is_open_at(hours, weekday, window_start_min) is not False:
                    return True
                return next_open_minute(hours, weekday, window_start_min, window_end_min) is not None
            except Exception:  # noqa: BLE001 - a bad hours check must not exclude a candidate
                return True

        open_or_unknown = [r for r in with_place if open_or_reopens(r)]
        if open_or_unknown:
            pool = open_or_unknown

    if pool and near is not None:
        chosen = min(pool, key=lambda r: _haversine_meters(near, (r.place.lat, r.place.lng)))
    elif pool:
        chosen = pool[0]
    else:
        chosen = available[0]
    used.add(chosen.index)
    return chosen


# --- Time-block scheduling ------------------------------------------------------


def _make_item(
    start: int,
    end: int,
    title: str,
    item_type: ItineraryItemType,
    *,
    location_name: str | None = None,
    description: str | None = None,
    estimated_cost: Decimal | None = None,
    verified_cost: Decimal | None = None,
    price_source: str | None = None,
    walking_intensity: WalkingIntensity | None = None,
    priority: ItineraryItemPriority = ItineraryItemPriority.REQUIRED,
    place_id: int | None = None,
) -> ItineraryItem:
    return ItineraryItem(
        start_time=_fmt_time(start),
        end_time=_fmt_time(end),
        title=title,
        type=item_type,
        location_name=location_name,
        description=description,
        estimated_cost=estimated_cost,
        verified_cost=verified_cost,
        price_source=price_source,
        walking_intensity=walking_intensity,
        priority=priority,
        order_index=0,  # reassigned by the caller once the day is fully built
        place_id=place_id,
    )


def _make_meal_item(start: int, end: int, title: str, restaurant: PoolRestaurant | None) -> ItineraryItem:
    if restaurant is None:
        return _make_item(start, end, title, ItineraryItemType.MEAL, description="Meal on the go")
    return _make_item(
        start,
        end,
        title,
        ItineraryItemType.MEAL,
        location_name=restaurant.name,
        description=restaurant.description,
        estimated_cost=restaurant.estimated_cost,
        verified_cost=restaurant.verified_cost,
        price_source=restaurant.price_source,
        place_id=restaurant.place.id if restaurant.place is not None else None,
    )


def _build_day_items(
    ordered_activities: list[PoolActivity],
    travel_minutes: list[int | None],
    travel_meters: list[int | None],
    unresolved_activities: list[PoolActivity],
    lunch: PoolRestaurant | None,
    dinner: PoolRestaurant | None,
    hotel: HotelInfo,
    travel_modes: list[str],
    is_first_day: bool,
    is_last_day: bool,
    activity_start_min: int = _DEFAULT_ACTIVITY_START_MIN,
    hard_stop_min: int = _DEFAULT_HARD_STOP_MIN,
    weekday: int | None = None,
) -> tuple[list[ItineraryItem], int, int, int, int]:
    """Lay out one day's items within the user's activity window.

    Returns ``(items, scheduled_count, dropped_count, segments_with_routes,
    hours_warnings)``. Travel fields are only set between consecutive
    scheduled activities — meal/rest/hotel items keep them ``None``.

    When ``weekday`` is known (Google convention, 0=Sunday), venues that
    would be closed at their scheduled time are avoided where a fit exists
    (dinner shift, activity deferral) and otherwise flagged with a warning
    appended to their description — never dropped for hours reasons alone,
    and never blocking when hours data is unknown for a venue.
    """
    items: list[ItineraryItem] = []
    scheduled_count = 0
    dropped_count = 0
    segments_with_routes = 0
    hours_warnings = 0
    last_activity_item: ItineraryItem | None = None
    hotel_place_id = hotel.place.id if hotel.place is not None else None
    deferred: list[PoolActivity] = []
    hours_deferred: set[int] = set()
    earliest_start: dict[int, int] = {}

    def _mark_if_closed(meal_item: ItineraryItem, restaurant: PoolRestaurant | None, start_min: int) -> None:
        """Append an hours warning to ``meal_item`` if the restaurant is
        confirmed closed at ``start_min`` on ``weekday``. No-op when hours
        are unknown or ``weekday`` isn't set."""
        nonlocal hours_warnings
        if weekday is None or restaurant is None or restaurant.place is None:
            return
        try:
            if is_open_at(restaurant.place.opening_hours, weekday, start_min) is False:
                meal_item.description = _append_warning(
                    meal_item.description, _hours_warning(restaurant.name, start_min, weekday)
                )
                hours_warnings += 1
        except Exception:  # noqa: BLE001 - a bad hours check must not abort scheduling
            pass

    items.append(
        _make_item(
            8 * 60,
            9 * 60,
            "Breakfast",
            ItineraryItemType.MEAL,
            location_name=hotel.name,
            description="Breakfast at the hotel",
            place_id=hotel_place_id,
        )
    )

    t = 9 * 60
    if is_first_day:
        items.append(
            _make_item(
                t,
                t + 30,
                "Hotel check-in",
                ItineraryItemType.HOTEL,
                location_name=hotel.name,
                description=hotel.description,
                estimated_cost=hotel.estimated_cost_per_night,
                place_id=hotel_place_id,
            )
        )
        t += 30
    t = max(t, activity_start_min)

    lunch_placed = False
    all_activities = list(ordered_activities)
    i = 0
    n = len(all_activities)

    while i < n:
        act = all_activities[i]
        travel = travel_minutes[i - 1] if i > 0 and i - 1 < len(travel_minutes) else None
        gap = _ceil5(travel) if travel is not None else (0 if i == 0 else 15)
        candidate_start = t + gap
        duration = act.duration_minutes or 90
        candidate_end = candidate_start + duration

        if candidate_end > hard_stop_min:
            if act.priority == ItineraryItemPriority.OPTIONAL:
                dropped_count += 1
            else:
                deferred.append(act)
            i += 1
            continue

        if not lunch_placed and candidate_start >= _LUNCH_TRIGGER_MIN:
            lunch_item = _make_meal_item(t, t + 60, "Lunch", lunch)
            _mark_if_closed(lunch_item, lunch, t)
            items.append(lunch_item)
            t += 60
            lunch_placed = True
            continue

        description = act.description
        act_hours = act.place.opening_hours if act.place is not None else None
        try:
            open_state = is_open_at(act_hours, weekday, candidate_start) if weekday is not None else None
        except Exception:  # noqa: BLE001 - a bad hours check must not abort scheduling
            open_state = None

        if open_state is False and id(act) not in hours_deferred:
            duration_for_reopen = act.duration_minutes or 90
            try:
                reopen_at = next_open_minute(
                    act_hours, weekday, candidate_start, hard_stop_min - duration_for_reopen
                )
            except Exception:  # noqa: BLE001 - a bad hours check must not abort scheduling
                reopen_at = None
            prefers_later = act.best_time_of_day in ("afternoon", "evening", "any")
            if reopen_at is not None and prefers_later:
                hours_deferred.add(id(act))
                earliest_start[id(act)] = reopen_at
                deferred.append(act)
                i += 1
                continue
            description = _append_warning(description, _hours_warning(act.name, candidate_start, weekday))
            hours_warnings += 1

        item = _make_item(
            candidate_start,
            candidate_end,
            act.name,
            act.type,
            location_name=act.name,
            description=description,
            estimated_cost=act.estimated_cost,
            verified_cost=act.verified_cost,
            price_source=act.price_source,
            walking_intensity=act.walking_intensity,
            priority=act.priority,
            place_id=act.place.id if act.place is not None else None,
        )
        if last_activity_item is not None and travel is not None:
            last_activity_item.travel_time_to_next_minutes = travel
            last_activity_item.distance_to_next_meters = travel_meters[i - 1]
            last_activity_item.travel_mode_to_next = travel_modes[i - 1]
            segments_with_routes += 1
        items.append(item)
        last_activity_item = item
        t = candidate_end
        scheduled_count += 1
        i += 1

    for act in deferred + unresolved_activities:
        duration = act.duration_minutes or 90
        is_hours_deferred = id(act) in hours_deferred
        start = max(t, earliest_start.get(id(act), t))
        latest_end = (
            hard_stop_min
            if act.priority == ItineraryItemPriority.OPTIONAL
            else hard_stop_min + 60
        )
        description = act.description
        if start + duration > latest_end:
            if is_hours_deferred:
                # Never drop for hours reasons alone — fall back to the
                # ordinary retry slot with a warning instead of the shifted one.
                start = t
                if weekday is not None:
                    description = _append_warning(description, _hours_warning(act.name, start, weekday))
                    hours_warnings += 1
                if start + duration > latest_end:
                    dropped_count += 1
                    continue
            else:
                dropped_count += 1
                continue

        # Hours-deferred items are already known-open at their shifted
        # `start` (or already warned above); everything else here (ordinary
        # hard-stop overflow, unresolved activities, and every activity in
        # the naive `_fallback_plan` path, which routes activities through
        # `unresolved_activities` unconditionally) never went through the
        # main loop's hours check, so it happens here instead.
        if weekday is not None and not is_hours_deferred:
            act_hours = act.place.opening_hours if act.place is not None else None
            try:
                if is_open_at(act_hours, weekday, start) is False:
                    description = _append_warning(description, _hours_warning(act.name, start, weekday))
                    hours_warnings += 1
            except Exception:  # noqa: BLE001 - a bad hours check must not abort scheduling
                pass

        item = _make_item(
            start,
            start + duration,
            act.name,
            act.type,
            location_name=act.name,
            description=description,
            estimated_cost=act.estimated_cost,
            verified_cost=act.verified_cost,
            price_source=act.price_source,
            walking_intensity=act.walking_intensity,
            priority=act.priority,
        )
        items.append(item)
        last_activity_item = item
        t = start + duration
        scheduled_count += 1

    if not lunch_placed:
        if t >= _LATE_LUNCH_CUTOFF_MIN:
            # The day's clock already ran past a sane lunch window (a long
            # excursion consumed it) — note lunch as folded into that
            # excursion instead of stacking a full block after it, which
            # would only push dinner even later.
            items.append(
                _make_item(
                    _LUNCH_TRIGGER_MIN,
                    _LUNCH_TRIGGER_MIN,
                    "Lunch (on the go during the day's excursion)",
                    ItineraryItemType.MEAL,
                    priority=ItineraryItemPriority.OPTIONAL,
                )
            )
        else:
            t = max(t, _LUNCH_TRIGGER_MIN)
            lunch_item = _make_meal_item(t, t + 60, "Lunch", lunch)
            _mark_if_closed(lunch_item, lunch, t)
            items.append(lunch_item)
            t += 60
        lunch_placed = True

    dinner_start = max(t, _DINNER_MIN)
    if weekday is not None and dinner is not None and dinner.place is not None:
        try:
            if is_open_at(dinner.place.opening_hours, weekday, dinner_start) is False:
                shifted = next_open_minute(
                    dinner.place.opening_hours,
                    weekday,
                    dinner_start,
                    min(_DINNER_WINDOW_END, max(hard_stop_min, dinner_start)),
                )
                if shifted is not None:
                    dinner_start = shifted
        except Exception:  # noqa: BLE001 - a bad hours check must not abort scheduling
            pass
    dinner_item = _make_meal_item(dinner_start, dinner_start + 90, "Dinner", dinner)
    _mark_if_closed(dinner_item, dinner, dinner_start)
    items.append(dinner_item)
    t = dinner_start + 90

    if is_last_day:
        items.append(
            _make_item(
                t,
                t + 30,
                "Hotel check-out",
                ItineraryItemType.HOTEL,
                location_name=hotel.name,
                place_id=hotel_place_id,
            )
        )

    for order_index, item in enumerate(items):
        item.order_index = order_index

    return items, scheduled_count, dropped_count, segments_with_routes, hours_warnings


# --- Entry point ----------------------------------------------------------------


class DayPlannerService:
    """Clusters a place pool into days and schedules each day's time blocks."""

    @staticmethod
    def plan_days(
        db: Session,
        agent_run_id: int,
        num_days: int,
        hotel: HotelInfo,
        activities: list[PoolActivity],
        restaurants: list[PoolRestaurant],
        travel_mode: str = "walking",
        max_walk_minutes: int | None = None,
        activity_start_min: int = _DEFAULT_ACTIVITY_START_MIN,
        hard_stop_min: int = _DEFAULT_HARD_STOP_MIN,
        start_date: date | None = None,
    ) -> PlanResult:
        try:
            return DayPlannerService._plan_days_inner(
                db,
                agent_run_id,
                num_days,
                hotel,
                activities,
                restaurants,
                travel_mode,
                max_walk_minutes,
                activity_start_min,
                hard_stop_min,
                start_date=start_date,
            )
        except Exception as e:  # noqa: BLE001 — a bad trip must not abort the run
            return DayPlannerService._fallback_plan(
                num_days,
                hotel,
                activities,
                restaurants,
                str(e),
                activity_start_min,
                hard_stop_min,
                start_date=start_date,
            )

    @staticmethod
    def _plan_days_inner(
        db: Session,
        agent_run_id: int,
        num_days: int,
        hotel: HotelInfo,
        activities: list[PoolActivity],
        restaurants: list[PoolRestaurant],
        travel_mode: str,
        max_walk_minutes: int | None = None,
        activity_start_min: int = _DEFAULT_ACTIVITY_START_MIN,
        hard_stop_min: int = _DEFAULT_HARD_STOP_MIN,
        *,
        start_date: date | None = None,
    ) -> PlanResult:
        max_walk_minutes = max_walk_minutes if max_walk_minutes is not None else _DEFAULT_MAX_WALK_MINUTES
        num_days = max(1, num_days)
        resolved = [a for a in activities if a.place is not None]
        unresolved = [a for a in activities if a.place is None]

        points = [(a.place.lat, a.place.lng) for a in resolved]
        labels = _kmeans_labels(points, num_days)
        labels = _balance_clusters(labels, points, num_days)

        hotel_coord = (hotel.place.lat, hotel.place.lng) if hotel.place is not None else None
        cluster_order = _order_clusters(labels, points, num_days, hotel_coord)

        buckets: list[list[PoolActivity]] = [[] for _ in range(num_days)]
        for i, act in enumerate(resolved):
            buckets[labels[i]].append(act)

        # Round-robin unresolved activities onto the currently-smallest days.
        for act in unresolved:
            target = min(range(num_days), key=lambda d: len(buckets[d]))
            buckets[target].append(act)

        lunch_options = [r for r in restaurants if r.meal_type == "lunch"]
        dinner_options = [r for r in restaurants if r.meal_type == "dinner"]
        used_lunch: set[int] = set()
        used_dinner: set[int] = set()

        days: list[DayPlan] = []
        total_scheduled = 0
        total_dropped = 0
        total_segments = 0
        total_rest_stops = 0
        total_hours_warnings = 0

        for day_position, cluster_id in enumerate(cluster_order):
            day_number = day_position + 1
            weekday = google_weekday(start_date + timedelta(days=day_position)) if start_date is not None else None
            bucket = buckets[cluster_id]
            bucket_resolved = [a for a in bucket if a.place is not None]
            bucket_unresolved = [a for a in bucket if a.place is None]

            ordered, travel_minutes, travel_meters, travel_modes = _sequence_day_activities(
                db, agent_run_id, bucket_resolved, hotel_coord, travel_mode, max_walk_minutes
            )
            ordered, travel_minutes, travel_meters, travel_modes, stops_inserted = _insert_rest_stops(
                db,
                agent_run_id,
                ordered,
                travel_minutes,
                travel_meters,
                travel_modes,
                max_walk_minutes,
                weekday=weekday,
            )
            total_rest_stops += stops_inserted

            day_centroid = None
            if bucket_resolved:
                day_centroid = (
                    sum(a.place.lat for a in bucket_resolved) / len(bucket_resolved),
                    sum(a.place.lng for a in bucket_resolved) / len(bucket_resolved),
                )
            near = day_centroid or hotel_coord

            lunch = _pick_restaurant(lunch_options, used_lunch, near, weekday, *_LUNCH_WINDOW)
            dinner_window = (_DINNER_MIN, min(_DINNER_WINDOW_END, max(hard_stop_min, _DINNER_MIN)))
            dinner = _pick_restaurant(dinner_options, used_dinner, near, weekday, *dinner_window)

            items, scheduled, dropped, segments, hours_warnings = _build_day_items(
                ordered,
                travel_minutes,
                travel_meters,
                bucket_unresolved,
                lunch,
                dinner,
                hotel,
                travel_modes,
                is_first_day=(day_position == 0),
                is_last_day=(day_position == len(cluster_order) - 1),
                activity_start_min=activity_start_min,
                hard_stop_min=hard_stop_min,
                weekday=weekday,
            )
            total_hours_warnings += hours_warnings

            walking_minutes = sum(
                item.travel_time_to_next_minutes
                for item in items
                if item.travel_mode_to_next == "walking" and item.travel_time_to_next_minutes is not None
            )
            transit_minutes = sum(
                item.travel_time_to_next_minutes
                for item in items
                if item.travel_mode_to_next in ("transit", "driving") and item.travel_time_to_next_minutes is not None
            )
            distance_meters = sum(
                item.distance_to_next_meters for item in items if item.distance_to_next_meters is not None
            )

            days.append(
                DayPlan(
                    day_number=day_number,
                    items=items,
                    route_optimized=segments > 0,
                    total_walking_minutes=walking_minutes if segments > 0 else None,
                    total_transit_minutes=transit_minutes if segments > 0 else None,
                    total_distance_meters=distance_meters if segments > 0 else None,
                )
            )
            total_scheduled += scheduled
            total_dropped += dropped
            total_segments += segments

        return PlanResult(
            days=days,
            activities_scheduled=total_scheduled,
            activities_dropped=total_dropped,
            segments_with_routes=total_segments,
            degraded=False,
            rest_stops_inserted=total_rest_stops,
            hours_warnings_added=total_hours_warnings,
        )

    @staticmethod
    def _fallback_plan(
        num_days: int,
        hotel: HotelInfo,
        activities: list[PoolActivity],
        restaurants: list[PoolRestaurant],
        reason: str,
        activity_start_min: int = _DEFAULT_ACTIVITY_START_MIN,
        hard_stop_min: int = _DEFAULT_HARD_STOP_MIN,
        *,
        start_date: date | None = None,
    ) -> PlanResult:
        """Naive round-robin day assignment with template times, no travel
        data. Used when clustering/scheduling raises for any reason."""
        num_days = max(1, num_days)
        buckets: list[list[PoolActivity]] = [[] for _ in range(num_days)]
        for i, act in enumerate(activities):
            buckets[i % num_days].append(act)

        lunch_options = [r for r in restaurants if r.meal_type == "lunch"]
        dinner_options = [r for r in restaurants if r.meal_type == "dinner"]

        days: list[DayPlan] = []
        total_scheduled = 0
        total_dropped = 0
        total_hours_warnings = 0

        for day_position in range(num_days):
            weekday = google_weekday(start_date + timedelta(days=day_position)) if start_date is not None else None
            bucket = buckets[day_position]
            lunch = lunch_options[day_position % len(lunch_options)] if lunch_options else None
            dinner = dinner_options[day_position % len(dinner_options)] if dinner_options else None

            items, scheduled, dropped, _segments, hours_warnings = _build_day_items(
                [],
                [],
                [],
                bucket,
                lunch,
                dinner,
                hotel,
                travel_modes=[],
                is_first_day=(day_position == 0),
                is_last_day=(day_position == num_days - 1),
                activity_start_min=activity_start_min,
                hard_stop_min=hard_stop_min,
                weekday=weekday,
            )
            days.append(
                DayPlan(
                    day_number=day_position + 1,
                    items=items,
                    route_optimized=False,
                    total_walking_minutes=None,
                    total_transit_minutes=None,
                    total_distance_meters=None,
                )
            )
            total_scheduled += scheduled
            total_dropped += dropped
            total_hours_warnings += hours_warnings

        return PlanResult(
            days=days,
            activities_scheduled=total_scheduled,
            activities_dropped=total_dropped,
            segments_with_routes=0,
            degraded=True,
            degraded_reason=reason,
            hours_warnings_added=total_hours_warnings,
        )
