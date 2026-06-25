import Link from "next/link";

export default function HomePage() {
  return (
    <section className="flex flex-col items-start gap-6 py-12">
      <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
        Plan smarter trips with GuideGenie
      </h1>
      <p className="max-w-2xl text-lg text-gray-600">
        Enter your travel preferences and get route-optimized itineraries built
        from real places, restaurants, events, and rest stops.
      </p>
      <div className="flex flex-wrap gap-4">
        <Link
          href="/trips/new"
          className="rounded-md bg-gray-900 px-5 py-2.5 text-sm font-semibold text-white hover:bg-gray-700"
        >
          Create a trip
        </Link>
        <Link
          href="/dashboard"
          className="rounded-md border border-gray-300 px-5 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-50"
        >
          View dashboard
        </Link>
      </div>
    </section>
  );
}
