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

**Sprint 3 — Real Place / Restaurant Search + Price Verification**

The agent now resolves LLM-proposed location names into real Google Places records.
The pipeline adds a `resolve_places` step (with a bare-name query fallback for
venues that don't match when the destination is appended) and a `resolve_prices`
step between `parse_response` and `save_itinerary`. Every place lookup, and
the single batched price-verification call per run, is logged as a `ToolCall` row.

Sprint 3 is complete when:
- `places` and `tool_calls` tables exist in PostgreSQL
- `ItineraryItem.place_id` FK is populated for resolved items
- `PlacesService.resolve_item_place()` calls the Google Places Text Search API,
  retrying with a bare-name query if `"{location_name}, {destination}"` misses
- A `resolve_places` AgentStep is logged per generation run
- `PriceService.search_batch_prices()` grounds real prices for resolved items
  via one batched Gemini + Google Search call per run, populating
  `ItineraryItem.verified_cost` / `.price_source` alongside the LLM's
  `estimated_cost` (never overwriting it)
- A `resolve_prices` AgentStep is logged per generation run
- `GET /api/trips/{trip_id}/itinerary` returns nested place data per item
- `GET /api/agent-runs/{run_id}/tool-calls` returns ToolCall rows
- Frontend shows real address, rating, and Google Maps link for resolved items
- Pipeline degrades gracefully when `GOOGLE_PLACES_API_KEY` is missing

Do NOT add in Sprint 3:
- Google Routes API or route ordering
- Rest-stop insertion
- Ticketmaster / events
- Redis caching (cache_hit column is stored but always False for now)
- Background jobs
- Google Calendar sync
- Cloud deployment
- LangGraph (introduced in a later sprint)

---

## Architecture Principles

- **API routes are thin.** No business logic in route handlers. Queries + HTTP
  translation only.
- **Business logic lives in services.** `app/services/` is the only place that
  calls the LLM, external APIs, or runs multi-step logic.
- **The LLM is not the source of truth.** LLM proposes → tools verify → backend
  validates → LLM explains.
- **External APIs are wrapped in service classes.** Never call Google Places or
  Gemini directly from a route handler or model.
- **Tool calls are logged.** Every external API call produces a `ToolCall` row
  with input, output, latency, and cache_hit.
- **Agent runs always end completed or failed.** Never leave a run stuck in
  `running`. Every failure path calls `_fail_run()`.
- **Graceful degradation per item.** A single failed place lookup must not abort
  the entire generation run. Log it, set `place_id=None`, continue.
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
    │   ├── trips.py            # Trip CRUD + itinerary endpoints
    │   └── agent_runs.py       # AgentRun read + steps + tool-calls endpoints
    ├── core/
    │   └── config.py           # Pydantic Settings (DATABASE_URL, GEMINI_API_KEY,
    │                           #   AI_MODEL, GOOGLE_PLACES_API_KEY)
    ├── models/
    │   ├── __init__.py         # Re-exports all models so Base.metadata is complete
    │   ├── user.py             # User, DEFAULT_USER_ID
    │   ├── trip.py             # Trip, TripPreference, TripStatus
    │   ├── agent.py            # AgentRun, AgentStep, AgentRunStatus, AgentStepName
    │   ├── itinerary.py        # ItineraryDay, ItineraryItem, enums
    │   ├── place.py            # Place (Sprint 3)
    │   └── tool_call.py        # ToolCall (Sprint 3)
    ├── schemas/
    │   ├── trip.py             # TripBase/Create/Update/Read, TripPreferenceRead
    │   ├── agent.py            # AgentRunRead, AgentStepRead
    │   ├── itinerary.py        # ItineraryDayRead, ItineraryItemRead,
    │   │                       #   ItineraryAIResponse (AI output validation)
    │   ├── place.py            # PlaceRead (Sprint 3)
    │   └── tool_call.py        # ToolCallRead (Sprint 3)
    └── services/
        ├── ai_itinerary_service.py  # 7-step agent pipeline (+resolve_places, +resolve_prices)
        ├── places_service.py        # Google Places API wrapper (Sprint 3)
        └── price_service.py         # Gemini + Google Search price verification (Sprint 3)
```

---

## Coding Conventions

### SQLAlchemy models
- Use SQLAlchemy 2.0 `Mapped[...]` / `mapped_column(...)` style throughout.
  Never use legacy `Column()`.
- Enums are Python `class Foo(str, Enum)` stored as `String(N)` columns.
  Never use native PostgreSQL enum types.
- Timestamps: `DateTime(timezone=True)` with `server_default=func.now()`.
  Add `onupdate=func.now()` only on `updated_at` columns that have it already.
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

### Agent pipeline
- The pipeline is in `app/services/ai_itinerary_service.py`.
- Steps: `load_trip_preferences` → `build_prompt` → `call_llm` →
  `parse_response` → `resolve_places` → `resolve_prices` → `save_itinerary`.
- Every step is logged via `_log_step()` immediately (committed to DB).
- Any failure after the AgentRun is created calls `_fail_run()` and returns.
  Never raise from inside the pipeline — return the failed run.
- The only exception that propagates out is `TripNotFoundError` (raised before
  the run is created).

### Places service
- All Google Places API logic lives in `app/services/places_service.py`.
  Never call the Places API from a route handler or directly from the agent
  service.
- `resolve_item_place()` tries `"{location_name}, {destination}"` first, then
  falls back to `location_name` alone — logs one `ToolCall` per attempt.
- Every Places API call produces a `ToolCall` row committed immediately.
- Failures per item return `None` — they never raise or abort the run.
- `find_or_create_place()` checks for an existing `google_place_id` before
  inserting, so the same place is never duplicated across runs.

### Price service
- All price-verification logic lives in `app/services/price_service.py`.
  Never call Gemini for pricing from a route handler or directly from the
  agent service.
- `search_batch_prices()` grounds prices for every resolved item in a
  **single** Gemini + Google Search call per generation run (not one call
  per item) — logs exactly one `ToolCall` row (`tool_name="gemini_price_search_batch"`)
  regardless of how many items were priced.
- The Gemini `google_search` grounding tool cannot be combined with
  `response_mime_type: application/json` — this call uses plain-text output
  in a strict `"<index>: PRICE_USD: <number|unknown>"` line format, parsed
  with a regex, not JSON parsing.
- Failures (API error, or zero parseable price lines) return `{}` — they
  never raise or abort the run.
- Verified prices are additive: they populate `ItineraryItem.verified_cost`
  / `.price_source`, never overwrite the LLM's `estimated_cost`.

### API routes
- Routers live in `app/api/`. One file per resource group.
- Routes return Pydantic `*Read` schemas, not ORM objects directly.
- Use `selectinload` or `joinedload` for any relationship that needs to be
  serialized in the response — never rely on lazy loading after session close.
- 404 for missing resources, 502 for upstream API failures (LLM / Places).

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `GEMINI_API_KEY` | Yes | Gemini API key (Google AI Studio) |
| `AI_MODEL` | Yes | Gemini model string e.g. `gemini-1.5-flash` |
| `GOOGLE_PLACES_API_KEY` | Sprint 3 | Google Cloud API key with Places API enabled |

---

## Database

No Alembic yet. Schema is managed via `Base.metadata.create_all` in `init_db.py`.
To apply schema changes: stop the app, drop and recreate the DB, rerun `init_db.py`.

Tables (Sprint 3):
- `users` — seeded default user
- `trips` — core trip record
- `trip_preferences` — one-to-one planning constraints
- `agent_runs` — one per generation attempt
- `agent_steps` — one per pipeline stage per run
- `itinerary_days` — generated day records per trip
- `itinerary_items` — individual items per day, with optional `place_id` FK
- `places` — real place records from Google Places API
- `tool_calls` — one per external API call per run

---

## After Every Coding Task

Always explain:
1. Files changed / created
2. How to run or test it
3. How to verify it worked
4. What to do next
