# Redesign: LLM place pool → backend day clustering + scheduling

Status: implemented on branch `sprint4`.

## Why this changed

The original Sprint 4 plan had the LLM produce a full day-by-day itinerary
(same as Sprints 2-3), and the backend only reordered *within* each day using
nearest-neighbor over the Google Distance Matrix API. That means the LLM was
still deciding which places belong on which day — a geographic/logistics
decision an LLM is bad at and a deterministic backend is good at.

The new design: **the LLM proposes a flat pool of real places (one hotel,
many activities/events, many restaurant options), and the backend clusters
them into geographically tight days, sequences each day, and assigns time
blocks.** This matches the project's own architecture principle: "LLM
proposes → tools verify → backend optimizes → backend validates → LLM
explains" (`CLAUDE.md`).

A second, very cheap LLM call ("narration") writes day themes/summaries
after the schedule exists, so the itinerary still reads naturally without
giving the LLM control over structure.

## Old vs. new pipeline

| Step | Old (Sprint 4 original plan) | New |
|---|---|---|
| 1 | `load_trip_preferences` | same |
| 2 | `build_prompt` | same shape, new contract (see below) |
| 3 | `call_llm` | same mechanics, new prompt |
| 4 | `parse_response` — `ItineraryAIResponse` (days + items) | `TripPlanAIResponse` (hotel + activities + restaurants, flat) |
| 5 | `resolve_places` — keyed by `(day_index, item_index)` | keyed by `("hotel"\|"activity"\|"restaurant", index)` |
| 6 | `resolve_prices` | same pattern, new keys |
| 7 | `optimize_route` — reorder *within* LLM-assigned days | `optimize_route` — **cluster into days**, order days, sequence within day, assign meals, build time blocks, construct `ItineraryItem` rows |
| 8 | — | **new:** `narrate_days` — one batched, cheap LLM call for day themes/summaries |
| 9 | `save_itinerary` | same role, persists day route-summary columns too |

No database schema changes — all Sprint 4 columns already existed
(`itinerary_days.total_walking_minutes` / `total_transit_minutes` /
`total_distance_meters` / `route_optimized`; `itinerary_items
.travel_time_to_next_minutes` / `distance_to_next_meters` /
`travel_mode_to_next`).

## New LLM contract (`TripPlanAIResponse`)

The LLM no longer assigns days, dates, or times — only real places and
rough scheduling hints (duration, priority, walking intensity, best time of
day).

```json
{
  "tripTitle": "string",
  "overview": "string",
  "hotel": {
    "name": "string",
    "description": "string",
    "estimatedCostPerNight": 0
  },
  "activities": [
    {
      "name": "string",
      "type": "activity | event",
      "durationMinutes": 90,
      "priority": "required | recommended | optional",
      "walkingIntensity": "low | medium | high",
      "description": "string",
      "estimatedCost": 0,
      "bestTimeOfDay": "morning | afternoon | evening | any"
    }
  ],
  "restaurants": [
    {
      "name": "string",
      "mealType": "lunch | dinner",
      "description": "string",
      "estimatedCost": 0
    }
  ]
}
```

Prompt asks for `3*D` to `4*D` activities and `D+1` lunch / `D+1` dinner
options, where `D` = trip length in days (breakfast is always at the hotel,
so no breakfast venues are requested). Descriptions are written here
(place-specific, order-independent) so the narration call doesn't need to
repeat that work.

## Backend scheduling (`DayPlannerService`, new file
`app/services/day_planner_service.py`)

1. **Cluster** — resolved activities (those with a Google Places match) are
   grouped into `D` clusters via a deterministic, capacity-balanced k-means
   over an equirectangular projection of lat/lng (no external dependency,
   no randomness — reproducible runs). Unresolved activities round-robin
   onto the smallest days afterward.
2. **Order the days** — cluster centroids are visited in nearest-neighbor
   order starting from the hotel, so day 1 is whichever cluster sits
   closest to the hotel.
3. **Sequence within a day** — resolved activities in a day are ordered by
   nearest-neighbor over a real Google Distance Matrix (walking mode);
   falls back to arrival order if the API is unavailable.
4. **Assign meals** — nearest unused lunch/dinner restaurant to the day's
   centroid.
5. **Time blocks** — fixed daily template: breakfast 08:00-09:00 → (day 1
   only) hotel check-in 09:00-09:30 → activities from 09:30, each with a
   travel gap rounded up to 5 minutes → lunch once the clock passes 12:00 →
   a 30-minute rest block once it passes 15:30 → dinner at/after 19:00 →
   (last day only) hotel check-out. If a day would run past 18:30,
   `optional`-priority activities are dropped first; if the overflowing
   activity isn't optional, the rest of that day's remaining activities are
   dropped.
6. **Build `ItineraryItem` rows** directly (not in `save_itinerary`), with
   `travel_time_to_next_minutes` / `distance_to_next_meters` /
   `travel_mode_to_next` populated between consecutive *scheduled activity*
   items only (meal/rest/hotel items keep these `None`).

`DayPlannerService.plan_days()` never raises: any internal failure falls
back to `_fallback_plan()` — naive round-robin day assignment using the same
time template but no clustering/Distance Matrix calls. The same fallback
path (not just on error) is used when `GOOGLE_ROUTES_API_KEY` is missing, so
no network calls are wasted.

## Narration pass (latency-optimized)

Writing day themes/summaries is order-dependent (it needs to know what ended
up on each day), so it has to happen after scheduling — but it's kept as
cheap as possible:

- **One batched call for the whole trip**, not one per day. Input is a
  compact skeleton: `"Day 1: Senso-ji -> Nakamise -> Ichiran (lunch) ->
  teamLab"` per day.
- **A separate, lighter/faster model** (`settings.AI_MODEL_LIGHT`, default
  `gemini-flash-lite-latest` — an auto-updating alias, since pinned lite
  model versions like `gemini-2.5-flash-lite` can 404 as "no longer
  available to new users") — narration needs no reasoning, just phrasing.
- **Capped output** (`max_output_tokens=500`) and JSON mode, so the call
  resolves in well under a second typically.
- **Never blocks the run.** On failure/timeout/parse error, each day falls
  back to a deterministic theme/summary built from its own scheduled
  activity titles.

New `AgentStepName.NARRATE_DAYS` step, logged between `optimize_route` and
`save_itinerary`.

## Files affected

| File | Change |
|---|---|
| `backend/app/services/ai_itinerary_service.py` | Rewritten: new prompts, new parse target, restructured steps 5-9, new `narrate_days` step |
| `backend/app/schemas/itinerary.py` | `ItineraryAIResponse`/`ItineraryDayAI`/`ItineraryItemAI` replaced with `HotelAI`/`ActivityAI`/`RestaurantAI`/`TripPlanAIResponse`; added `DayNarrationAI`/`DayNarrationBatchAI`. `*Read` schemas unchanged |
| `backend/app/services/day_planner_service.py` | **New file** — clustering, day ordering, meal assignment, time-block scheduling, `ItineraryItem` construction |
| `backend/app/services/route_service.py` | Removed the anchor-based `optimize_day`/`_optimize_day_inner` (obsolete — the backend now builds days itself instead of reordering LLM-given days). Kept `get_distance_matrix`, `_get_distance_matrix_full`, `nearest_neighbor_order`, `_log_tool_call` — now consumed by `day_planner_service` |
| `backend/app/models/agent.py` | Added `AgentStepName.NARRATE_DAYS` |
| `backend/app/core/config.py` | Added `AI_MODEL_LIGHT` setting |
| `CLAUDE.md` | Updated Sprint 4 section, architecture principles, folder structure, and coding conventions to describe the new pipeline |

**Unchanged:** DB models/migrations (all Sprint 4 columns pre-existed), `*Read`
schemas, `app/api/trips.py`, `app/api/agent_runs.py`, `places_service.py`,
`price_service.py`, frontend (`ItineraryDayRead`/`ItineraryItemRead` shape is
identical, so `frontend/types/itinerary.ts` and `ItineraryView.tsx` need no
changes).

## Explicitly out of scope for this change

- `GET /api/trips/{trip_id}/route-summary` endpoint and the `RouteDaySummary`
  schema mentioned in the original Sprint 4 checklist — not yet implemented,
  tracked as a follow-up.
- Frontend travel-time connectors and the static map image — separate
  Sprint 4 frontend tasks, unaffected by this backend redesign.
- Rest-stop *tuning* beyond the fixed template block — Sprint 5.
- Ticketmaster/events sourcing — Sprint 6 (the `event` item type already
  exists as an LLM-proposable pool entry type, just no external events API
  yet).
- Replanning/user editing — Sprint 7. Note this redesign makes that sprint
  easier: since the pool and the schedule are now separate, replanning can
  mutate the place pool and re-run `DayPlannerService` without another LLM
  call.

## Degradation matrix

| Missing/failing | Behavior |
|---|---|
| `GEMINI_API_KEY` | Run fails at `call_llm` (unchanged from before) |
| `GOOGLE_PLACES_API_KEY` | No coordinates resolved → round-robin day assignment (via the same fallback path), template times, no travel fields |
| `GOOGLE_ROUTES_API_KEY` | Clustering still runs (haversine only, no network calls); day ordering and within-day sequencing degrade to arrival order; travel fields stay `None` |
| `narrate_days` failure/timeout | Each day gets a deterministic theme/summary from its own scheduled activities; run still completes |
| Unexpected exception anywhere in `optimize_route` | Caught locally, falls back to `_fallback_plan()`, step logged `COMPLETED` with a `warning`, run continues |

## Verification

1. Restart the backend (`uvicorn app.main:app --reload` from `backend/`). No
   DB reset needed.
2. `POST /api/trips/{trip_id}/generate-itinerary` for an existing multi-day
   trip.
3. `GET /api/agent-runs/{run_id}/steps` → 9 steps; `optimize_route` shows
   `days_processed` / `activities_scheduled` / `segments_with_routes` /
   `total_tool_calls`; `narrate_days` shows `days_narrated`.
4. `GET /api/trips/{trip_id}/itinerary` → each day's activities should be
   geographically coherent (spot-check on a map); consecutive scheduled
   activities have non-null `travel_time_to_next_minutes`; themes/summaries
   are present; meals land around 08:00 / 12:xx / 19:00.
5. Degradation checks: unset `GOOGLE_ROUTES_API_KEY` → run completes, days
   still clustered, travel fields null. Unset `GOOGLE_PLACES_API_KEY` → run
   completes, round-robin day assignment.
6. Pure-logic smoke test (no DB/network) for the clustering + scheduling
   functions in `day_planner_service.py`: `_kmeans_labels` /
   `_balance_clusters` / `_order_clusters` / `_build_day_items` are all
   plain functions and straightforward to unit test or exercise in a REPL
   with synthetic lat/lng points and `PoolActivity`/`PoolRestaurant`/
   `HotelInfo` objects.
