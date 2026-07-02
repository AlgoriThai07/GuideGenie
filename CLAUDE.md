# GuideGenie — Claude Context

AI travel planning agent. Long-term: route-optimized itineraries w/ real places, hotels, events, Calendar sync. **Currently: Sprint 2 only.**

## Stack
- FE: Next.js, TypeScript, Tailwind, App Router
- BE: FastAPI, Python, PostgreSQL, SQLAlchemy/SQLModel, Pydantic, Alembic (if configured)
- AI: Gemini API (`google-genai`). Read `GEMINI_API_KEY`, `AI_MODEL` from env.

## Sprint 1 (done)
Next.js FE, FastAPI BE, Postgres, Trip CRUD APIs, create-trip form, dashboard, trip detail page.

## Sprint 2 Goal
Generate a structured day-by-day itinerary from an existing trip: user clicks **Generate Itinerary** → backend calls LLM → validates JSON → saves to Postgres → frontend displays itinerary by day.

### In scope
AI itinerary generation service, agent run/step tracking, itinerary day/item storage, itinerary read endpoints, generate endpoint, FE generate button + display.

### Out of scope (do not implement)
LangGraph, Google Places/Routes API, Ticketmaster, route optimization, rest-stop insertion, Redis, Celery/RQ, Calendar sync, cloud deploy, full observability dashboard, auth changes (unless required).

## DB Models to Add

**agent_runs**: id, trip_id, status, model_used, started_at, completed_at, error_message, created_at, updated_at
Statuses: `pending`, `running`, `completed`, `failed`

**agent_steps**: id, agent_run_id, step_name, status, input_json, output_json, error_message, latency_ms, created_at
Step names: `load_trip_preferences`, `build_prompt`, `call_llm`, `parse_response`, `save_itinerary`

**itinerary_days**: id, trip_id, day_number, date, theme, summary, created_at, updated_at

**itinerary_items**: id, itinerary_day_id, order_index, start_time, end_time, title, type, location_name, description, estimated_cost, walking_intensity, priority, created_at, updated_at
- type: `activity`|`meal`|`hotel`|`transport`|`rest`|`event`|`free_time`
- walking_intensity: `low`|`medium`|`high`
- priority: `required`|`recommended`|`optional`

## LLM Output Contract
Valid JSON only, no markdown. Shape:
```json
{
  "tripTitle": "string",
  "overview": "string",
  "days": [{
    "dayNumber": 1, "date": "YYYY-MM-DD", "theme": "string", "summary": "string",
    "items": [{
      "startTime": "HH:MM", "endTime": "HH:MM", "title": "string", "type": "activity",
      "locationName": "string", "description": "string", "estimatedCost": 5,
      "walkingIntensity": "low", "priority": "recommended"
    }]
  }]
}
```
Validate with Pydantic before saving.

## Prompt Rules
JSON only, no markdown, no invented ratings/review counts/opening hours, placeholder locations OK. Respect: date range, destination, walking tolerance, interests, food prefs, hotel prefs, must-visit, avoid-list. Include meals + rest/free time. Max 4 major activities/day, realistic pacing. Every item needs start/end times; every day needs theme + summary. Must match schema.

## Endpoints
```
POST /api/trips/{trip_id}/generate-itinerary   (sync for Sprint 2)
GET  /api/trips/{trip_id}/itinerary
GET  /api/agent-runs/{run_id}
GET  /api/agent-runs/{run_id}/steps
```

## Service: `backend/app/services/ai_itinerary_service.py`
1. Load trip + preferences
2. Create agent_run (`running`)
3. Log agent_steps
4. Build prompt → call LLM → parse JSON → validate (Pydantic)
5. Replace existing itinerary if regenerating
6. Save itinerary_days + itinerary_items
7. Mark agent_run `completed` (or `failed` + error_message on error)

## Frontend (trip detail page)
- Show trip preferences
- "Generate Itinerary" button → POST generate-itinerary, loading state, error state
- On success → GET itinerary → display grouped by day
- Each item shows: time range, title, type, location, description, cost, walking intensity, priority

## Error Handling
Cover: trip not found, missing preferences, missing LLM API key, invalid JSON from LLM, Pydantic validation failure, DB save failure. On failure: mark agent_run `failed`, store error_message, return clean API error, show friendly UI message.

## Code Style
Modular, logic in services not route handlers, Pydantic for validation, typed FE components, no unnecessary libs, no overengineering, no future-sprint features. Update README only for Sprint 2 setup.

## Definition of Done
Create trip → open detail → Generate Itinerary → agent_run created → steps logged → LLM JSON validated → itinerary saved → FE displays by day → failures show clean error → README documents env vars + demo steps.

## Next: Sprint 3
Real place/restaurant search. Don't start until Sprint 2 is done.