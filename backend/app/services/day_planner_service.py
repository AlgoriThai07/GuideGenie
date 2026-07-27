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
from app.services.route_service import RouteService

_EARTH_RADIUS_M = 6_371_000.0

_ACTIVITY_START_MIN = 9 * 60 + 30  # 09:30
_LUNCH_TRIGGER_MIN = 12 * 60  # 12:00
_REST_TRIGGER_MIN = 15 * 60 + 30  # 15:30
_DINNER_MIN = 19 * 60  # 19:00
_HARD_STOP_MIN = 18 * 60 + 30  # 18:30 — after this, only optional items get dropped


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
    degraded_reason: str | None = None


# --- Geometry helpers --------------------------------------------------------


def _haversine_meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lng1 = math.radians(a[0]), math.radians(a[1])
    lat2, lng2 = math.radians(b[0]), math.radians(b[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


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


def _sequence_day_activities(
    db: Session,
    agent_run_id: int,
    activities: list[PoolActivity],
    hotel_coord: tuple[float, float] | None,
    travel_mode: str,
) -> tuple[list[PoolActivity], list[int | None], list[int | None]]:
    """Order ``activities`` (all with a resolved place) by nearest-neighbor
    travel time. Returns ``(ordered, travel_minutes, travel_meters)`` where
    the travel lists have length ``len(activities) - 1`` (gap i is between
    ordered[i] and ordered[i+1])."""
    n = len(activities)
    if n == 0:
        return [], [], []
    if n == 1:
        return list(activities), [], []

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
    ordered = [activities[i] for i in order]
    travel_minutes = [minutes[order[i]][order[i + 1]] for i in range(n - 1)]
    travel_meters = [meters[order[i]][order[i + 1]] for i in range(n - 1)]
    return ordered, travel_minutes, travel_meters


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
    travel_mode: str,
    is_first_day: bool,
    is_last_day: bool,
) -> tuple[list[ItineraryItem], int, int, int]:
    """Lay out one day's items on a fixed time-block template.

    Returns ``(items, scheduled_count, dropped_count, segments_with_routes)``.
    Travel fields are only set between consecutive scheduled activities —
    meal/rest/hotel items keep them ``None``.
    """
    items: list[ItineraryItem] = []
    scheduled_count = 0
    dropped_count = 0
    segments_with_routes = 0
    last_activity_item: ItineraryItem | None = None
    hotel_place_id = hotel.place.id if hotel.place is not None else None

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
    t = max(t, _ACTIVITY_START_MIN)

    lunch_placed = False
    rest_placed = False
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

        if candidate_end > _HARD_STOP_MIN:
            if act.priority == ItineraryItemPriority.OPTIONAL:
                dropped_count += 1
                i += 1
                continue
            dropped_count += n - i
            break

        if not lunch_placed and candidate_start >= _LUNCH_TRIGGER_MIN:
            lunch_item = _make_meal_item(t, t + 60, "Lunch", lunch)
            items.append(lunch_item)
            t += 60
            lunch_placed = True
            continue

        if not rest_placed and candidate_start >= _REST_TRIGGER_MIN:
            items.append(_make_item(t, t + 30, "Rest", ItineraryItemType.REST, priority=ItineraryItemPriority.OPTIONAL))
            t += 30
            rest_placed = True
            continue

        item = _make_item(
            candidate_start,
            candidate_end,
            act.name,
            act.type,
            location_name=act.name,
            description=act.description,
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
            last_activity_item.travel_mode_to_next = travel_mode
            segments_with_routes += 1
        items.append(item)
        last_activity_item = item
        t = candidate_end
        scheduled_count += 1
        i += 1

    for act in unresolved_activities:
        duration = act.duration_minutes or 90
        if t + duration > _HARD_STOP_MIN + 60:
            dropped_count += 1
            continue
        item = _make_item(
            t,
            t + duration,
            act.name,
            act.type,
            location_name=act.name,
            description=act.description,
            estimated_cost=act.estimated_cost,
            verified_cost=act.verified_cost,
            price_source=act.price_source,
            walking_intensity=act.walking_intensity,
            priority=act.priority,
        )
        items.append(item)
        last_activity_item = item
        t += duration
        scheduled_count += 1

    if not lunch_placed:
        t = max(t, _LUNCH_TRIGGER_MIN)
        items.append(_make_meal_item(t, t + 60, "Lunch", lunch))
        t += 60
        lunch_placed = True

    if not rest_placed and t < _DINNER_MIN:
        t = max(t, _REST_TRIGGER_MIN)
        items.append(_make_item(t, t + 30, "Rest", ItineraryItemType.REST, priority=ItineraryItemPriority.OPTIONAL))
        t += 30

    dinner_start = max(t, _DINNER_MIN)
    items.append(_make_meal_item(dinner_start, dinner_start + 90, "Dinner", dinner))
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

    return items, scheduled_count, dropped_count, segments_with_routes


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
    ) -> PlanResult:
        try:
            return DayPlannerService._plan_days_inner(
                db, agent_run_id, num_days, hotel, activities, restaurants, travel_mode
            )
        except Exception as e:  # noqa: BLE001 — a bad trip must not abort the run
            return DayPlannerService._fallback_plan(num_days, hotel, activities, restaurants, str(e))

    @staticmethod
    def _plan_days_inner(
        db: Session,
        agent_run_id: int,
        num_days: int,
        hotel: HotelInfo,
        activities: list[PoolActivity],
        restaurants: list[PoolRestaurant],
        travel_mode: str,
    ) -> PlanResult:
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

        def pick_restaurant(options: list[PoolRestaurant], used: set[int], near: tuple[float, float] | None) -> PoolRestaurant | None:
            available = [r for r in options if r.index not in used]
            if not available:
                available = options
            if not available:
                return None
            with_place = [r for r in available if r.place is not None]
            if with_place and near is not None:
                chosen = min(with_place, key=lambda r: _haversine_meters(near, (r.place.lat, r.place.lng)))
            else:
                chosen = available[0]
            used.add(chosen.index)
            return chosen

        days: list[DayPlan] = []
        total_scheduled = 0
        total_dropped = 0
        total_segments = 0

        for day_position, cluster_id in enumerate(cluster_order):
            day_number = day_position + 1
            bucket = buckets[cluster_id]
            bucket_resolved = [a for a in bucket if a.place is not None]
            bucket_unresolved = [a for a in bucket if a.place is None]

            ordered, travel_minutes, travel_meters = _sequence_day_activities(
                db, agent_run_id, bucket_resolved, hotel_coord, travel_mode
            )

            day_centroid = None
            if bucket_resolved:
                day_centroid = (
                    sum(a.place.lat for a in bucket_resolved) / len(bucket_resolved),
                    sum(a.place.lng for a in bucket_resolved) / len(bucket_resolved),
                )
            near = day_centroid or hotel_coord

            lunch = pick_restaurant(lunch_options, used_lunch, near)
            dinner = pick_restaurant(dinner_options, used_dinner, near)

            items, scheduled, dropped, segments = _build_day_items(
                ordered,
                travel_minutes,
                travel_meters,
                bucket_unresolved,
                lunch,
                dinner,
                hotel,
                travel_mode,
                is_first_day=(day_position == 0),
                is_last_day=(day_position == len(cluster_order) - 1),
            )

            walking_minutes = sum(
                item.travel_time_to_next_minutes
                for item in items
                if item.travel_mode_to_next == "walking" and item.travel_time_to_next_minutes is not None
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
                    total_transit_minutes=None,
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
        )

    @staticmethod
    def _fallback_plan(
        num_days: int,
        hotel: HotelInfo,
        activities: list[PoolActivity],
        restaurants: list[PoolRestaurant],
        reason: str,
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

        for day_position in range(num_days):
            bucket = buckets[day_position]
            lunch = lunch_options[day_position % len(lunch_options)] if lunch_options else None
            dinner = dinner_options[day_position % len(dinner_options)] if dinner_options else None

            items, scheduled, dropped, _segments = _build_day_items(
                [],
                [],
                [],
                bucket,
                lunch,
                dinner,
                hotel,
                travel_mode="walking",
                is_first_day=(day_position == 0),
                is_last_day=(day_position == num_days - 1),
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

        return PlanResult(
            days=days,
            activities_scheduled=total_scheduled,
            activities_dropped=total_dropped,
            segments_with_routes=0,
            degraded=True,
            degraded_reason=reason,
        )
