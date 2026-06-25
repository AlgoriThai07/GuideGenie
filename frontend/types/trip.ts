/**
 * Trip domain types.
 *
 * These mirror the Sprint 1 backend trip CRUD API (FastAPI + Pydantic).
 * Read shapes match `TripRead` / `TripPreferenceRead`; input shapes match
 * `TripCreate` / `TripUpdate`.
 *
 * Notes on field formats coming from the backend:
 * - `start_date` / `end_date` are ISO date strings (`YYYY-MM-DD`) or null.
 * - `created_at` / `updated_at` are ISO datetime strings.
 * - `budget` is a Pydantic `Decimal`, which serializes to a JSON *string*
 *   (e.g. "1500.00") on read. On input a number is accepted and coerced.
 */

/** Trip lifecycle. Matches backend `TripStatus`. */
export type TripStatus = "draft" | "planned" | "completed" | "archived";

/** Shared trip preference fields (one-to-one with a trip). */
export interface TripPreferenceBase {
  travel_style: string | null;
  max_walking_minutes_between_stops: number | null;
  max_total_walking_minutes_per_day: number | null;
  interests: string[];
  hotel_preferences: string[];
  food_preferences: string[];
  must_visit_places: string[];
  avoid_places: string[];
}

/** Trip preference as returned by the API (`TripPreferenceRead`). */
export interface TripPreference extends TripPreferenceBase {
  id: number;
  trip_id: number;
}

/** A trip as returned by the API (`TripRead`). */
export interface Trip {
  id: number;
  user_id: number;
  title: string;
  destination: string;
  start_date: string | null;
  end_date: string | null;
  travelers: number;
  budget: string | null;
  status: TripStatus;
  created_at: string;
  updated_at: string;
  preference: TripPreference | null;
}

/** Preference fields when creating/updating a trip (`TripPreferenceCreate`). */
export interface TripPreferenceInput {
  travel_style?: string | null;
  max_walking_minutes_between_stops?: number | null;
  max_total_walking_minutes_per_day?: number | null;
  interests?: string[];
  hotel_preferences?: string[];
  food_preferences?: string[];
  must_visit_places?: string[];
  avoid_places?: string[];
}

/** Request body for creating a trip (`TripCreate`). */
export interface CreateTripInput {
  title: string;
  destination: string;
  start_date?: string | null;
  end_date?: string | null;
  travelers?: number;
  budget?: number | string | null;
  status?: TripStatus;
  preference?: TripPreferenceInput | null;
}

/** Request body for a partial update (`TripUpdate`). All fields optional. */
export type UpdateTripInput = Partial<CreateTripInput>;
