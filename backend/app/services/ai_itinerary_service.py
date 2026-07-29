"""AI itinerary generation service (Sprint 2, redesigned in Sprint 4).

Turns an existing trip + its preferences into a saved day-by-day itinerary.
The LLM proposes a flat *pool* of real places (one hotel, many activities/
events, many restaurant options) — it does not assign days or times. The
backend clusters, sequences, and schedules; a second, cheap LLM call then
writes day themes/summaries. Business logic lives here (not in route
handlers), per the project's clean-architecture rule.

The single entrypoint is :func:`generate_itinerary`. It records an
``AgentRun`` and one ``AgentStep`` per pipeline stage (``load_trip_preferences``
→ ``build_prompt`` → ``call_llm`` → ``parse_response`` → ``resolve_places`` →
``resolve_prices`` → ``optimize_route`` → ``narrate_days`` →
``save_itinerary``), so a run is observable while in progress and its outcome
is auditable afterwards.

Failure handling: a run always ends ``completed`` or ``failed`` — never stuck
in ``running``. Only a missing trip (before any run is created) raises
(:class:`TripNotFoundError`); every failure after the run exists is recorded on
the run (``status=failed`` + ``error_message``) and the failed run is returned
so the caller can inspect it. ``optimize_route`` and ``narrate_days`` never
fail the run themselves — they degrade to a fallback and log a warning.

Uses the Gemini API (``google-genai`` SDK) with JSON response mode.
"""

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from pydantic import ValidationError
from sqlalchemy import delete, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRun, AgentRunStatus, AgentStep, AgentStepName
from app.models.itinerary import ItineraryDay, ItineraryItemType
from app.models.place import Place
from app.models.tool_call import ToolCall
from app.models.trip import Trip, TripPreference
from app.schemas.itinerary import DayNarrationBatchAI, TripPlanAIResponse
from app.services.day_planner_service import (
    DayPlan,
    DayPlannerService,
    HotelInfo,
    PoolActivity,
    PoolRestaurant,
)
from app.services.places_service import PlacesService
from app.services.price_service import PriceQuery, PriceResult, PriceService

# Prompt/response text stored in JSON step columns is truncated to keep rows
# small; the full itinerary is persisted separately as day/item rows.
_MAX_STORED_TEXT = 8000

# Composite key into resolved_places / verified_prices: ("hotel", 0),
# ("activity", i), or ("restaurant", i).
_PoolKey = tuple[str, int]


class TripNotFoundError(ValueError):
    """Raised when the requested trip does not exist."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _truncate(text: str) -> str:
    if len(text) <= _MAX_STORED_TEXT:
        return text
    return text[:_MAX_STORED_TEXT] + "... [truncated]"


def _log_step(
    db: Session,
    run_id: int,
    name: AgentStepName,
    status: AgentRunStatus,
    *,
    input_json: dict[str, Any] | None = None,
    output_json: dict[str, Any] | None = None,
    error_message: str | None = None,
    latency_ms: int | None = None,
) -> None:
    """Persist a single agent step and commit it immediately."""
    step = AgentStep(
        agent_run_id=run_id,
        step_name=name,
        status=status,
        input_json=input_json,
        output_json=output_json,
        error_message=error_message,
        latency_ms=latency_ms,
    )
    db.add(step)
    db.commit()


def _fail_run(db: Session, run: AgentRun, message: str) -> AgentRun:
    """Mark a run failed with an error message and return it."""
    run.status = AgentRunStatus.FAILED
    run.error_message = message
    run.completed_at = _now()
    db.commit()
    db.refresh(run)
    return run


def _preferences_summary(pref: TripPreference | None) -> dict[str, Any]:
    """Flatten a (possibly missing) preference row into a plain dict."""
    if pref is None:
        return {
            "travel_style": None,
            "max_walking_minutes_between_stops": None,
            "max_total_walking_minutes_per_day": None,
            "interests": [],
            "hotel_preferences": [],
            "food_preferences": [],
            "must_visit_places": [],
            "avoid_places": [],
        }
    return {
        "travel_style": pref.travel_style,
        "max_walking_minutes_between_stops": pref.max_walking_minutes_between_stops,
        "max_total_walking_minutes_per_day": pref.max_total_walking_minutes_per_day,
        "interests": list(pref.interests or []),
        "hotel_preferences": list(pref.hotel_preferences or []),
        "food_preferences": list(pref.food_preferences or []),
        "must_visit_places": list(pref.must_visit_places or []),
        "avoid_places": list(pref.avoid_places or []),
    }


def _compute_num_days(trip: Trip) -> int:
    """Trip length in inclusive days, or a sane default if dates are unset."""
    if trip.start_date and trip.end_date:
        return max(1, (trip.end_date - trip.start_date).days + 1)
    return 3


def _build_system_prompt(num_days: int) -> str:
    """Static-shaped system prompt asking for a place *pool*, not a schedule.

    The backend (day_planner_service) owns clustering, sequencing, and
    timing — the LLM only proposes real, named places and a rough sense of
    duration/priority/best time of day for each.
    """
    min_activities = num_days * 3
    max_activities = num_days * 4
    meals_each = num_days + 1
    return (
        "You are an expert travel-planning assistant. You produce a POOL of "
        "real places for a trip — NOT a day-by-day schedule. A separate "
        "system clusters these places into days and builds the schedule.\n\n"
        "OUTPUT FORMAT:\n"
        "- Return ONLY a single valid JSON object. No markdown, no code fences, "
        "no commentary before or after.\n"
        "- The JSON MUST match this exact shape (camelCase keys):\n"
        "{\n"
        '  "tripTitle": string,\n'
        '  "overview": string,\n'
        '  "hotel": {"name": string, "description": string, '
        '"estimatedCostPerNight": number},\n'
        '  "activities": [{\n'
        '    "name": string, "type": one of ["activity","event"],\n'
        '    "durationMinutes": integer, '
        '"priority": one of ["required","recommended","optional"],\n'
        '    "walkingIntensity": one of ["low","medium","high"], '
        '"description": string,\n'
        '    "estimatedCost": number, '
        '"bestTimeOfDay": one of ["morning","afternoon","evening","any"]\n'
        "  }],\n"
        '  "restaurants": [{\n'
        '    "name": string, "mealType": one of ["lunch","dinner"], '
        '"description": string, "estimatedCost": number\n'
        "  }]\n"
        "}\n\n"
        "PLANNING RULES:\n"
        f"- Propose between {min_activities} and {max_activities} activities "
        "total for the whole trip. Do NOT assign them to days or times "
        "yourself — that is handled separately.\n"
        f"- Propose at least {meals_each} lunch restaurant options and at "
        f"least {meals_each} dinner restaurant options: real, distinct "
        "venues so a variety pack is available (breakfast is assumed to be "
        "at the hotel, do not propose breakfast venues).\n"
        "- Exactly ONE hotel for the entire trip.\n"
        "- name MUST be a specific, real, named venue — a real restaurant, "
        "cafe, hotel, museum, or landmark name that plausibly exists in the "
        "destination (e.g. \"Ichiran Ramen Shinjuku\", not \"a local ramen "
        "restaurant\" or \"a museum\"). Never use a generic description in "
        "place of a real name.\n"
        "- Do NOT invent exact ratings, review counts, street addresses, or "
        "opening hours for a venue — those are looked up separately from a "
        "real source. A plausible real name is all that's needed here.\n"
        "- durationMinutes should reflect a realistic visit length (e.g. a "
        "quick landmark: 30-60, a museum: 90-150, a full-day excursion: "
        "240+).\n"
        "- Align walkingIntensity with realistic effort for a traveler with "
        "average walking tolerance.\n"
        "- Respect interests, food preferences, hotel preferences, "
        "must-visit places, and the avoid list."
    )


def _build_user_prompt(trip: Trip, pref: TripPreference | None, num_days: int) -> str:
    """Per-trip user prompt built from the trip and its preferences."""
    p = _preferences_summary(pref)
    start = trip.start_date.isoformat() if trip.start_date else "unspecified"
    end = trip.end_date.isoformat() if trip.end_date else "unspecified"
    budget = f"{trip.budget}" if trip.budget is not None else "no fixed budget"

    lines = [
        "Propose a pool of real places for the following trip.",
        "",
        f"Title: {trip.title}",
        f"Destination: {trip.destination}",
        f"Dates: {start} to {end} (inclusive, {num_days} day(s))",
        f"Travelers: {trip.travelers}",
        f"Total budget: {budget}",
        "",
        "Traveler preferences:",
        f"- Travel style: {p['travel_style'] or 'not specified'}",
        "- Max walking minutes between stops: "
        f"{p['max_walking_minutes_between_stops'] or 'not specified'}",
        "- Max total walking minutes per day: "
        f"{p['max_total_walking_minutes_per_day'] or 'not specified'}",
        f"- Interests: {', '.join(p['interests']) or 'none given'}",
        f"- Food preferences: {', '.join(p['food_preferences']) or 'none given'}",
        f"- Hotel preferences: {', '.join(p['hotel_preferences']) or 'none given'}",
        f"- Must-visit places: {', '.join(p['must_visit_places']) or 'none given'}",
        f"- Avoid: {', '.join(p['avoid_places']) or 'none given'}",
        "",
        "Return the place pool as the JSON object described in the system "
        "instructions.",
    ]
    return "\n".join(lines)


def _fallback_theme_summary(day: DayPlan) -> tuple[str, str]:
    """Deterministic theme/summary when narrate_days can't produce one."""
    activity_titles = [
        item.title
        for item in day.items
        if item.type in (ItineraryItemType.ACTIVITY, ItineraryItemType.EVENT)
    ]
    if activity_titles:
        return activity_titles[0], ", ".join(activity_titles)
    return f"Day {day.day_number}", "A relaxed day."


def generate_itinerary(db: Session, trip_id: int) -> AgentRun:
    """Generate, validate, and persist an itinerary for ``trip_id``.

    Returns the ``AgentRun``. On success it is ``completed``; on any failure
    after the run is created it is ``failed`` with an ``error_message``. Raises
    :class:`TripNotFoundError` only when the trip does not exist.
    """
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise TripNotFoundError(f"Trip {trip_id} not found")

    pref = trip.preference
    num_days = _compute_num_days(trip)

    run = AgentRun(
        trip_id=trip_id,
        status=AgentRunStatus.RUNNING,
        model_used=settings.AI_MODEL,
        started_at=_now(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        # --- Step 1: load_trip_preferences ---------------------------------
        t0 = time.perf_counter()
        summary = {
            "trip": {
                "title": trip.title,
                "destination": trip.destination,
                "start_date": trip.start_date.isoformat() if trip.start_date else None,
                "end_date": trip.end_date.isoformat() if trip.end_date else None,
                "travelers": trip.travelers,
                "budget": str(trip.budget) if trip.budget is not None else None,
                "num_days": num_days,
            },
            "preferences": _preferences_summary(pref),
            "has_preferences": pref is not None,
        }
        _log_step(
            db,
            run.id,
            AgentStepName.LOAD_TRIP_PREFERENCES,
            AgentRunStatus.COMPLETED,
            input_json={"trip_id": trip_id},
            output_json=summary,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 2: build_prompt ------------------------------------------
        t0 = time.perf_counter()
        system_prompt = _build_system_prompt(num_days)
        user_prompt = _build_user_prompt(trip, pref, num_days)
        _log_step(
            db,
            run.id,
            AgentStepName.BUILD_PROMPT,
            AgentRunStatus.COMPLETED,
            output_json={
                "system": _truncate(system_prompt),
                "user": _truncate(user_prompt),
            },
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 3: call_llm ----------------------------------------------
        if not settings.GEMINI_API_KEY:
            message = "missing GEMINI_API_KEY"
            _log_step(
                db,
                run.id,
                AgentStepName.CALL_LLM,
                AgentRunStatus.FAILED,
                error_message=message,
            )
            return _fail_run(db, run, message)

        t0 = time.perf_counter()
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            completion = client.models.generate_content(
                model=settings.AI_MODEL,
                contents=user_prompt,
                config={
                    "system_instruction": system_prompt,
                    "response_mime_type": "application/json",
                },
            )
            raw = completion.text or ""
        except genai_errors.APIError as e:
            message = f"LLM API call failed: {e}"
            _log_step(
                db,
                run.id,
                AgentStepName.CALL_LLM,
                AgentRunStatus.FAILED,
                error_message=message,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return _fail_run(db, run, message)

        _log_step(
            db,
            run.id,
            AgentStepName.CALL_LLM,
            AgentRunStatus.COMPLETED,
            input_json={"model": settings.AI_MODEL, "prompt_chars": len(user_prompt)},
            output_json={"raw": _truncate(raw)},
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 4: parse_response ------------------------------------------
        t0 = time.perf_counter()
        try:
            parsed = TripPlanAIResponse.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            message = f"Invalid place-pool JSON from LLM: {e}"
            _log_step(
                db,
                run.id,
                AgentStepName.PARSE_RESPONSE,
                AgentRunStatus.FAILED,
                input_json={"raw": _truncate(raw)},
                error_message=message,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            return _fail_run(db, run, message)

        _log_step(
            db,
            run.id,
            AgentStepName.PARSE_RESPONSE,
            AgentRunStatus.COMPLETED,
            output_json=parsed.model_dump(mode="json"),
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 5: resolve_places -------------------------------------------
        t0 = time.perf_counter()
        resolved_places: dict[_PoolKey, Place | None] = {}
        resolved_count = 0
        failed_count = 0
        skipped_count = 0

        if settings.GOOGLE_PLACES_API_KEY:
            hotel_place = PlacesService.resolve_item_place(
                db, run.id, parsed.hotel.name, trip.destination
            )
            resolved_places[("hotel", 0)] = hotel_place
            resolved_count += 1 if hotel_place is not None else 0
            failed_count += 0 if hotel_place is not None else 1

            for i, act in enumerate(parsed.activities):
                place = PlacesService.resolve_item_place(
                    db, run.id, act.name, trip.destination
                )
                resolved_places[("activity", i)] = place
                resolved_count += 1 if place is not None else 0
                failed_count += 0 if place is not None else 1

            for i, rest in enumerate(parsed.restaurants):
                place = PlacesService.resolve_item_place(
                    db, run.id, rest.name, trip.destination
                )
                resolved_places[("restaurant", i)] = place
                resolved_count += 1 if place is not None else 0
                failed_count += 0 if place is not None else 1
        else:
            skipped_count = 1 + len(parsed.activities) + len(parsed.restaurants)

        resolve_output: dict[str, Any] = {
            "resolved": resolved_count,
            "failed": failed_count,
            "skipped": skipped_count,
        }
        if resolved_count == 0 and failed_count > 0:
            resolve_output["warning"] = "all place lookups failed"

        _log_step(
            db,
            run.id,
            AgentStepName.RESOLVE_PLACES,
            AgentRunStatus.COMPLETED,
            output_json=resolve_output,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 6: resolve_prices -------------------------------------------
        t0 = time.perf_counter()
        price_queries: list[PriceQuery] = []
        price_keys: list[_PoolKey] = []

        hotel_place_resolved = resolved_places.get(("hotel", 0))
        if hotel_place_resolved is not None:
            price_queries.append(
                PriceQuery(
                    item_title=f"1 night at {parsed.hotel.name}",
                    place=hotel_place_resolved,
                )
            )
            price_keys.append(("hotel", 0))

        for i, act in enumerate(parsed.activities):
            place = resolved_places.get(("activity", i))
            if place is not None:
                price_queries.append(PriceQuery(item_title=act.name, place=place))
                price_keys.append(("activity", i))

        for i, rest in enumerate(parsed.restaurants):
            place = resolved_places.get(("restaurant", i))
            if place is not None:
                price_queries.append(PriceQuery(item_title=rest.name, place=place))
                price_keys.append(("restaurant", i))

        verified_prices: dict[_PoolKey, PriceResult] = {}
        if price_queries:
            price_results = PriceService.search_batch_prices(
                db, run.id, price_queries, trip.destination
            )
            for position, key in enumerate(price_keys):
                if position in price_results:
                    verified_prices[key] = price_results[position]

        _log_step(
            db,
            run.id,
            AgentStepName.RESOLVE_PRICES,
            AgentRunStatus.COMPLETED,
            output_json={
                "queried": len(price_queries),
                "priced": len(verified_prices),
            },
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 7: optimize_route --------------------------------------------
        t0 = time.perf_counter()
        hotel_info = HotelInfo(
            name=parsed.hotel.name,
            description=parsed.hotel.description,
            estimated_cost_per_night=parsed.hotel.estimated_cost_per_night,
            place=resolved_places.get(("hotel", 0)),
        )

        pool_activities: list[PoolActivity] = []
        for i, act in enumerate(parsed.activities):
            price_result = verified_prices.get(("activity", i))
            pool_activities.append(
                PoolActivity(
                    index=i,
                    name=act.name,
                    type=act.type,
                    duration_minutes=act.duration_minutes,
                    priority=act.priority,
                    walking_intensity=act.walking_intensity,
                    description=act.description,
                    estimated_cost=act.estimated_cost,
                    verified_cost=price_result.price if price_result else None,
                    price_source="gemini_google_search" if price_result else None,
                    place=resolved_places.get(("activity", i)),
                    best_time_of_day=act.best_time_of_day,
                )
            )

        pool_restaurants: list[PoolRestaurant] = []
        for i, rest in enumerate(parsed.restaurants):
            price_result = verified_prices.get(("restaurant", i))
            pool_restaurants.append(
                PoolRestaurant(
                    index=i,
                    name=rest.name,
                    meal_type=rest.meal_type,
                    description=rest.description,
                    estimated_cost=rest.estimated_cost,
                    verified_cost=price_result.price if price_result else None,
                    price_source="gemini_google_search" if price_result else None,
                    place=resolved_places.get(("restaurant", i)),
                )
            )

        try:
            if not settings.GOOGLE_ROUTES_API_KEY:
                plan = DayPlannerService._fallback_plan(
                    num_days,
                    hotel_info,
                    pool_activities,
                    pool_restaurants,
                    "no GOOGLE_ROUTES_API_KEY",
                )
                route_output: dict[str, Any] = {
                    "skipped": "no GOOGLE_ROUTES_API_KEY",
                    "days_processed": len(plan.days),
                    "activities_scheduled": plan.activities_scheduled,
                    "activities_dropped": plan.activities_dropped,
                    "segments_with_routes": 0,
                    "total_tool_calls": 0,
                }
            else:
                tool_calls_before = (
                    db.query(func.count(ToolCall.id))
                    .filter(
                        ToolCall.agent_run_id == run.id,
                        ToolCall.tool_name == "google_distance_matrix",
                    )
                    .scalar()
                    or 0
                )

                plan = DayPlannerService.plan_days(
                    db,
                    run.id,
                    num_days,
                    hotel_info,
                    pool_activities,
                    pool_restaurants,
                    travel_mode="walking",
                    max_walk_minutes=p["max_walking_minutes_between_stops"],
                )

                tool_calls_after = (
                    db.query(func.count(ToolCall.id))
                    .filter(
                        ToolCall.agent_run_id == run.id,
                        ToolCall.tool_name == "google_distance_matrix",
                    )
                    .scalar()
                    or 0
                )

                route_output = {
                    "days_processed": len(plan.days),
                    "days_optimized": sum(1 for d in plan.days if d.route_optimized),
                    "segments_with_routes": plan.segments_with_routes,
                    "activities_scheduled": plan.activities_scheduled,
                    "activities_dropped": plan.activities_dropped,
                    "total_tool_calls": tool_calls_after - tool_calls_before,
                }
                if plan.degraded:
                    route_output["warning"] = (
                        f"optimize_route degraded: {plan.degraded_reason}"
                    )
        except Exception as e:  # noqa: BLE001 — optimize_route must never fail the run
            plan = DayPlannerService._fallback_plan(
                num_days, hotel_info, pool_activities, pool_restaurants, str(e)
            )
            route_output = {
                "warning": f"optimize_route failed: {e}",
                "days_processed": len(plan.days),
                "activities_scheduled": plan.activities_scheduled,
                "activities_dropped": plan.activities_dropped,
                "segments_with_routes": 0,
                "total_tool_calls": 0,
            }

        _log_step(
            db,
            run.id,
            AgentStepName.OPTIMIZE_ROUTE,
            AgentRunStatus.COMPLETED,
            output_json=route_output,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Step 8: narrate_days -----------------------------------------------
        t0 = time.perf_counter()
        day_themes: dict[int, tuple[str, str]] = {}
        try:
            if not settings.GEMINI_API_KEY:
                raise RuntimeError("no GEMINI_API_KEY")

            skeleton_lines = []
            for day in plan.days:
                titles = [
                    item.title
                    for item in day.items
                    if item.type in (ItineraryItemType.ACTIVITY, ItineraryItemType.EVENT)
                ]
                stops = " -> ".join(titles) if titles else "Free day"
                skeleton_lines.append(f"Day {day.day_number}: {stops}")

            narration_prompt = (
                f"Destination: {trip.destination}\n"
                f"Travel style: {(pref.travel_style if pref else None) or 'not specified'}\n\n"
                + "\n".join(skeleton_lines)
            )

            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            completion = client.models.generate_content(
                model=settings.AI_MODEL_LIGHT,
                contents=narration_prompt,
                config={
                    "system_instruction": (
                        "For each day listed below, write a short, punchy theme "
                        "(3-6 words) and a one-sentence summary. Return ONLY a "
                        "JSON object: {\"days\": [{\"dayNumber\": integer, "
                        '"theme": string, "summary": string}]}. No markdown, no '
                        "commentary."
                    ),
                    "response_mime_type": "application/json",
                    "max_output_tokens": 500,
                },
            )
            narration = DayNarrationBatchAI.model_validate(
                json.loads(completion.text or "")
            )
            for entry in narration.days:
                day_themes[entry.day_number] = (entry.theme, entry.summary)

            _log_step(
                db,
                run.id,
                AgentStepName.NARRATE_DAYS,
                AgentRunStatus.COMPLETED,
                output_json={
                    "days_narrated": len(day_themes),
                    "days_total": len(plan.days),
                },
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001 — narrate_days must never fail the run
            _log_step(
                db,
                run.id,
                AgentStepName.NARRATE_DAYS,
                AgentRunStatus.COMPLETED,
                output_json={
                    "warning": f"narrate_days failed: {e}",
                    "days_narrated": 0,
                    "days_total": len(plan.days),
                },
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )

        # --- Step 9: save_itinerary ----------------------------------------------
        t0 = time.perf_counter()
        # Regenerate from scratch: drop any existing days (items cascade).
        db.execute(delete(ItineraryDay).where(ItineraryDay.trip_id == trip_id))

        days_saved = 0
        items_saved = 0
        for day in plan.days:
            theme, day_summary = day_themes.get(
                day.day_number, _fallback_theme_summary(day)
            )
            day_date = (
                trip.start_date + timedelta(days=day.day_number - 1)
                if trip.start_date
                else None
            )
            itinerary_day = ItineraryDay(
                trip_id=trip_id,
                day_number=day.day_number,
                date=day_date,
                theme=theme,
                summary=day_summary,
                total_walking_minutes=day.total_walking_minutes,
                total_transit_minutes=day.total_transit_minutes,
                total_distance_meters=day.total_distance_meters,
                route_optimized=day.route_optimized,
            )
            itinerary_day.items.extend(day.items)
            db.add(itinerary_day)
            days_saved += 1
            items_saved += len(day.items)

        db.commit()
        _log_step(
            db,
            run.id,
            AgentStepName.SAVE_ITINERARY,
            AgentRunStatus.COMPLETED,
            output_json={"days_saved": days_saved, "items_saved": items_saved},
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

        # --- Done ----------------------------------------------------------
        run.status = AgentRunStatus.COMPLETED
        run.completed_at = _now()
        db.commit()
        db.refresh(run)
        return run

    except Exception as e:  # noqa: BLE001 — never leave a run stuck in "running"
        db.rollback()
        return _fail_run(db, run, f"Unexpected error: {e}")
