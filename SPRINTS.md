# GuideGenie Sprint Plan

## Sprint 1: Core Full-Stack Trip Creation

Goal:
User can create, save, view, update, and delete trip requests.

Deliverables:
- Next.js frontend
- FastAPI backend
- PostgreSQL database
- Trip CRUD APIs
- Create trip form
- Dashboard page
- Trip detail page

Definition of Done:
- User can create a trip from the frontend.
- Trip is saved to PostgreSQL.
- Dashboard displays saved trips.
- Trip detail page displays preferences.
- API endpoints work in FastAPI Swagger UI.

## Sprint 2: Basic AI Itinerary Generation

### Goal

Generate a structured day-by-day itinerary from an existing trip request.

Sprint 2 should turn GuideGenie from a basic full-stack CRUD app into an AI-powered itinerary generator.

The user should be able to:

1. Create a trip using the Sprint 1 form.
2. Open the trip detail page.
3. Click **Generate Itinerary**.
4. Wait while the backend calls the LLM.
5. See a structured day-by-day itinerary saved and displayed in the app.

Definition of Done

Sprint 2 is complete when:

User can create a trip.
User can open trip detail page.
User can click Generate Itinerary.
Backend creates an agent_run.
Backend logs agent_steps.
LLM returns structured JSON.
Backend validates the JSON.
Itinerary is saved to PostgreSQL.
Frontend displays the itinerary grouped by day.
Failed LLM calls show a clean error.
README explains Sprint 2 setup and demo steps.

## Sprint 3: Real Place / Restaurant Search

### Goal

Ground every LLM-proposed location in real Google Places data.

Sprint 3 should turn GuideGenie from an AI itinerary generator that invents
placeholder location names into one that resolves every activity, meal, and
hotel suggestion into a real verified place with a real name, address, rating,
and coordinates.

The user should be able to:

1. Create a trip and generate an itinerary as in Sprint 2.
2. See itinerary items enriched with real place data — name, address, rating.
3. Click a **View on Google Maps** link on any resolved item and land on the
   correct place in Google Maps.
4. See a clear visual distinction between items with a resolved real place and
   items that fell back to the LLM-generated location name.
5. (Developer) Hit `GET /api/agent-runs/{run_id}/tool-calls` and see one
   logged ToolCall row per Google Places lookup, with input query, result
   summary, and latency.
6. (Developer) Hit `GET /api/agent-runs/{run_id}/steps` and see a
   `resolve_places` step with a count of how many items were resolved,
   failed, or skipped.

### Definition of Done

Sprint 3 is complete when:

- `places` table exists in PostgreSQL with `google_place_id`, `name`,
  `address`, `lat`, `lng`, `rating`, `price_level`, `types`, `opening_hours`.
- `tool_calls` table exists in PostgreSQL with `tool_name`, `status`,
  `input_json`, `output_json`, `latency_ms`, `cache_hit`, `agent_run_id`.
- `itinerary_items.place_id` FK column exists and is populated for items
  whose location was successfully resolved.
- `PlacesService.resolve_item_place()` calls the Google Places Text Search
  API and returns a `Place` ORM object or `None` on failure.
- `find_or_create_place()` does not insert duplicate rows for the same
  `google_place_id` across multiple generation runs.
- A `resolve_places` AgentStep is logged for every generation run, with
  `output_json` showing `{resolved: N, failed: N, skipped: N}`.
- A `ToolCall` row is committed for every Google Places API call made.
- `GET /api/trips/{trip_id}/itinerary` returns a nested `place` object
  (name, address, rating, google_place_id, lat, lng) inside each item that
  was resolved; `null` for unresolved items.
- `GET /api/agent-runs/{run_id}/tool-calls` returns all tool call logs for
  a run.
- Frontend displays real address and rating on resolved items.
- Frontend shows a **View on Google Maps** link on resolved items.
- Frontend shows a visual indicator distinguishing resolved from unresolved
  items.
- If `GOOGLE_PLACES_API_KEY` is missing or a lookup fails, the item saves
  with `place_id=null` and the UI falls back to the LLM location name —
  no crash, no failed run.
- README documents `GOOGLE_PLACES_API_KEY` setup and a Sprint 3 demo
  checklist.

## Sprint 4: Route Optimization + Backend Day Planning

### Goal

Take scheduling control away from the LLM and give it to the backend.

Sprint 4 redesigns the core pipeline so the LLM's job is limited to proposing
a flat pool of real, named places — one hotel, a list of activities and events,
and restaurant options. All structural decisions (which places go on which day,
what order to visit them, when to eat, when to rest) are made by a deterministic
backend scheduler (`DayPlannerService`) using real geographic coordinates and
real travel times from the Google Distance Matrix API. A second, lightweight LLM
call writes day themes and summaries after the schedule is built.

This is the architecture the project has always aimed for: LLM proposes →
tools verify → backend clusters and schedules → LLM narrates.

The user should be able to:

1. Generate an itinerary as in Sprint 3, with no change to the UI flow.
2. See itinerary days that are geographically coherent — nearby places grouped
   together — rather than in the arbitrary order the LLM chose.
3. See meals land at realistic times (breakfast ~08:00, lunch ~12:00, dinner
   ~19:00) and a rest block automatically inserted mid-afternoon.
4. See travel time and distance displayed between consecutive stops in the day
   view — e.g. "~12 min walk · 850 m".
5. See a per-day route summary showing total walking time and whether the
   route was successfully optimized.
6. See a static map image per day with a marker for every resolved place.
7. (Developer) Hit `GET /api/agent-runs/{run_id}/steps` and see 9 steps,
   including `optimize_route` (with clustering and scheduling counts) and
   `narrate_days` (with days narrated count).
8. (Developer) Hit `GET /api/trips/{trip_id}/route-summary` and see per-day
   totals: `route_optimized`, `total_walking_minutes`, `total_distance_meters`.

### Definition of Done

Sprint 4 is complete when:

- The LLM is prompted to return `TripPlanAIResponse` — a flat pool containing
  one `hotel`, a list of `activities` (with `durationMinutes`, `priority`,
  `walkingIntensity`, `bestTimeOfDay`), and a list of `restaurants` (with
  `mealType`). The LLM no longer assigns days, dates, or times.
- `HotelAI`, `ActivityAI`, `RestaurantAI`, `TripPlanAIResponse` schemas exist
  in `app/schemas/itinerary.py` with camelCase aliases. The old
  `ItineraryAIResponse`/`ItineraryDayAI`/`ItineraryItemAI` schemas are removed.
- `DayNarrationAI` and `DayNarrationBatchAI` schemas exist for the narration
  LLM call output.
- `app/services/day_planner_service.py` exists and implements:
  - k-means clustering of resolved activities by lat/lng into D day-clusters
    (equirectangular projection, no external dependency, reproducible output)
  - Capacity-balanced cluster assignment for unresolved activities
  - Day ordering by nearest-neighbor from the hotel centroid
  - Within-day activity sequencing via Google Distance Matrix (nearest-neighbor)
  - Meal assignment: nearest unused lunch/dinner restaurant to the day's centroid
  - Time-block construction: breakfast 08:00–09:00, hotel check-in 09:00–09:30
    (day 1), activities from 09:30 with travel gaps rounded to 5 min, lunch
    after 12:00, 30-min rest after 15:30, dinner at/after 19:00, hotel
    check-out (last day)
  - Overflow handling: optional activities dropped if day runs past 18:30
  - `_fallback_plan()` for when no coordinates are available or any exception
    occurs (round-robin day assignment, same time template, no network calls)
- `app/services/route_service.py` retains `get_distance_matrix()` and
  `nearest_neighbor_order()` (pure function). The old `optimize_day()` is removed.
- `AI_MODEL_LIGHT` setting exists in `app/core/config.py` (default
  `gemini-flash-lite-latest` — an auto-updating alias; pinned lite versions
  like `gemini-2.5-flash-lite` can 404 as "no longer available to new users").
- `AgentStepName.NARRATE_DAYS` exists in `app/models/agent.py`.
- The pipeline has 9 steps: `load_trip_preferences` → `build_prompt` →
  `call_llm` → `parse_response` → `resolve_places` → `resolve_prices` →
  `optimize_route` → `narrate_days` → `save_itinerary`.
- The `optimize_route` step logs `{days_processed, activities_scheduled,
  segments_with_routes, total_tool_calls}`.
- The `narrate_days` step makes one batched LLM call using `AI_MODEL_LIGHT`
  and logs `{days_narrated}`. On failure, each day falls back to a deterministic
  theme from its scheduled activity titles.
- `ItineraryItem` ORM objects are constructed inside `DayPlannerService` (not
  in `save_itinerary`) so `travel_time_to_next_minutes`, `distance_to_next_meters`,
  and `travel_mode_to_next` are set before DB insertion.
- `GET /api/trips/{trip_id}/itinerary` returns `travel_time_to_next_minutes`,
  `distance_to_next_meters`, and `travel_mode_to_next` on each item. `*Read`
  schemas are otherwise unchanged from Sprint 3.
- `GET /api/trips/{trip_id}/route-summary` returns a per-day list with
  `route_optimized`, `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, and `item_count`. `RouteDaySummary` schema exists.
- Frontend shows a travel segment connector (time + distance) between
  consecutive items when `travel_time_to_next_minutes` is non-null.
- Frontend shows a route summary badge per day when `route_optimized` is true.
- Frontend shows a Google Maps Static API `<img>` per day with a marker for
  each resolved place. Days with no resolved places hide the map.
- If `GOOGLE_PLACES_API_KEY` is missing: no coordinates → `_fallback_plan()`,
  round-robin days, no travel fields. Run completes.
- If `GOOGLE_ROUTES_API_KEY` is missing: clustering still runs (haversine
  only); sequencing degrades to arrival order; travel fields stay null. Run
  completes.
- If `narrate_days` fails: deterministic fallback themes; run still completes.
- README documents `GOOGLE_ROUTES_API_KEY`, `AI_MODEL_LIGHT`, and
  `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY` setup and a Sprint 4 demo checklist.

## Sprint 5: Rest Stop Insertion

Goal:
Insert cafes/convenience stores/rest areas if walking is too long.

## Sprint 6: Events / Festivals Discovery

Goal:
Find local events during trip dates.

## Sprint 7: Constraint Validation

Goal:
Validate walking, budget, opening hours, and time feasibility.

## Sprint 8: Editable Itinerary + Approval

Goal:
Allow user edits and final approval before external actions.

## Sprint 9: Google Calendar Sync

Goal:
Sync approved itinerary items to Google Calendar.

## Sprint 10: Redis + Background Jobs

Goal:
Add caching and async processing.

## Sprint 11: Observability Dashboard

Goal:
Show agent steps, tool calls, latency, and cache hits.

## Sprint 12: Cloud + CI/CD + Polish

Goal:
Deploy and prepare project for resume/demo.