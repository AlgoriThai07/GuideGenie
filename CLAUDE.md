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
backend ranks, optimizes, and validates. The LLM explains the final result.

---

## Current Sprint

**Sprint 4 — Route Optimization MVP (place-pool + backend scheduler design)**

The LLM proposes a flat *pool* of real places (one hotel, many activities/
events, many restaurant options) with no day assignment or timing. The
backend (`DayPlannerService`) clusters activities into geographically tight
days (capacity-balanced k-means over projected lat/lng), orders the days by
nearest-neighbor from the hotel, sequences each day's stops using real
travel times from the Google Distance Matrix API, assigns lunch/dinner
restaurants, and lays out a fixed daily time-block template (breakfast,
activities, lunch, rest, dinner, check-in/out). A second, cheap LLM call
(`AI_MODEL_LIGHT`, one batched request) then writes day themes/summaries.
Travel time and distance between consecutive scheduled stops are stored per
item. A static map image shows place markers per day.

This replaces the original Sprint 4 plan of having the LLM produce a full
day-by-day itinerary that the backend merely reordered within each day — see
`docs/REDESIGN-place-pool-scheduler.md` for the rationale and full design.

Sprint 4 is complete when:
- `itinerary_items` has `travel_time_to_next_minutes`, `distance_to_next_meters`,
  `travel_mode_to_next` columns
- `itinerary_days` has `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, `route_optimized` columns
- `RouteService.get_distance_matrix()` / `_get_distance_matrix_full()` call
  the Google Distance Matrix API
- `RouteService.nearest_neighbor_order()` is a pure function with no API calls
- `DayPlannerService.plan_days()` clusters the pool into days, sequences each
  day, and populates travel fields on the `ItineraryItem` objects it builds
- An `optimize_route` AgentStep is logged per generation run, followed by a
  `narrate_days` AgentStep
- `GET /api/trips/{trip_id}/itinerary` returns travel time fields per item
- `GET /api/trips/{trip_id}/route-summary` returns per-day route totals
  (endpoint not yet implemented — tracked as a follow-up)
- Frontend shows travel time connectors between items
- Frontend shows a static map with place markers per day
- Pipeline degrades gracefully when `GOOGLE_ROUTES_API_KEY` is missing
  (clustering still runs on haversine distance; travel fields stay null)

Do NOT add in Sprint 4:
- Rest-stop *tuning* beyond the fixed template block (Sprint 5)
- Ticketmaster / events sourcing (Sprint 6) — the `event` item type already
  exists for LLM-proposed pool entries, just no external events API yet
- LangGraph or clarifying questions (Sprint 6)
- User editing or replanning (Sprint 7) — though the new pool + scheduler
  split makes this natural later: mutate the pool, re-run the scheduler,
  no LLM call needed
- Redis caching (cache_hit column exists but is always False)
- Background jobs
- Google Calendar sync
- Cloud deployment
- Interactive maps or route polylines (Static API image only)

---

## Architecture Principles

- **API routes are thin.** No business logic in route handlers. Queries + HTTP
  translation only.
- **Business logic lives in services.** `app/services/` is the only place that
  calls the LLM, external APIs, or runs multi-step logic.
- **The LLM is not the source of truth.** LLM proposes → tools verify → backend
  optimizes → backend validates → LLM explains.
- **External APIs are wrapped in service classes.** Never call Google Places,
  Google Distance Matrix, or Gemini directly from a route handler or model.
- **Tool calls are logged.** Every external API call produces a `ToolCall` row
  with input, output, latency, and cache_hit.
- **Agent runs always end completed or failed.** Never leave a run stuck in
  `running`. Every failure path calls `_fail_run()`.
- **Graceful degradation per step.** A missing API key or failed step must not
  abort the run — log it as completed with a warning and continue.
- **The backend builds days, not the LLM.** The LLM proposes a flat place
  pool (hotel + activities/events + restaurant options); `DayPlannerService`
  clusters, sequences, and schedules it into days. The LLM never assigns
  days or times.
- **Route optimizer constructs items, not save_itinerary.** `ItineraryItem` ORM
  objects are built during the `optimize_route` step (inside
  `DayPlannerService`) so travel fields can be mutated before DB insertion.
  `save_itinerary` adds and commits pre-built items.
- **Narration is a separate, cheap pass.** Day themes/summaries are written
  by a second LLM call (`narrate_days`, using `AI_MODEL_LIGHT`) after the
  schedule exists, batched into one request for the whole trip. It never
  blocks or fails the run — a missing/failed narration falls back to a
  deterministic theme derived from the day's scheduled activities.
- **Secrets come from environment variables.** Never hardcode API keys.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, TypeScript, Tailwind CSS, App Router |
| Backend | FastAPI, Python, Pydantic, SQLAlchemy 2.0 |
| Database | PostgreSQL (Base.metadata.create_all via init_db.py — no Alembic yet) |
| AI / LLM | Gemini API via google-genai SDK, JSON response mode |
| Agent framework | Hand-rolled pipeline now; LangGraph introduced in a later sprint |
| Places API | Google Places Text Search API |
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
    │                           #   AI_MODEL, GOOGLE_PLACES_API_KEY,
    │                           #   GOOGLE_ROUTES_API_KEY)
    ├── models/
    │   ├── __init__.py         # Re-exports all models so Base.metadata is complete
    │   ├── user.py             # User, DEFAULT_USER_ID
    │   ├── trip.py             # Trip, TripPreference, TripStatus
    │   ├── agent.py            # AgentRun, AgentStep, AgentRunStatus, AgentStepName
    │   ├── itinerary.py        # ItineraryDay, ItineraryItem, enums
    │   ├── place.py            # Place
    │   └── tool_call.py        # ToolCall
    ├── schemas/
    │   ├── trip.py             # TripBase/Create/Update/Read, TripPreferenceRead
    │   ├── agent.py            # AgentRunRead, AgentStepRead
    │   ├── itinerary.py        # ItineraryDayRead, ItineraryItemRead,
    │   │                       #   TripPlanAIResponse (hotel/activities/
    │   │                       #   restaurants pool), DayNarrationBatchAI
    │   ├── place.py            # PlaceRead
    │   └── tool_call.py        # ToolCallRead
    └── services/
        ├── ai_itinerary_service.py  # 9-step agent pipeline
        ├── places_service.py        # Google Places API wrapper
        ├── price_service.py         # Price resolution service
        ├── route_service.py         # Google Distance Matrix + nearest-neighbor
        └── day_planner_service.py   # Clustering + scheduling (place pool -> days)
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
- AI output schemas (e.g. `TripPlanAIResponse`, `DayNarrationBatchAI`) use
  camelCase aliases via `Field(alias=...)` and
  `ConfigDict(populate_by_name=True)` to match the JSON the LLM returns.
- Non-ORM response schemas (e.g. `RouteDaySummary`) use plain
  `model_config = ConfigDict()` — no `from_attributes`.

### Agent pipeline
- The pipeline is in `app/services/ai_itinerary_service.py`.
- Steps: `load_trip_preferences` → `build_prompt` → `call_llm` →
  `parse_response` → `resolve_places` → `resolve_prices` →
  `optimize_route` → `narrate_days` → `save_itinerary`.
- The LLM call (`call_llm`/`parse_response`) returns a `TripPlanAIResponse`:
  one hotel, a flat list of activities/events, and a flat list of restaurant
  options — no days, no times.
- `resolve_places`/`resolve_prices` key their lookups by a composite
  `("hotel" | "activity" | "restaurant", index)` tuple instead of
  `(day_index, item_index)`, since there are no days yet at that point.
- `optimize_route` builds `PoolActivity`/`PoolRestaurant`/`HotelInfo` from the
  resolved places + verified prices and calls
  `DayPlannerService.plan_days()`, which does the clustering/scheduling and
  constructs the final `ItineraryItem` ORM objects (see Day planner section
  below). `save_itinerary` only adds and commits the pre-built
  `ItineraryDay`/`ItineraryItem` objects it gets back.
- `narrate_days` makes one batched call to `AI_MODEL_LIGHT` with a compact
  day skeleton (place names in schedule order) and gets back a theme +
  summary per day. On failure it falls back to a theme derived from the
  day's own scheduled activity titles — never blocks `save_itinerary`.
- Every step is logged via `_log_step()` immediately (committed to DB).
- Any failure after the AgentRun is created calls `_fail_run()` and returns.
  Never raise from inside the pipeline — return the failed run. The
  `optimize_route` and `narrate_days` steps are the exception to this at the
  step level: they catch their own errors internally and log a `COMPLETED`
  step with a `warning` in `output_json` rather than failing the run.
- The only exception that propagates out of `generate_itinerary` is
  `TripNotFoundError`.

### Route service
- Low-level Distance Matrix API access lives in
  `app/services/route_service.py`: `get_distance_matrix()` (public, minutes
  only), `_get_distance_matrix_full()` (private, minutes + meters, used by
  `day_planner_service`), and `nearest_neighbor_order()` (pure function — no
  DB, no API calls).
- Every Distance Matrix API call is logged as a ToolCall row via
  `_log_tool_call()`.
- `RouteService` never raises — a failed request degrades to a
  `None`-filled matrix.

### Day planner service
- Clustering, day ordering, meal assignment, and time-block scheduling live
  in `app/services/day_planner_service.py` (`DayPlannerService.plan_days()`).
- Clustering is a deterministic (no randomness), capacity-balanced k-means
  over an equirectangular projection of resolved activities' lat/lng —
  `_kmeans_labels()` + `_balance_clusters()`, both pure functions.
- Days are ordered by nearest-neighbor over cluster centroids starting from
  the hotel (`_order_clusters()`, pure, haversine distance).
- Within a day, activities are sequenced by nearest-neighbor over a real
  Distance Matrix (`_sequence_day_activities()`, calls `RouteService`).
- `_build_day_items()` lays out the fixed daily template (breakfast 08:00,
  optional check-in, activities from 09:30, lunch once the clock passes
  12:00, a rest block once it passes 15:30, dinner at/after 19:00, optional
  check-out) and only sets `travel_time_to_next_minutes` /
  `distance_to_next_meters` / `travel_mode_to_next` between consecutive
  *scheduled activity* items — meal/rest/hotel items keep those fields
  `None`. Overflow past 18:30 drops `optional`-priority activities first.
- `plan_days()` never raises: any exception falls back to
  `_fallback_plan()`, a naive round-robin day assignment with the same time
  template but no clustering and no Distance Matrix calls. The same
  fallback is used deliberately (not just on error) when
  `GOOGLE_ROUTES_API_KEY` is missing, so no wasted network calls are made.

### API routes
- Routers live in `app/api/`. One file per resource group.
- Routes return Pydantic `*Read` schemas, not ORM objects directly.
- Use `selectinload` or `joinedload` for any relationship serialized in the
  response — never rely on lazy loading after session close.
- 404 for missing resources, 502 for upstream API failures.

---

## Environment Variables

### Backend (.env)

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Gemini API key (Google AI Studio) |
| `AI_MODEL` | Yes | Gemini model string e.g. `gemini-1.5-flash` — used for the place-pool proposal call |
| `AI_MODEL_LIGHT` | Sprint 4 | Cheap/fast Gemini model, default `gemini-flash-lite-latest` (auto-updating alias — pinned lite versions like `gemini-2.5-flash-lite` can 404 for new API keys) — used only for the batched `narrate_days` call |
| `GOOGLE_PLACES_API_KEY` | Sprint 3 | Google Cloud key, Places API enabled |
| `GOOGLE_ROUTES_API_KEY` | Sprint 4 | Google Cloud key, Distance Matrix API + Maps Static API enabled |

### Frontend (.env.local)

| Variable | Required | Description |
|---|---|---|
| `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` | Sprint 4 | Same key value as `GOOGLE_ROUTES_API_KEY`, used for Maps Static API img src |

All three Google API keys can share the same Google Cloud API key value as long
as Places API, Distance Matrix API, and Maps Static API are all enabled on the
same project.

---

## Database

No Alembic yet. Schema is managed via `Base.metadata.create_all` in `init_db.py`.
To apply schema changes: stop the app, drop and recreate the DB, rerun `init_db.py`.

Tables (Sprint 4):
- `users`
- `trips`
- `trip_preferences`
- `agent_runs`
- `agent_steps`
- `itinerary_days` — includes `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, `route_optimized`
- `itinerary_items` — includes `travel_time_to_next_minutes`,
  `distance_to_next_meters`, `travel_mode_to_next`, `verified_cost`,
  `price_source`, `place_id`
- `places`
- `tool_calls`

---

## After Every Coding Task

Always explain:
1. Files changed / created
2. How to run or test it
3. How to verify it worked
4. What to do next