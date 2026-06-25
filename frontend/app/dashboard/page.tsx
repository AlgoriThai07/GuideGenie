"use client";

/**
 * Dashboard page (`/dashboard`).
 *
 * Loads all saved trips via `getTrips` and lists them as cards with their key
 * details. Provides links to each trip's detail page and to the create form.
 */

import { useEffect, useState } from "react";
import Link from "next/link";

import { ApiError, getTrips } from "@/lib/api";
import Spinner from "@/components/Spinner";
import type { Trip } from "@/types/trip";

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

const primaryButtonClass =
  "rounded-md bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white " +
  "hover:bg-gray-700";

function TripCard({ trip }: { trip: Trip }) {
  return (
    <article className="flex flex-col gap-3 rounded-md border border-gray-200 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-gray-900">{trip.title}</h2>
          <p className="text-sm text-gray-600">{trip.destination}</p>
        </div>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium capitalize text-gray-700">
          {trip.status}
        </span>
      </div>

      <dl className="flex flex-col gap-1 text-sm text-gray-600">
        <div className="flex justify-between gap-3">
          <dt>Dates</dt>
          <dd className="text-gray-900">
            {formatDateRange(trip.start_date, trip.end_date)}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Travelers</dt>
          <dd className="text-gray-900">
            {trip.travelers} {trip.travelers === 1 ? "traveler" : "travelers"}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt>Budget</dt>
          <dd className="text-gray-900">{formatBudget(trip.budget)}</dd>
        </div>
      </dl>

      <Link
        href={`/trips/${trip.id}`}
        className="mt-1 text-sm font-semibold text-gray-900 hover:text-gray-700"
      >
        View Trip →
      </Link>
    </article>
  );
}

export default function DashboardPage() {
  const [trips, setTrips] = useState<Trip[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    getTrips()
      .then((data) => {
        if (active) setTrips(data);
      })
      .catch((err) => {
        if (!active) return;
        const message =
          err instanceof ApiError
            ? err.message
            : "Something went wrong while loading trips. Please try again.";
        setError(message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="flex flex-col gap-8 py-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          Your trips
        </h1>
        <Link href="/trips/new" className={primaryButtonClass}>
          Create New Trip
        </Link>
      </div>

      {loading && <Spinner label="Loading trips…" />}

      {!loading && error && (
        <div
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800"
        >
          {error}
        </div>
      )}

      {!loading && !error && trips.length === 0 && (
        <div className="flex flex-col items-start gap-4 rounded-md border border-gray-200 p-8">
          <p className="text-gray-600">No trips yet.</p>
          <Link href="/trips/new" className={primaryButtonClass}>
            Create New Trip
          </Link>
        </div>
      )}

      {!loading && !error && trips.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {trips.map((trip) => (
            <TripCard key={trip.id} trip={trip} />
          ))}
        </div>
      )}
    </section>
  );
}
