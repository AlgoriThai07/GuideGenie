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

**Sprint 4 — Route Optimization MVP**

The agent now orders each day's stops logically using real travel times from
the Google Distance Matrix API. A nearest-neighbor heuristic reorders flexible
items (activities and events) within each day while keeping anchors (meals,
hotel, rest, transport) in place. Travel time and distance between consecutive
stops are stored per item. A static map image shows place markers per day.

Sprint 4 is complete when:
- `itinerary_items` has `travel_time_to_next_minutes`, `distance_to_next_meters`,
  `travel_mode_to_next` columns
- `itinerary_days` has `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, `route_optimized` columns
- `RouteService.get_distance_matrix()` calls the Google Distance Matrix API
- `RouteService.nearest_neighbor_order()` is a pure function with no API calls
- `RouteService.optimize_day()` reorders flexible items and populates travel fields
- An `optimize_route` AgentStep is logged per generation run
- `GET /api/trips/{trip_id}/itinerary` returns travel time fields per item
- `GET /api/trips/{trip_id}/route-summary` returns per-day route totals
- Frontend shows travel time connectors between items
- Frontend shows a static map with place markers per day
- Pipeline degrades gracefully when `GOOGLE_ROUTES_API_KEY` is missing

Do NOT add in Sprint 4:
- Rest-stop insertion (Sprint 5)
- Ticketmaster / events (Sprint 6)
- LangGraph or clarifying questions (Sprint 6)
- User editing or replanning (Sprint 7)
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
- **Route optimizer constructs items, not save_itinerary.** `ItineraryItem` ORM
  objects are built during the `optimize_route` step so travel fields can be
  mutated before DB insertion. `save_itinerary` adds and commits pre-built items.
- **Nearest-neighbor only moves flexible items.** Anchors (hotel, meal, rest,
  free_time, transport) keep their relative positions. Only activity and event
  type items with a resolved place are candidates for reordering.
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
    │   │                       #   ItineraryAIResponse, RouteDaySummary
    │   ├── place.py            # PlaceRead
    │   └── tool_call.py        # ToolCallRead
    └── services/
        ├── ai_itinerary_service.py  # 8-step agent pipeline
        ├── places_service.py        # Google Places API wrapper
        ├── price_service.py         # Price resolution service
        └── route_service.py         # Google Distance Matrix + nearest-neighbor
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
- AI output schemas (e.g. `ItineraryAIResponse`) use camelCase aliases via
  `Field(alias=...)` and `ConfigDict(populate_by_name=True)` to match the
  JSON the LLM returns.
- Non-ORM response schemas (e.g. `RouteDaySummary`) use plain
  `model_config = ConfigDict()` — no `from_attributes`.

### Agent pipeline
- The pipeline is in `app/services/ai_itinerary_service.py`.
- Steps: `load_trip_preferences` → `build_prompt` → `call_llm` →
  `parse_response` → `resolve_places` → `resolve_prices` →
  `optimize_route` → `save_itinerary`.
- `ItineraryItem` ORM objects are constructed in the `optimize_route` step
  so travel fields can be set before DB insertion. `save_itinerary` only
  adds and commits pre-built objects.
- Every step is logged via `_log_step()` immediately (committed to DB).
- Any failure after the AgentRun is created calls `_fail_run()` and returns.
  Never raise from inside the pipeline — return the failed run.
- The only exception that propagates out is `TripNotFoundError`.

### Route service
- All Distance Matrix API logic lives in `app/services/route_service.py`.
- `nearest_neighbor_order()` is a pure function — no DB, no API calls.
- `optimize_day()` only reorders items of type activity/event that have a
  resolved place. Anchors (hotel, meal, rest, free_time, transport) and
  items without a place keep their relative positions.
- Every Distance Matrix API call is logged as a ToolCall row.
- `optimize_day()` never raises — on any failure it returns the original
  item list unmodified.

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
| `AI_MODEL` | Yes | Gemini model string e.g. `gemini-1.5-flash` |
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