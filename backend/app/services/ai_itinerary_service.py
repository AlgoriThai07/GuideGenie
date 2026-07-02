"""AI itinerary generation service (Sprint 2).

Turns an existing trip + its preferences into a saved day-by-day itinerary via
an LLM. Business logic lives here (not in route handlers), per the project's
clean-architecture rule.

The single entrypoint is :func:`generate_itinerary`. It records an
``AgentRun`` and one ``AgentStep`` per pipeline stage
(``load_trip_preferences`` → ``build_prompt`` → ``call_llm`` →
``parse_response`` → ``save_itinerary``), so a run is observable while in
progress and its outcome is auditable afterwards.

Failure handling: a run always ends ``completed`` or ``failed`` — never stuck
in ``running``. Only a missing trip (before any run is created) raises
(:class:`TripNotFoundError`); every failure after the run exists is recorded on
the run (``status=failed`` + ``error_message``) and the failed run is returned
so the caller can inspect it.

Uses the Gemini API (``google-genai`` SDK) with JSON response mode.
"""

import json
import time
from datetime import datetime, timezone
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.agent import AgentRun, AgentRunStatus, AgentStep, AgentStepName
from app.models.itinerary import ItineraryDay, ItineraryItem
from app.models.trip import Trip, TripPreference
from app.schemas.itinerary import ItineraryAIResponse

# Prompt/response text stored in JSON step columns is truncated to keep rows
# small; the full itinerary is persisted separately as day/item rows.
_MAX_STORED_TEXT = 8000


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


def _build_system_prompt() -> str:
    """Static system prompt encoding the output contract and planning rules."""
    return (
        "You are an expert travel-planning assistant. You produce a structured "
        "day-by-day itinerary for a trip.\n\n"
        "OUTPUT FORMAT:\n"
        "- Return ONLY a single valid JSON object. No markdown, no code fences, "
        "no commentary before or after.\n"
        "- The JSON MUST match this exact shape (camelCase keys):\n"
        "{\n"
        '  "tripTitle": string,\n'
        '  "overview": string,\n'
        '  "days": [{\n'
        '    "dayNumber": integer, "date": "YYYY-MM-DD", "theme": string, '
        '"summary": string,\n'
        '    "items": [{\n'
        '      "startTime": "HH:MM", "endTime": "HH:MM", "title": string,\n'
        '      "type": one of ["activity","meal","hotel","transport","rest",'
        '"event","free_time"],\n'
        '      "locationName": string, "description": string,\n'
        '      "estimatedCost": number, '
        '"walkingIntensity": one of ["low","medium","high"],\n'
        '      "priority": one of ["required","recommended","optional"]\n'
        "    }]\n"
        "  }]\n"
        "}\n\n"
        "PLANNING RULES:\n"
        "- Do NOT invent exact ratings, review counts, street addresses, or "
        "opening hours. Use reasonable, generic placeholder location names.\n"
        "- Every item MUST have startTime and endTime. Every day MUST have a "
        "theme and a summary.\n"
        "- Include meals (breakfast/lunch/dinner as appropriate) and at least "
        "one rest or free_time block per day.\n"
        "- No more than 4 major activities per day; keep pacing realistic.\n"
        "- Align walkingIntensity with the traveler's walking tolerance: lower "
        "tolerance means fewer high-intensity items and shorter distances.\n"
        "- Respect interests, food preferences, hotel preferences, must-visit "
        "places, and the avoid list.\n"
        "- Every day's date MUST fall within the trip's start and end dates "
        "(inclusive), one day per date in order."
    )


def _build_user_prompt(trip: Trip, pref: TripPreference | None) -> str:
    """Per-trip user prompt built from the trip and its preferences."""
    p = _preferences_summary(pref)
    start = trip.start_date.isoformat() if trip.start_date else "unspecified"
    end = trip.end_date.isoformat() if trip.end_date else "unspecified"
    budget = f"{trip.budget}" if trip.budget is not None else "no fixed budget"

    lines = [
        "Plan an itinerary for the following trip.",
        "",
        f"Title: {trip.title}",
        f"Destination: {trip.destination}",
        f"Dates: {start} to {end} (inclusive)",
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
        "Return the itinerary as the JSON object described in the system "
        "instructions.",
    ]
    return "\n".join(lines)


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
        system_prompt = _build_system_prompt()
        user_prompt = _build_user_prompt(trip, pref)
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

        # --- Step 4: parse_response ----------------------------------------
        t0 = time.perf_counter()
        try:
            parsed = ItineraryAIResponse.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValidationError) as e:
            message = f"Invalid itinerary JSON from LLM: {e}"
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

        # --- Step 5: save_itinerary ----------------------------------------
        t0 = time.perf_counter()
        # Regenerate from scratch: drop any existing days (items cascade).
        db.execute(delete(ItineraryDay).where(ItineraryDay.trip_id == trip_id))

        days_saved = 0
        items_saved = 0
        for day_ai in parsed.days:
            day = ItineraryDay(
                trip_id=trip_id,
                day_number=day_ai.day_number,
                date=day_ai.date,
                theme=day_ai.theme,
                summary=day_ai.summary,
            )
            for order_index, item_ai in enumerate(day_ai.items):
                day.items.append(
                    ItineraryItem(
                        order_index=order_index,
                        start_time=item_ai.start_time,
                        end_time=item_ai.end_time,
                        title=item_ai.title,
                        type=item_ai.type,
                        location_name=item_ai.location_name,
                        description=item_ai.description,
                        estimated_cost=item_ai.estimated_cost,
                        walking_intensity=item_ai.walking_intensity,
                        priority=item_ai.priority,
                    )
                )
                items_saved += 1
            db.add(day)
            days_saved += 1

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
