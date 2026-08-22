# CLAUDE.md — GuideGenie

This file is read at the start of every Claude Code session.
Always read this file first before touching any code.

---

## Project Overview

GuideGenie is a full-stack AI travel planning agent that converts natural-language
trip preferences into personalized, route-optimized itineraries using real places,
restaurants, hotels, events, and comfort-aware constraints.

This is a portfolio project targeting Big Tech SWE / AI engineering internships.
It must demonstrate: full-stack development, AI agent workflow, structured LLM
output, tool use, backend API design, PostgreSQL data modeling, external API
integration, Redis caching, background jobs, observability, and cloud deployment.

**It is not a ChatGPT wrapper.** The LLM proposes. External tools verify. The
backend clusters, schedules, and optimizes. The LLM explains the final result.

---

## Current Sprint

**Sprint 5 — Rest-Stop Insertion**

When a walking segment between two consecutive stops exceeds the user's
`max_walking_minutes_between_stops` preference, the backend now searches for a
real physical rest stop (cafe, convenience store, park, etc.) near the segment
midpoint via Google Places Nearby Search. Candidates are scored by seating
confidence (type-based prior + rating bonus) and filtered by detour penalty.
If a suitable stop is found, it is inserted into the day's schedule as a REST
item with a real place record and an explanation in the description.

Sprint 5 is complete when:
- `app/services/rest_stop_service.py` exists with `nearby_search()`,
  `seating_confidence_score()`, and `find_rest_stop()`
- `_insert_rest_stops()` runs in `DayPlannerService._plan_days_inner()` between
  `_sequence_day_activities()` and `_build_day_items()`
- Inserted rest stops appear as REST-type `ItineraryItem` rows with a real
  `place_id` and an explanation in `description`
- `google_places_nearby_search` ToolCall rows are logged per search
- `optimize_route` AgentStep output_json includes `rest_stops_inserted: N`
- Frontend shows real rest stops with place name, seating confidence, rating,
  and a Google Maps link; plain rest blocks (no place) keep existing display
- README documents Sprint 5 behavior and demo checklist

Do NOT add in Sprint 5:
- Ticketmaster / events API (Sprint 6)
- LangGraph or clarifying questions (Sprint 6)
- User editing or replanning (Sprint 7)
- Amadeus hotel pricing (Sprint 8)
- Redis caching
- Background jobs
- Google Calendar sync
- Cloud deployment
- New model columns (rest stops use existing ItineraryItem columns)
- New pipeline steps (rest-stop insertion runs inside optimize_route)

---

## Architecture Principles

- **API routes are thin.** No business logic in route handlers. Queries + HTTP
  translation only.
- **Business logic lives in services.** `app/services/` is the only place that
  calls the LLM, external APIs, or runs multi-step logic.
- **The LLM proposes places; the backend owns scheduling.** The LLM outputs a
  flat pool of named places. Day assignment, sequencing, meal assignment,
  rest-stop insertion, and time-block construction are all deterministic backend
  logic in `DayPlannerService`.
- **The LLM is not the source of truth.** LLM proposes → tools verify → backend
  clusters, schedules, and inserts rest stops → LLM narrates.
- **External APIs are wrapped in service classes.** Never call Google Places,
  Google Distance Matrix, or Gemini directly from a route handler or model.
- **Tool calls are logged.** Every external API call produces a `ToolCall` row
  with input, output, latency, and cache_hit.
- **Agent runs always end completed or failed.** Never leave a run stuck in
  `running`. Every failure path calls `_fail_run()`.
- **Graceful degradation per step.** A missing API key or failed step must not
  abort the run — log it as completed with a warning and continue.
- **DayPlannerService never raises.** Any internal failure falls back to
  `_fallback_plan()`. `_insert_rest_stops()` also never raises — on any
  exception it returns the original lists unmodified.
- **Rest stops use existing model columns.** Inserted rest stops are
  `ItineraryItem` rows with `type=REST`, `place_id` pointing to a real Place,
  and the insertion explanation in `description`. No new columns needed.
- **Seating confidence is an estimate, not a guarantee.** Scored from a
  type-based prior (cafe: 0.85, convenience_store: 0.65, park: 0.40, etc.)
  plus a rating bonus. Displayed as a percentage, not a boolean.
- **API calls are bounded.** One Nearby Search call per long walking segment,
  haversine pre-filtering of candidates, no Distance Matrix call per candidate.
- **ItineraryItem rows are built in optimize_route, not save_itinerary.**
  `DayPlannerService` constructs the ORM objects so all fields (including
  rest-stop place_id and description) are set before DB insertion.
- **Narration is cheap and non-blocking.** One batched LLM call using
  `AI_MODEL_LIGHT` writes all day themes/summaries after scheduling.
- **Secrets come from environment variables.** Never hardcode API keys.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, App Router |
| Backend | FastAPI, Python, Pydantic, SQLAlchemy 2.0 |
| Database | PostgreSQL (Base.metadata.create_all via init_db.py — no Alembic yet) |
| AI / LLM | Gemini API via google-genai SDK; JSON mode for pool generation; light model for narration |
| Agent framework | Hand-rolled pipeline now; LangGraph introduced in Sprint 6 |
| Places API | Google Places API (New) v1 — Text Search + Nearby Search (`searchText`/`searchNearby`, field-masked, includes `regularOpeningHours`) |
| Route API | Google Distance Matrix API |
| Static Maps | Google Maps Static API (frontend, img tag only) |
| Caching / Jobs | Redis + background workers — later sprint |
| Calendar | Google OAuth + Calendar API — later sprint |
| DevOps | Docker Compose (local), AWS ECS/RDS/ElastiCache (later sprint) |

---

## Folder Structure

```
backend/
├── requirements.txt
├── .venv/
└── app/
    ├── database.py             # SQLAlchemy engine, SessionLocal, Base, get_session
    ├── init_db.py              # Base.metadata.create_all + seed default user
    ├── main.py                 # FastAPI app, middleware, router registration
    ├── api/
    │   ├── trips.py            # Trip CRUD + itinerary + route-summary endpoints
    │   └── agent_runs.py       # AgentRun read + steps + tool-calls endpoints
    ├── core/
    │   └── config.py           # Pydantic Settings (DATABASE_URL, GEMINI_API_KEY,
    │                           #   AI_MODEL, AI_MODEL_LIGHT, GOOGLE_PLACES_API_KEY,
    │                           #   GOOGLE_ROUTES_API_KEY)
    ├── models/
    │   ├── __init__.py         # Re-exports all models so Base.metadata is complete
    │   ├── user.py             # User, DEFAULT_USER_ID
    │   ├── trip.py             # Trip, TripPreference, TripStatus
    │   ├── agent.py            # AgentRun, AgentStep, AgentRunStatus, AgentStepName
    │   │                       #   (includes OPTIMIZE_ROUTE, NARRATE_DAYS)
    │   ├── itinerary.py        # ItineraryDay, ItineraryItem, enums
    │   ├── place.py            # Place
    │   └── tool_call.py        # ToolCall
    ├── schemas/
    │   ├── trip.py             # TripBase/Create/Update/Read, TripPreferenceRead
    │   ├── agent.py            # AgentRunRead, AgentStepRead
    │   ├── itinerary.py        # ItineraryDayRead, ItineraryItemRead;
    │   │                       #   HotelAI, ActivityAI, RestaurantAI,
    │   │                       #   TripPlanAIResponse; DayNarrationAI,
    │   │                       #   DayNarrationBatchAI; RouteDaySummary
    │   ├── place.py            # PlaceRead
    │   └── tool_call.py        # ToolCallRead
    └── services/
        ├── ai_itinerary_service.py  # 9-step agent pipeline
        ├── day_planner_service.py   # Clustering, sequencing, rest-stop insertion,
        │                            #   meal assignment, time-block scheduling,
        │                            #   hours-aware scheduling/warnings
        ├── opening_hours.py         # Pure is_open_at/next_open_minute helpers over
        │                            #   Places API (New) regularOpeningHours
        ├── places_service.py        # Google Places API (New) Text Search wrapper
        ├── price_service.py         # Price resolution service
        ├── rest_stop_service.py     # Google Places API (New) Nearby Search + seating
        │                            #   confidence scoring (Sprint 5), hours-aware pick
        └── route_service.py         # Google Distance Matrix API +
                                     #   nearest_neighbor_order (pure function)
```

---

## Coding Conventions

### SQLAlchemy models
- Use SQLAlchemy 2.0 `Mapped[...]` / `mapped_column(...)` style throughout.
  Never use legacy `Column()`.
- Enums are Python `class Foo(str, Enum)` stored as `String(N)` columns.
  Never use native PostgreSQL enum types.
- Timestamps: `DateTime(timezone=True)` with `server_default=func.now()`.
  Add `onupdate=func.now()` only on `updated_at` columns.
- Nullable columns: `Mapped[str | None]` with `default=None`.
- List/dict fields: `JSON` column type, `default=list` or `default=dict`.
- Foreign keys: always `ondelete="CASCADE"` (or `"SET NULL"` where appropriate)
  and `index=True`.
- Every new model must be imported in `app/models/__init__.py` and added to
  `__all__` so `Base.metadata` is fully populated before table creation.

### Pydantic schemas
- Naming: `*Base` (shared fields), `*Create` (request body), `*Update`
  (partial update, all fields optional), `*Read` (response, includes server
  fields).
- All `*Read` schemas: `model_config = ConfigDict(from_attributes=True)`.
- AI pool schemas use camelCase aliases via `Field(alias=...)` and
  `ConfigDict(populate_by_name=True)`.
- Non-ORM response schemas (e.g. `RouteDaySummary`) use plain
  `model_config = ConfigDict()` — no `from_attributes`.

### Agent pipeline
- The pipeline is in `app/services/ai_itinerary_service.py`.
- Steps (9 total): `load_trip_preferences` → `build_prompt` → `call_llm` →
  `parse_response` → `resolve_places` → `resolve_prices` → `optimize_route`
  → `narrate_days` → `save_itinerary`.
- Rest-stop insertion runs inside `optimize_route` via `DayPlannerService` —
  it is not a separate pipeline step.
- `ItineraryItem` ORM objects are built inside `DayPlannerService` so all
  fields are set before DB insertion. `save_itinerary` only calls `db.add()`
  and `db.commit()` on pre-built objects.
- Every step is logged via `_log_step()` immediately (committed to DB).
- Any failure after the AgentRun is created calls `_fail_run()` and returns.
  Never raise from inside the pipeline — return the failed run.
- The only exception that propagates out is `TripNotFoundError`.

### DayPlannerService
- Lives in `app/services/day_planner_service.py`. No FastAPI dependencies.
- `plan_days()` is the single public entrypoint; it never raises.
- Internal steps: k-means clustering → day ordering → within-day sequencing
  → **rest-stop insertion** → meal assignment → time-block construction.
- `_insert_rest_stops()` builds new lists rather than mutating in place to
  avoid index bugs during insertion.
- Falls back to `_fallback_plan()` on any internal exception.
- Hours-aware scheduling: when `start_date` is passed (from `Trip.start_date`),
  each day's Google weekday is computed and threaded into restaurant
  selection, dinner-time shifting, and activity deferral via
  `app/services/opening_hours.py`. With `start_date=None`, all hours logic is
  a no-op — byte-identical to pre-hours-aware behavior.
- Closed-venue handling is "avoid + warn, never drop": `_pick_restaurant()`
  prefers open/unknown-hours candidates; dinner shifts into the venue's open
  window when possible; otherwise the original pick/time is kept with a
  warning appended to `description` (no new columns, same pattern as
  rest-stop explanations) and `PlanResult.hours_warnings_added` incremented.
  Unknown hours are always treated as open — never a false block.

### RestStopService
- Lives in `app/services/rest_stop_service.py`. No FastAPI dependencies.
- `find_rest_stop()` is the main entrypoint; it never raises.
- Uses Google Places API (New) Nearby Search (not Text Search). Filters
  results client-side by type against `SEATING_CONFIDENCE` keys.
- One Nearby Search call per long segment. Haversine pre-filtering of
  candidates. No Distance Matrix call per candidate — detour is estimated
  with haversine at 80 m/min walking pace.
- Every Nearby Search call logged as `ToolCall` with
  `tool_name="google_places_nearby_search"`.
- Reuses `PlacesService.find_or_create_place()` for Place upsert — never
  duplicates that logic.
- Accepts optional `weekday`/`check_minute` to prefer a candidate that isn't
  confirmed closed at that point in the day; falls back to the best-scoring
  candidate if every option is closed (never worse than the weekday-agnostic
  behavior).

### opening_hours
- Lives in `app/services/opening_hours.py`. Pure module — no FastAPI/
  SQLAlchemy imports, never raises (malformed or missing hours data returns
  `None`, meaning "unknown").
- `is_open_at(hours, weekday, minute_of_day) -> bool | None` and
  `next_open_minute(hours, weekday, from_minute, until_minute) -> int | None`
  operate on the Places API (New) `regularOpeningHours` shape (`periods` of
  `{open, close}` day/hour/minute points; a close-less period means 24/7;
  `weekday` uses the Google convention, 0=Sunday).
- `None` (unknown) is always treated as open by callers — never a source of
  false blocking or warnings.

### Route service
- `app/services/route_service.py` provides `get_distance_matrix()`,
  `nearest_neighbor_order()` (pure function), `_get_distance_matrix_full()`,
  and `_log_tool_call()`.
- `optimize_day()` was removed in the Sprint 4 redesign.

### API routes
- Routers live in `app/api/`. One file per resource group.
- Routes return Pydantic `*Read` schemas, not ORM objects directly.
- Use `selectinload` or `joinedload` for any relationship serialized in the
  response — never rely on lazy loading after session close.
- 404 for missing resources, 502 for upstream API failures.

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Gemini API key (Google AI Studio) |
| `AI_MODEL` | Yes | Main Gemini model e.g. `gemini-2.5-flash` |
| `AI_MODEL_LIGHT` | Yes | Narration model e.g. `gemini-2.5-flash-lite` |
| `GOOGLE_PLACES_API_KEY` | Sprint 3 | Google Cloud key, **Places API (New)** enabled (a separate Cloud Console toggle from the legacy "Places API") — used for Text Search in Sprint 3 and Nearby Search in Sprint 5, both migrated to the v1 endpoints for `regularOpeningHours` support |
| `GOOGLE_ROUTES_API_KEY` | Sprint 4 | Google Cloud key, Distance Matrix API enabled |

### Frontend (`frontend/.env.local`)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Sprint 4 | Google Cloud key, Maps Static API enabled |

All Google API keys can share the same Google Cloud key value as long as
Places API (New) (Text Search + Nearby Search), Distance Matrix API, and Maps
Static API are all enabled on the same project.

---

## Database

No Alembic yet. Schema is managed via `Base.metadata.create_all` in `init_db.py`.
To apply schema changes: stop the app, drop and recreate the DB, rerun `init_db.py`.

Tables (Sprint 5 — no new tables or columns since Sprint 4):
- `users`
- `trips`
- `trip_preferences`
- `agent_runs`
- `agent_steps`
- `itinerary_days` — `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, `route_optimized`
- `itinerary_items` — `travel_time_to_next_minutes`, `distance_to_next_meters`,
  `travel_mode_to_next`, `verified_cost`, `price_source`, `place_id`
- `places`
- `tool_calls`

---

## Degradation Matrix

| Missing / failing | Behavior |
|---|---|
| `GEMINI_API_KEY` | Run fails at `call_llm` |
| `GOOGLE_PLACES_API_KEY` | No places resolved AND no rest stops found; `_fallback_plan()` used for scheduling; run completes |
| `GOOGLE_ROUTES_API_KEY` | Clustering runs (haversine only); sequencing degrades to arrival order; travel fields null; run completes |
| `find_rest_stop()` returns None | Long segment left unchanged; no rest stop inserted; run continues |
| `narrate_days` failure | Deterministic fallback themes; run still completes |
| Any exception in `optimize_route` | `_fallback_plan()` used; step logged COMPLETED with warning; run continues |

---

## After Every Coding Task

Always explain:
1. Files changed / created
2. How to run or test it
3. How to verify it worked
4. What to do next