/**
 * Itinerary domain types.
 *
 * Mirror the Sprint 2 backend itinerary API (FastAPI + Pydantic).
 * Read shapes match `ItineraryDayRead` / `ItineraryItemRead` /
 * `AgentRunRead`. All fields are snake_case — the backend only uses
 * camelCase aliases internally when validating raw LLM JSON, not at the
 * API boundary.
 *
 * `estimated_cost` is a Pydantic `Decimal`, which serializes to a JSON
 * *string* (e.g. "12.50"), same as `Trip.budget` in `types/trip.ts`.
 */

export type ItineraryItemType =
  | "activity"
  | "meal"
  | "hotel"
  | "transport"
  | "rest"
  | "event"
  | "free_time";

export type WalkingIntensity = "low" | "medium" | "high";

export type ItineraryItemPriority = "required" | "recommended" | "optional";

export type AgentRunStatus = "pending" | "running" | "completed" | "failed";

/** A resolved place as returned by the API (`PlaceRead`). */
export interface Place {
  id: number;
  google_place_id: string;
  name: string;
  address: string | null;
  lat: number | null;
  lng: number | null;
  rating: number | null;
  price_level: number | null;
  types: string[];
  opening_hours: Record<string, unknown> | null;
  maps_url: string;
  created_at: string;
  updated_at: string;
}

/** An itinerary item as returned by the API (`ItineraryItemRead`). */
export interface ItineraryItem {
  id: number;
  itinerary_day_id: number;
  start_time: string;
  end_time: string;
  title: string;
  type: ItineraryItemType;
  location_name: string | null;
  description: string | null;
  estimated_cost: string | null;
  verified_cost: string | null;
  price_source: string | null;
  walking_intensity: WalkingIntensity | null;
  priority: ItineraryItemPriority;
  order_index: number;
  place: Place | null;
  travel_time_to_next_minutes: number | null;
  distance_to_next_meters: number | null;
  travel_mode_to_next: string | null;
}

/** An itinerary day as returned by the API (`ItineraryDayRead`). */
export interface ItineraryDay {
  id: number;
  trip_id: number;
  day_number: number;
  date: string | null;
  theme: string | null;
  summary: string | null;
  total_walking_minutes: number | null;
  total_transit_minutes: number | null;
  total_distance_meters: number | null;
  route_optimized: boolean;
  items: ItineraryItem[];
}

/** Per-day route totals as returned by the API (`RouteDaySummary`). */
export interface RouteDaySummary {
  day_number: number;
  date: string | null;
  theme: string | null;
  route_optimized: boolean;
  total_walking_minutes: number | null;
  total_transit_minutes: number | null;
  total_distance_meters: number | null;
  item_count: number;
}

/** An agent run as returned by the API (`AgentRunRead`). */
export interface AgentRun {
  id: number;
  trip_id: number;
  status: AgentRunStatus;
  model_used: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
