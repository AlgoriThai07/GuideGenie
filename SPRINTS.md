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

## Sprint 4: Route Optimization MVP

### Goal

Order each day's stops logically using real travel times and a nearest-neighbor
heuristic, and surface that route data to the user.

Sprint 4 should turn GuideGenie from an app that displays stops in whatever
order the LLM invented into one that groups nearby activities together,
calculates real travel time between each stop, and shows the user how long
they'll spend getting from place to place each day.

The user should be able to:

1. Generate an itinerary as in Sprint 3.
2. See travel time and distance displayed between consecutive stops in the
   day view — e.g. "~12 min walk · 850 m".
3. See a per-day route summary badge showing total walking time when the route
   was successfully optimized — e.g. "Route optimized · ~34 min walking total".
4. See a static map image for each day with a pin for every resolved place,
   giving a geographic sense of the day's route.
5. (Developer) Hit `GET /api/trips/{trip_id}/route-summary` and see per-day
   totals: `total_walking_minutes`, `total_distance_meters`, `route_optimized`.
6. (Developer) Hit `GET /api/agent-runs/{run_id}/steps` and see an
   `optimize_route` step with counts of segments resolved and days optimized.
7. (Developer) Hit `GET /api/agent-runs/{run_id}/tool-calls` and see one
   `google_distance_matrix` ToolCall row per Distance Matrix API call made
   during route optimization.

### Definition of Done

Sprint 4 is complete when:

- `itinerary_items` table has `travel_time_to_next_minutes` (Integer, nullable),
  `distance_to_next_meters` (Integer, nullable), and `travel_mode_to_next`
  (String, nullable) columns.
- `itinerary_days` table has `total_walking_minutes` (Integer, nullable),
  `total_transit_minutes` (Integer, nullable), `total_distance_meters`
  (Integer, nullable), and `route_optimized` (Boolean, default False) columns.
- `RouteService.get_distance_matrix()` calls the Google Distance Matrix API
  and returns an N×M matrix of travel times in minutes (None for missing pairs).
- `RouteService.nearest_neighbor_order()` is a pure function — no API calls,
  no DB — that takes a travel-time matrix and returns an optimized visit order.
- `RouteService.optimize_day()` reorders activity/event items with a resolved
  place using nearest-neighbor, keeps all other items (hotel, meal, rest,
  free_time, transport) and items without a place in their original relative
  positions, and populates travel time fields on every item.
- Every Distance Matrix API call is logged as a `ToolCall` row with
  `tool_name="google_distance_matrix"`.
- An `optimize_route` AgentStep is logged for every generation run, with
  `output_json` showing `{days_processed, days_optimized, segments_with_routes,
  total_tool_calls}`.
- `ItineraryItem` ORM objects are constructed during the `optimize_route`
  step (not `save_itinerary`) so travel fields are set before DB insertion.
- `GET /api/trips/{trip_id}/itinerary` returns `travel_time_to_next_minutes`,
  `distance_to_next_meters`, and `travel_mode_to_next` on each item.
- `GET /api/trips/{trip_id}/route-summary` returns a per-day list with
  `route_optimized`, `total_walking_minutes`, `total_transit_minutes`,
  `total_distance_meters`, and `item_count`.
- Frontend displays a travel segment connector between each consecutive pair
  of items when `travel_time_to_next_minutes` is non-null.
- Frontend displays a route summary badge per day when `route_optimized` is true.
- Frontend displays a Google Maps Static API image per day showing a marker
  for each resolved place.
- If `GOOGLE_ROUTES_API_KEY` is missing, the `optimize_route` step logs
  `{skipped: "no GOOGLE_ROUTES_API_KEY"}` and continues — travel fields
  remain null, the itinerary saves normally, no crash, no failed run.
- README documents `GOOGLE_ROUTES_API_KEY` and `NEXT_PUBLIC_GOOGLE_MAPS_API_KEY`
  setup and a Sprint 4 demo checklist.

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