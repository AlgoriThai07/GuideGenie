/**
 * Read-only day-by-day itinerary display.
 *
 * Renders the days/items returned by `GET /api/trips/{id}/itinerary`. No
 * editing, map rendering, or route visuals — those are later sprints.
 */

import type { ItineraryDay, ItineraryItem } from "@/types/itinerary";

const dayCardClass =
  "flex flex-col gap-4 rounded-md border border-gray-200 p-5";

const pillClass =
  "rounded-full bg-gray-100 px-2.5 py-0.5 text-xs font-medium capitalize text-gray-700";

/** Format a "type"/"priority"/"walking_intensity" enum value for display. */
function formatLabel(value: string): string {
  return value.replace(/_/g, " ");
}

/** Format an itinerary item's estimated cost, or omit when unset. */
function formatCost(cost: number | null): string | null {
  if (cost === null) return null;
  return cost.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function ItineraryItemRow({ item }: { item: ItineraryItem }) {
  const cost = formatCost(item.estimated_cost);

  return (
    <li className="flex flex-col gap-1.5 border-t border-gray-100 pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-semibold text-gray-900">
          {item.start_time}–{item.end_time} {item.title}
        </span>
        <span className={pillClass}>{formatLabel(item.type)}</span>
      </div>
      {item.location_name && (
        <p className="text-sm text-gray-600">{item.location_name}</p>
      )}
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
