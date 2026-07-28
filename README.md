# GuideGenie

AI travel planning agent. Users enter travel preferences and get route-optimized
itineraries built from real places, restaurants, events, and rest stops — with
Google Calendar sync planned.

This is a software-engineering portfolio project, built incrementally in small,
well-scoped sprints. See `SPRINTS.md` for the roadmap and `CLAUDE.md` for project
context and rules.

> **Status:** Sprint 4 complete — route optimization + backend day planning.
> A user can create a trip, save it to PostgreSQL, view saved trips in a
> dashboard, open a trip detail page, edit or delete a trip, and click
> **Generate Itinerary** to get a day-by-day plan where the LLM proposes a
> flat pool of places, and the backend handles clustering, sequencing, meal
> assignment, and time-block construction. Output is complete with travel
> connectors, route summaries, and static maps. Next up: Sprint 5 (rest-stop
> insertion).

## Tech Stack

- **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python, Pydantic
- **AI:** Gemini API (`google-genai`) for itinerary generation
- **Database:** PostgreSQL with SQLAlchemy
- **Local infra:** Docker Compose (PostgreSQL only, for now)

## Architecture (Sprint 1)

```
frontend (Next.js :3000)  ──HTTP──>  backend (FastAPI :8000)  ──SQLAlchemy──>  PostgreSQL (:5433)
```

- Frontend trip CRUD calls live in `frontend/lib/api.ts`.
- Backend trip endpoints live under `/api/trips` (`backend/app/api/trips.py`).
- There is no authentication yet: every trip is owned by a single seeded
  "default" user.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + Docker Compose
- Python 3.11+
- Node.js 18.18+ (Next.js 15 requirement)

## Setup

The project has three pieces: PostgreSQL (Docker), the backend (FastAPI), and the
frontend (Next.js). Bring them up in that order.

### 1. PostgreSQL

From the repo root:

```bash
# Copy env defaults (used by Docker Compose and the backend).
cp .env.example .env

# Start PostgreSQL in the background.
docker compose up -d
```

This runs PostgreSQL 16 on host port **5433** (mapped to the container's 5432) to
avoid clashing with a native install on 5432. Data persists in the
`guidegenie_pgdata` volume.

### 2. Backend (FastAPI)

```bash
cd backend

# Create and activate a virtual environment.
python -m venv .venv
source .venv/bin/activate          # Windows (PowerShell): .venv\Scripts\Activate.ps1

# Install dependencies.
pip install -r requirements.txt

# Create tables and seed the default user.
python -m app.init_db

# Run the dev server.
uvicorn app.main:app --reload
```

The API is now at `http://localhost:8000`. Interactive Swagger docs:
`http://localhost:8000/docs`. Health check: `http://localhost:8000/health`.

> The backend's default `DATABASE_URL` already matches the Docker Compose
> Postgres, so no extra config is needed. To customize it, create
> `backend/.env` and set `DATABASE_URL`.

> **Sprint 2 (AI itinerary generation)** requires two more vars in
> `backend/.env`:
> - `GEMINI_API_KEY` — a Gemini API key. Required; without it,
>   Generate Itinerary fails with a clean "missing GEMINI_API_KEY" error.
> - `AI_MODEL` — the Gemini model to call, e.g. `gemini-2.5-flash` (this is
>   also the default baked into `app/core/config.py` if the var is unset).
>   Any Gemini model that supports JSON response mode works.

> **Sprint 3 (real place search)** adds one optional var in `backend/.env`:
> - `GOOGLE_PLACES_API_KEY` — a Google Cloud API key with the **Places API**
>   enabled. Get one from the
>   [Google Cloud Console](https://console.cloud.google.com/) →
>   APIs & Services → Credentials, after enabling "Places API" for the
>   project. **Optional for development** — if unset, `resolve_places` skips
>   every item (logged as `skipped`, not `failed`) and itinerary items save
>   with `place_id=null`. The run still completes; nothing crashes.

> **Sprint 4 (route optimization)** adds three new variables:
> - `AI_MODEL_LIGHT` in `backend/.env` — lighter Gemini model for the narration
>   step (e.g. `gemini-2.5-flash-lite`).
> - `GOOGLE_ROUTES_API_KEY` in `backend/.env` — requires "Distance Matrix API"
>   enabled in Google Cloud Console.
> - `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` in `frontend/.env.local` — requires "Maps
>   Static API" enabled.
> 
> *Note: All three Google API keys can share the same key value if all APIs are enabled on the same project.*

### 3. Frontend (Next.js)

In a new terminal:

```bash
cd frontend

# Copy env defaults (points the app at the backend).
cp .env.example .env.local

# Install dependencies and run the dev server.
npm install
npm run dev
```

The app is now at `http://localhost:3000`.

## Sprint 1 Demo Checklist

Run through this end-to-end to confirm the full stack works:

- [ ] **Infra:** `docker compose up -d` — Postgres healthy (`docker compose ps`).
- [ ] **Backend up:** `http://localhost:8000/health` returns
      `{"status":"ok",...}`.
- [ ] **Swagger:** `http://localhost:8000/docs` lists the `/api/trips` CRUD
      endpoints.
- [ ] **Frontend up:** `http://localhost:3000` loads the landing page.
- [ ] **Create:** `/trips/new` — fill the form, submit, and get redirected to the
      new trip's detail page.
- [ ] **Validation:** submitting with a blank title, or an end date before the
      start date, shows an inline error and makes no request.
- [ ] **Persistence:** the trip survives a backend restart (it's in PostgreSQL,
      not memory).
- [ ] **Dashboard:** `/dashboard` lists saved trips, newest first.
- [ ] **Detail:** opening a trip shows its overview and preferences.
- [ ] **Update:** edit a trip, save, and see the changes reflected.
- [ ] **Delete:** delete a trip (with confirm) and return to the dashboard.
- [ ] **Error state:** stop the backend and reload the dashboard — a clear
      "Cannot reach the server" message appears.

## Sprint 2 Demo Checklist

Requires `GEMINI_API_KEY` and `AI_MODEL` set in `backend/.env` (see Setup).

1. **Create a trip with preferences:** `/trips/new` — fill in destination,
   dates, and preferences (interests, food, hotel, must-visit, avoid).
2. **Open the trip detail page** — confirm the Preferences card shows what
   you entered.
3. **Click "Generate Itinerary"** in the Itinerary card — button shows a
   "Generating…" spinner (can take up to 30s).
4. **See the day-by-day itinerary render** — one section per day with theme,
   summary, and a list of timed items (title, type, location, description,
   cost, walking intensity, priority).
5. **(Optional) Inspect the agent run:** `GET /api/trips/{trip_id}` doesn't
   expose the run id directly, so grab it from the network tab's response to
   `POST /api/trips/{trip_id}/generate-itinerary` (field `id`), then:
   - `GET /api/agent-runs/{id}` — shows `status: completed`, `model_used`.
   - `GET /api/agent-runs/{id}/steps` — shows the five-step log
     (`load_trip_preferences` → `build_prompt` → `call_llm` →
     `parse_response` → `save_itinerary`), each with `latency_ms`.
6. **Regenerate:** click the button again (now labeled "Regenerate
   Itinerary") — old days are replaced, not duplicated.
7. **Error path:** unset `GEMINI_API_KEY`, restart the backend, click
   Generate — the UI shows a friendly error with a Retry button instead of
   crashing.

## Sprint 3 Demo Checklist

Requires `GOOGLE_PLACES_API_KEY` set in `backend/.env` (see Setup) to see real
place data — without it, this still works but every item falls back to the
LLM location name.

1. **Create a trip** with a destination and preferences (`/trips/new`).
2. **Click "Generate Itinerary"** on the trip detail page.
3. **Open `GET /api/trips/{trip_id}/itinerary`** — confirm some items have a
   non-null `place` object with a real `name`, `address`, and `rating`.
4. **Open `GET /api/agent-runs/{run_id}/steps`** — confirm a `resolve_places`
   step appears, with `output_json` showing `resolved` / `failed` / `skipped`
   counts.
5. **Open `GET /api/agent-runs/{run_id}/tool-calls`** — confirm one `ToolCall`
   row per resolved item (`tool_name="google_places_text_search"`), plus one
   batched `gemini_price_search_batch` row for price verification.
6. **On the trip detail page**, confirm a **"View on Google Maps"** link
   appears on resolved items.

### Graceful degradation

If `GOOGLE_PLACES_API_KEY` is missing, or a single Places lookup fails, that
item still saves — with `place_id=null` — and the UI falls back to showing
the LLM-generated `location_name` instead of a place card. The failure is
logged (`skipped` or `failed` in the `resolve_places` step's counts) but never
aborts the run: the agent run still ends `completed`, not `failed`.

### Example: generated itinerary (`GET /api/trips/{trip_id}/itinerary`)

Trimmed to one day; a real response has one entry per day in the trip.

```json
[
  {
    "id": 1,
    "trip_id": 4,
    "day_number": 1,
    "date": "2026-08-10",
    "theme": "Arrival & Old Town orientation",
    "summary": "Settle in near the city center, then a gentle walking loop through the historic core with an easy dinner nearby.",
    "created_at": "2026-08-01T14:32:01Z",
    "updated_at": "2026-08-01T14:32:01Z",
    "items": [
      {
        "id": 1,
        "itinerary_day_id": 1,
        "order_index": 0,
        "start_time": "14:00",
        "end_time": "15:00",
        "title": "Hotel check-in",
        "type": "hotel",
        "location_name": "Old Town boutique hotel",
        "description": "Drop bags and freshen up before heading out.",
        "estimated_cost": 0,
        "walking_intensity": "low",
        "priority": "required",
        "created_at": "2026-08-01T14:32:01Z",
        "updated_at": "2026-08-01T14:32:01Z"
      },
      {
        "id": 2,
        "itinerary_day_id": 1,
        "order_index": 1,
        "start_time": "15:30",
        "end_time": "17:30",
        "title": "Old Town walking loop",
        "type": "activity",
        "location_name": "Historic city center",
        "description": "Easy self-guided walk past the main square, cathedral, and riverside promenade.",
        "estimated_cost": 0,
        "walking_intensity": "medium",
        "priority": "recommended",
        "created_at": "2026-08-01T14:32:01Z",
        "updated_at": "2026-08-01T14:32:01Z"
      },
      {
        "id": 3,
        "itinerary_day_id": 1,
        "order_index": 2,
        "start_time": "19:00",
        "end_time": "20:30",
        "title": "Dinner near Old Town",
        "type": "meal",
        "location_name": "Local family-run restaurant",
        "description": "Regional dishes within walking distance of the hotel.",
        "estimated_cost": 35,
        "walking_intensity": "low",
        "priority": "optional",
        "created_at": "2026-08-01T14:32:01Z",
        "updated_at": "2026-08-01T14:32:01Z"
      }
    ]
  }
]
```

## Sprint 4 Demo Checklist

### Architecture Note
Sprint 4 shifted the LLM's role to proposing a flat pool of places (hotel, activities, restaurants), while the backend (`DayPlannerService`) handles all clustering, sequencing, meal assignment, and time-block construction.

### Demo Steps
- [ ] **Generate Itinerary:** Generate an itinerary for a multi-day trip.
- [ ] **Geographic Grouping:** Check that day activities are geographically grouped (spot-check on a map).
- [ ] **Meal Timing:** Confirm meals appear at realistic times in the itinerary view.
- [ ] **Travel Connectors:** See travel time connectors between stops.
- [ ] **Static Map:** See a static map image with place markers per day.
- [ ] **Agent Run Steps:** Hit `GET /api/agent-runs/{run_id}/steps` — confirm 9 steps including `optimize_route` (`days_processed`, `segments_with_routes`) and `narrate_days`.
- [ ] **Route Summary:** Hit `GET /api/trips/{trip_id}/route-summary` — confirm per-day walking totals.

### Graceful Degradation
- If `GOOGLE_ROUTES_API_KEY` is missing, clustering still runs using straight-line distances; days are still geographically grouped, but sequencing within days degrades to arrival order and travel time fields stay null.
- If `GOOGLE_PLACES_API_KEY` is missing, day assignment falls back to round-robin.
- In both cases, the run completes and the itinerary saves successfully.

## Project Layout

```
backend/
  app/
    api/trips.py                       # Trip CRUD + itinerary/generate endpoints
    api/agent_runs.py                  # Agent run + step + tool-call read endpoints
    core/config.py                     # Settings (DATABASE_URL, GEMINI_API_KEY, AI_MODEL,
                                        #   AI_MODEL_LIGHT, GOOGLE_PLACES_API_KEY, GOOGLE_ROUTES_API_KEY)
    models/                            # SQLAlchemy models (Trip, TripPreference, User,
                                        #   AgentRun/AgentStep, ItineraryDay/ItineraryItem,
                                        #   Place, ToolCall — Sprint 3/4)
    schemas/                           # Pydantic request/response schemas
    services/ai_itinerary_service.py   # 9-step agent pipeline (+resolve_places, +resolve_prices,
                                        #   +optimize_route, +narrate_days)
    services/day_planner_service.py    # Backend day clustering, sequencing & scheduling (Sprint 4)
    services/places_service.py         # Google Places API wrapper (Sprint 3)
    services/price_service.py          # Gemini + Google Search price verification (Sprint 3)
    services/route_service.py          # Route optimization and distance matrix client (Sprint 4)
    database.py                        # Engine + session
    init_db.py                         # Create tables + seed default user
    main.py                            # FastAPI app + CORS
frontend/
  app/                  # Next.js App Router pages
    dashboard/          # Saved trips list
    trips/new/          # Create trip form
    trips/[tripId]/     # Trip detail + inline edit form + itinerary view
  components/           # Navbar, Spinner
  lib/api.ts            # Backend API client
  lib/validation.ts     # Client-side form validation
  types/trip.ts         # Shared trip types
  types/itinerary.ts    # Shared itinerary types (Sprint 2)
docker-compose.yml      # PostgreSQL
```
