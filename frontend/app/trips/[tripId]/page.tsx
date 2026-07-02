"use client";

/**
 * Trip detail page (`/trips/[tripId]`).
 *
 * Loads a single trip via `getTripById` and displays its overview,
 * preferences, and AI-generated itinerary (generate + auto-load on visit).
 * Includes disabled placeholder buttons for features that arrive in later
 * sprints (route optimization, calendar sync).
 */

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import {
  ApiError,
  deleteTrip,
  generateItinerary,
  getTripById,
  getTripItinerary,
} from "@/lib/api";
import Spinner from "@/components/Spinner";
import type { Trip } from "@/types/trip";
import type { ItineraryDay } from "@/types/itinerary";
import TripEditForm from "./TripEditForm";
import ItineraryView from "./ItineraryView";

/** Format a trip's date range, tolerating missing start/end dates. */
function formatDateRange(start: string | null, end: string | null): string {
  if (!start && !end) return "Dates TBD";
  if (start && end) return `${start} → ${end}`;
  return start ?? (end as string);
}

/** Format the budget (a JSON string from the backend) as USD, or a fallback. */
function formatBudget(budget: string | null): string {
  if (budget === null) return "No budget set";
  const n = Number(budget);
  if (Number.isNaN(n)) return "No budget set";
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Format a walking-minutes limit, or a fallback when unset. */
function formatWalkLimit(minutes: number | null): string {
  if (minutes === null) return "No limit";
  return `${minutes} min`;
}

/** A labeled row in a definition list. */
function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-gray-600">{label}</dt>
      <dd className="text-gray-900">{value}</dd>
    </div>
  );
}

/** Render a list of strings as pills, or "None" when empty. */
function TagList({ label, items }: { label: string; items: string[] }) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-gray-900">{label}</h3>
      {items.length === 0 ? (
        <p className="text-sm text-gray-500">None</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {items.map((item) => (
            <li
              key={item}
              className="rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium text-gray-700"
            >
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const cardClass = "flex flex-col gap-4 rounded-md border border-gray-200 p-5";

/** Buttons for features coming in later sprints — disabled, no handlers. */
const futureFeatures = [
  { label: "Optimize Route", sprint: "Sprint 4" },
  { label: "Sync to Google Calendar", sprint: "Sprint 9" },
];

export default function TripDetailPage() {
  const params = useParams<{ tripId: string }>();
  const router = useRouter();
  const tripId = Number(params.tripId);

  const [trip, setTrip] = useState<Trip | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const [itinerary, setItinerary] = useState<ItineraryDay[] | null>(null);
  const [itineraryLoading, setItineraryLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [itineraryError, setItineraryError] = useState<string | null>(null);

  async function handleGenerate() {
    setGenerating(true);
    setItineraryError(null);
    try {
      await generateItinerary(tripId);
      const days = await getTripItinerary(tripId);
      setItinerary(days);
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong while generating the itinerary. Please try again.";
      setItineraryError(message);
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete() {
    if (!trip) return;
    const confirmed = window.confirm(
      `Delete "${trip.title}"? This cannot be undone.`,
    );
    if (!confirmed) return;

    setDeleting(true);
    setActionError(null);
    try {
      await deleteTrip(trip.id);
      router.push("/dashboard");
    } catch (err) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Something went wrong while deleting the trip. Please try again.";
      setActionError(message);
      setDeleting(false);
    }
  }

  useEffect(() => {
    let active = true;

    if (Number.isNaN(tripId)) {
      setNotFound(true);
      setLoading(false);
      return;
    }

    getTripById(tripId)
      .then((data) => {
        if (active) setTrip(data);
      })
      .catch((err) => {
        if (!active) return;
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
          return;
        }
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong while loading this trip. Please try again.";
        setError(message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [tripId]);

  useEffect(() => {
    let active = true;

    if (Number.isNaN(tripId)) {
      setItineraryLoading(false);
      return;
    }

    getTripItinerary(tripId)
      .then((days) => {
        if (active) setItinerary(days);
      })
      .catch(() => {
        // Trip-not-found is already surfaced by the trip-fetch effect above;
        // any other itinerary-fetch failure just means nothing to show yet.
      })
      .finally(() => {
        if (active) setItineraryLoading(false);
      });

    return () => {
      active = false;
    };
  }, [tripId]);

  return (
    <section className="flex flex-col gap-8 py-4">
      <Link
        href="/dashboard"
        className="text-sm font-semibold text-gray-900 hover:text-gray-700"
      >
        ← Back to dashboard
      </Link>

      {loading && <Spinner label="Loading trip…" />}

      {!loading && notFound && (
        <div className="flex flex-col items-start gap-4 rounded-md border border-gray-200 p-8">
          <p className="text-gray-600">Trip not found.</p>
          <Link
            href="/dashboard"
            className="text-sm font-semibold text-gray-900 hover:text-gray-700"
          >
            Back to dashboard →
          </Link>
        </div>
      )}

      {!loading && !notFound && error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {!loading && !notFound && !error && trip && editing && (
        <>
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-gray-900">
              Edit trip
            </h1>
            <p className="mt-2 text-gray-600">
              Update your trip details and preferences. For list fields,
              separate values with commas.
            </p>
          </div>
          <TripEditForm
            trip={trip}
            onSaved={(updated) => {
              setTrip(updated);
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        </>
      )}

      {!loading && !notFound && !error && trip && !editing && (
        <>
          {/* Overview */}
          <div className="flex flex-col gap-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-gray-900">
                  {trip.title}
                </h1>
                <p className="text-gray-600">{trip.destination}</p>
              </div>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium capitalize text-gray-700">
                {trip.status}
              </span>
            </div>

            {actionError && (
              <div
                role="alert"
                className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
              >
                {actionError}
              </div>
            )}

            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => {
                  setActionError(null);
                  setEditing(true);
                }}
                disabled={deleting}
                className="rounded-md border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Edit
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleting}
                className="rounded-md border border-red-300 px-5 py-2.5 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {deleting ? <Spinner label="Deleting…" /> : "Delete"}
              </button>
            </div>
          </div>

          <div className={cardClass}>
            <h2 className="font-semibold text-gray-900">Overview</h2>
            <dl className="flex flex-col gap-1 text-sm">
              <DetailRow label="Destination" value={trip.destination} />
              <DetailRow
                label="Dates"
                value={formatDateRange(trip.start_date, trip.end_date)}
              />
              <DetailRow
                label="Travelers"
                value={`${trip.travelers} ${
                  trip.travelers === 1 ? "traveler" : "travelers"
                }`}
              />
              <DetailRow label="Budget" value={formatBudget(trip.budget)} />
              <DetailRow label="Status" value={trip.status} />
            </dl>
          </div>

          {/* Preferences */}
          <div className={cardClass}>
            <h2 className="font-semibold text-gray-900">Preferences</h2>

            {trip.preference === null ? (
              <p className="text-sm text-gray-500">No preferences set.</p>
            ) : (
              <div className="flex flex-col gap-5">
                <dl className="flex flex-col gap-1 text-sm">
                  <DetailRow
                    label="Travel style"
                    value={trip.preference.travel_style ?? "Not set"}
                  />
                  <DetailRow
                    label="Max walking between stops"
                    value={formatWalkLimit(
                      trip.preference.max_walking_minutes_between_stops,
                    )}
                  />
                  <DetailRow
                    label="Max total walking per day"
                    value={formatWalkLimit(
                      trip.preference.max_total_walking_minutes_per_day,
                    )}
                  />
                </dl>

                <TagList label="Interests" items={trip.preference.interests} />
                <TagList
                  label="Food preferences"
                  items={trip.preference.food_preferences}
                />
                <TagList
                  label="Hotel preferences"
                  items={trip.preference.hotel_preferences}
                />
                <TagList
                  label="Must-visit places"
                  items={trip.preference.must_visit_places}
                />
                <TagList
                  label="Avoid places"
                  items={trip.preference.avoid_places}
                />
              </div>
            )}
          </div>

          {/* Itinerary */}
          <div className={cardClass}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold text-gray-900">Itinerary</h2>
              <div className="flex flex-col items-end gap-1">
                <button
                  type="button"
                  onClick={handleGenerate}
                  disabled={generating}
                  className="rounded-md bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {generating ? (
                    <Spinner label="Generating…" light />
                  ) : itinerary && itinerary.length > 0 ? (
                    "Regenerate Itinerary"
                  ) : (
                    "Generate Itinerary"
                  )}
                </button>
                {generating && (
                  <p className="text-xs text-gray-500">
                    This can take up to 30 seconds…
                  </p>
                )}
              </div>
            </div>

            {itineraryError && (
              <div
                role="alert"
                className="flex flex-col items-start gap-2 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
              >
                <p>{itineraryError}</p>
                <button
                  type="button"
                  onClick={handleGenerate}
                  className="text-sm font-semibold text-red-800 underline hover:text-red-900"
                >
                  Retry
                </button>
              </div>
            )}

            {itineraryLoading && <Spinner label="Loading itinerary…" />}

            {!itineraryLoading && itinerary && itinerary.length > 0 && (
              <ItineraryView days={itinerary} />
            )}

            {!itineraryLoading &&
              !generating &&
              !itineraryError &&
              (!itinerary || itinerary.length === 0) && (
                <p className="text-sm text-gray-500">
                  No itinerary yet — click Generate Itinerary to create one.
                </p>
              )}
          </div>

          {/* Future features (later sprints) — disabled placeholders */}
          <div className={cardClass}>
            <div className="flex flex-col gap-1">
              <h2 className="font-semibold text-gray-900">Coming soon</h2>
              <p className="text-sm text-gray-500">
                These features arrive in later sprints and are not available yet.
              </p>
            </div>
            <div className="flex flex-wrap gap-3">
              {futureFeatures.map((feature) => (
                <button
                  key={feature.label}
                  type="button"
                  disabled
                  title={`Coming in ${feature.sprint}`}
                  className="cursor-not-allowed rounded-md border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-900 opacity-50"
                >
                  {feature.label}
                  <span className="ml-2 text-xs font-normal text-gray-500">
                    {feature.sprint}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
