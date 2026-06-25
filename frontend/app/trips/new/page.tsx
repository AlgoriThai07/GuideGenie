"use client";

/**
 * Create Trip form page (`/trips/new`).
 *
 * Collects trip details and preferences, converts comma-separated list fields
 * into arrays, and POSTs via `createTrip`. On success it redirects to the new
 * trip's detail page.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, createTrip } from "@/lib/api";
import type { CreateTripInput, TripPreferenceInput } from "@/types/trip";

/** Split a comma-separated string into a trimmed, non-empty string array. */
function toList(csv: string): string[] {
  return csv
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
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

export default function NewTripPage() {
  const router = useRouter();

  // Trip fields.
  const [title, setTitle] = useState("");
  const [destination, setDestination] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [travelers, setTravelers] = useState("1");
  const [budget, setBudget] = useState("");

  // Preference fields.
  const [travelStyle, setTravelStyle] = useState("");
  const [maxWalkBetween, setMaxWalkBetween] = useState("");
  const [maxWalkPerDay, setMaxWalkPerDay] = useState("");
  const [interests, setInterests] = useState("");
  const [hotelPreferences, setHotelPreferences] = useState("");
  const [foodPreferences, setFoodPreferences] = useState("");
  const [mustVisitPlaces, setMustVisitPlaces] = useState("");
  const [avoidPlaces, setAvoidPlaces] = useState("");

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

    const input: CreateTripInput = {
      title: title.trim(),
      destination: destination.trim(),
      start_date: startDate || null,
      end_date: endDate || null,
      travelers: toNumberOrNull(travelers) ?? 1,
      budget: toNumberOrNull(budget),
      preference,
    };

    try {
      const trip = await createTrip(input);
      router.push(`/trips/${trip.id}`);
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
    <section className="flex flex-col gap-8 py-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Create a trip
        </h1>
        <p className="mt-2 text-gray-600">
          Enter your trip details and preferences. For list fields, separate
          values with commas.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-8">
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
              placeholder="Tokyo Spring Trip"
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
              placeholder="Tokyo, Japan"
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
                placeholder="3000"
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
              placeholder="relaxed"
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
                placeholder="20"
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
                placeholder="120"
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

        <div>
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {loading ? "Saving…" : "Create trip"}
          </button>
        </div>
      </form>
    </section>
  );
}
