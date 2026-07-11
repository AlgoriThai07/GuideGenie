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

## Sprint 4: Route Optimization

Goal:
Order itinerary stops logically and calculate walking time.

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