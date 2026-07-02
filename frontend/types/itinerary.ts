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
  walking_intensity: WalkingIntensity | null;
  priority: ItineraryItemPriority;
  order_index: number;
}

/** An itinerary day as returned by the API (`ItineraryDayRead`). */
export interface ItineraryDay {
  id: number;
  trip_id: number;
  day_number: number;
  date: string | null;
  theme: string | null;
  summary: string | null;
  items: ItineraryItem[];
}

/** An agent run as returned by the API (`AgentRunRead`). */
export interface AgentRun {
  id: number;
  trip_id: number;
  status: AgentRunStatus;
  model_used: string | null;
  error_message: string | null;
}
