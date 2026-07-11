/**
 * Read-only day-by-day itinerary display.
 *
 * Renders the days/items returned by `GET /api/trips/{id}/itinerary`. No
 * editing, map rendering, or route visuals — those are later sprints.
 */

import type { ItineraryDay, ItineraryItem, Place } from "@/types/itinerary";

const dayCardClass =
  "flex flex-col gap-4 rounded-md border border-gray-200 p-5";

const pillClass =
  "rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium capitalize text-gray-700";

const verifiedBadgeClass =
  "rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium normal-case text-gray-700";

/** Format a "type"/"priority"/"walking_intensity" enum value for display. */
function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

/** Format an itinerary item's estimated cost (a JSON string), or omit when unset. */
function formatCost(cost: string | null): string | null {
  if (cost === null) return null;
  const n = Number(cost);
  if (Number.isNaN(n)) return null;
  return n.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Build a Google Maps search link that opens directly on the resolved place. */
function buildMapsSearchUrl(place: Place): string {
  const params = new URLSearchParams({
    api: "1",
    query: place.name,
    query_place_id: place.google_place_id,
  });
  return `https://www.google.com/maps/search/?${params.toString()}`;
}

/** Location details for an item: real resolved place, or the LLM's raw name. */
function ItemLocation({ item }: { item: ItineraryItem }) {
  if (!item.place) {
    return item.location_name ? (
      <p className="text-sm text-gray-600">{item.location_name}</p>
    ) : null;
  }

  const { place } = item;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm text-gray-600">{place.name}</p>
        <span className={verifiedBadgeClass}>✓ Verified place</span>
      </div>
      {place.address && (
        <p className="text-sm text-gray-500">{place.address}</p>
      )}
      <div className="flex flex-wrap items-center gap-3">
        {place.rating != null && (
          <span className="text-sm text-gray-600">
            ★ {place.rating.toFixed(1)}
          </span>
        )}
        <a
          href={buildMapsSearchUrl(place)}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm font-semibold text-gray-900 hover:text-gray-700"
        >
          View on Google Maps
        </a>
      </div>
    </div>
  );
}

/** Cost pill text: prefer a web-search-verified price over the LLM's guess. */
function formatCostLabel(item: ItineraryItem): string | null {
  const verified = formatCost(item.verified_cost);
  if (verified) return `✓ ${verified}`;

  const estimated = formatCost(item.estimated_cost);
  return estimated ? `~${estimated} (est.)` : null;
}

function ItineraryItemRow({ item }: { item: ItineraryItem }) {
  const cost = formatCostLabel(item);

  return (
    <li className="flex flex-col gap-1.5 border-t border-gray-100 pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-gray-900">
          {item.start_time}–{item.end_time} {item.title}
        </span>
        <span className={pillClass}>{formatLabel(item.type)}</span>
      </div>
      <ItemLocation item={item} />
      {item.description && (
        <p className="text-sm text-gray-600">{item.description}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {cost && <span className={pillClass}>{cost}</span>}
        {item.walking_intensity && (
          <span className={pillClass}>
            {formatLabel(item.walking_intensity)} walking
          </span>
        )}
        <span className={pillClass}>{formatLabel(item.priority)}</span>
      </div>
    </li>
  );
}

function ItineraryDayCard({ day }: { day: ItineraryDay }) {
  return (
    <div className={dayCardClass}>
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold text-gray-900">
            Day {day.day_number}
            {day.theme ? `: ${day.theme}` : ""}
          </h3>
          {day.date && <span className="text-sm text-gray-500">{day.date}</span>}
        </div>
        {day.summary && <p className="text-sm text-gray-600">{day.summary}</p>}
      </div>
      <ul className="flex flex-col gap-3">
        {day.items.map((item) => (
          <ItineraryItemRow key={item.id} item={item} />
        ))}
      </ul>
    </div>
  );
}

export default function ItineraryView({ days }: { days: ItineraryDay[] }) {
  if (days.length === 0) return null;

  return (
    <div className="flex flex-col gap-4">
      {days.map((day) => (
        <ItineraryDayCard key={day.id} day={day} />
      ))}
    </div>
  );
}
