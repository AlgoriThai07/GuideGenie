"use client";

/**
 * Inline edit form for a trip, rendered on the trip detail page.
 *
 * Prefills its fields from the loaded trip, converts comma-separated list
 * fields into arrays, and PUTs via `updateTrip`. On success it hands the
 * updated trip back to the parent via `onSaved`.
 */

import { useState } from "react";

import { ApiError, updateTrip } from "@/lib/api";
import type { Trip, TripPreferenceInput, UpdateTripInput } from "@/types/trip";

/** Split a comma-separated string into a trimmed, non-empty string array. */
function toList(csv: string): string[] {
  return csv
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Join a string array into a comma-separated string for an input field. */
function fromList(items: string[]): string {
  return items.join(", ");
}

/** Parse a numeric input into a number, or `null` when blank/invalid. */
function toNumberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  const n = Number(trimmed);
  return Number.isNaN(n) ? null : n;
}

const inputClass =
  "mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm " +
  "text-gray-900 shadow-sm focus:border-gray-900 focus:outline-none focus:ring-1 " +
  "focus:ring-gray-900";

interface TripEditFormProps {
  trip: Trip;
  onSaved: (trip: Trip) => void;
  onCancel: () => void;
}

export default function TripEditForm({
  trip,
  onSaved,
  onCancel,
}: TripEditFormProps) {
  const pref = trip.preference;

  // Trip fields.
  const [title, setTitle] = useState(trip.title);
  const [destination, setDestination] = useState(trip.destination);
  const [startDate, setStartDate] = useState(trip.start_date ?? "");
  const [endDate, setEndDate] = useState(trip.end_date ?? "");
  const [travelers, setTravelers] = useState(String(trip.travelers));
  const [budget, setBudget] = useState(trip.budget ?? "");

  // Preference fields.
  const [travelStyle, setTravelStyle] = useState(pref?.travel_style ?? "");
  const [maxWalkBetween, setMaxWalkBetween] = useState(
    pref?.max_walking_minutes_between_stops?.toString() ?? "",
  );
  const [maxWalkPerDay, setMaxWalkPerDay] = useState(
    pref?.max_total_walking_minutes_per_day?.toString() ?? "",
  );
  const [interests, setInterests] = useState(fromList(pref?.interests ?? []));
  const [hotelPreferences, setHotelPreferences] = useState(
    fromList(pref?.hotel_preferences ?? []),
  );
  const [foodPreferences, setFoodPreferences] = useState(
    fromList(pref?.food_preferences ?? []),
  );
  const [mustVisitPlaces, setMustVisitPlaces] = useState(
    fromList(pref?.must_visit_places ?? []),
  );
  const [avoidPlaces, setAvoidPlaces] = useState(
    fromList(pref?.avoid_places ?? []),
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const preference: TripPreferenceInput = {
      travel_style: travelStyle.trim() || null,
      max_walking_minutes_between_stops: toNumberOrNull(maxWalkBetween),
      max_total_walking_minutes_per_day: toNumberOrNull(maxWalkPerDay),
      interests: toList(interests),
      hotel_preferences: toList(hotelPreferences),
      food_preferences: toList(foodPreferences),
      must_visit_places: toList(mustVisitPlaces),
      avoid_places: toList(avoidPlaces),
    };

    const input: UpdateTripInput = {
      title: title.trim(),
      destination: destination.trim(),
      start_date: startDate || null,
      end_date: endDate || null,
      travelers: toNumberOrNull(travelers) ?? 1,
      budget: toNumberOrNull(budget),
      preference,
    };

    try {
      const updated = await updateTrip(trip.id, input);
      onSaved(updated);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong while saving the trip. Please try again.";
      setError(message);
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-8">
      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {/* Trip details */}
      <fieldset className="flex flex-col gap-4">
        <legend className="text-lg font-semibold text-gray-900">
          Trip details
        </legend>

        <label className="block text-sm font-medium text-gray-700">
          Title
          <input
            type="text"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={inputClass}
          />
        </label>

        <label className="block text-sm font-medium text-gray-700">
          Destination
          <input
            type="text"
            required
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            className={inputClass}
          />
        </label>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-gray-700">
            Start date
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className={inputClass}
            />
          </label>

          <label className="block text-sm font-medium text-gray-700">
            End date
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-gray-700">
            Travelers
            <input
              type="number"
              min={1}
              value={travelers}
              onChange={(e) => setTravelers(e.target.value)}
              className={inputClass}
            />
          </label>

          <label className="block text-sm font-medium text-gray-700">
            Budget
            <input
              type="number"
              min={0}
              step="0.01"
              value={budget}
              onChange={(e) => setBudget(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>
      </fieldset>

      {/* Preferences */}
      <fieldset className="flex flex-col gap-4">
        <legend className="text-lg font-semibold text-gray-900">
          Preferences
        </legend>

        <label className="block text-sm font-medium text-gray-700">
          Travel style
          <input
            type="text"
            value={travelStyle}
            onChange={(e) => setTravelStyle(e.target.value)}
            className={inputClass}
          />
        </label>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-gray-700">
            Max walking minutes between stops
            <input
              type="number"
              min={0}
              value={maxWalkBetween}
              onChange={(e) => setMaxWalkBetween(e.target.value)}
              className={inputClass}
            />
          </label>

          <label className="block text-sm font-medium text-gray-700">
            Max total walking minutes per day
            <input
              type="number"
              min={0}
              value={maxWalkPerDay}
              onChange={(e) => setMaxWalkPerDay(e.target.value)}
              className={inputClass}
            />
          </label>
        </div>

        <label className="block text-sm font-medium text-gray-700">
          Interests
          <input
            type="text"
            value={interests}
            onChange={(e) => setInterests(e.target.value)}
            placeholder="food, temples, museums"
            className={inputClass}
          />
        </label>

        <label className="block text-sm font-medium text-gray-700">
          Hotel preferences
          <input
            type="text"
            value={hotelPreferences}
            onChange={(e) => setHotelPreferences(e.target.value)}
            placeholder="central, quiet"
            className={inputClass}
          />
        </label>

        <label className="block text-sm font-medium text-gray-700">
          Food preferences
          <input
            type="text"
            value={foodPreferences}
            onChange={(e) => setFoodPreferences(e.target.value)}
            placeholder="ramen, sushi"
            className={inputClass}
          />
        </label>

        <label className="block text-sm font-medium text-gray-700">
          Must-visit places
          <input
            type="text"
            value={mustVisitPlaces}
            onChange={(e) => setMustVisitPlaces(e.target.value)}
            placeholder="Senso-ji, Shibuya Crossing"
            className={inputClass}
          />
        </label>

        <label className="block text-sm font-medium text-gray-700">
          Avoid places
          <input
            type="text"
            value={avoidPlaces}
            onChange={(e) => setAvoidPlaces(e.target.value)}
            placeholder="crowded malls"
            className={inputClass}
          />
        </label>
      </fieldset>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Saving…" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="rounded-md border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
