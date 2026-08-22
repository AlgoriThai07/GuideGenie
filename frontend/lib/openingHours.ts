/**
 * Opening-hours helpers mirroring the backend's
 * `app/services/opening_hours.py` (Places API (New) v1 `regularOpeningHours`
 * shape). Used to decide whether an itinerary item's scheduled time falls
 * outside a venue's known opening hours, for the "may be closed" badge.
 */

export interface OpeningHoursPoint {
  day: number;
  hour?: number;
  minute?: number;
}

export interface OpeningHoursPeriod {
  open?: OpeningHoursPoint;
  close?: OpeningHoursPoint;
}

export interface OpeningHours {
  openNow?: boolean;
  periods?: OpeningHoursPeriod[];
  weekdayDescriptions?: string[];
}

const WEEK_MINUTES = 7 * 24 * 60;

function periodOpenMinute(period: OpeningHoursPeriod): number | null {
  const open = period.open;
  if (!open || typeof open.day !== "number") return null;
  return open.day * 1440 + (open.hour ?? 0) * 60 + (open.minute ?? 0);
}

function periodCloseMinute(period: OpeningHoursPeriod, openMinute: number): number | null {
  const close = period.close;
  if (!close) return null; // no close point -> 24/7 place
  const closeMinute = (close.day ?? 0) * 1440 + (close.hour ?? 0) * 60 + (close.minute ?? 0);
  return closeMinute <= openMinute ? closeMinute + WEEK_MINUTES : closeMinute;
}

/**
 * `true`/`false` when hours are known, `null` when unknown or malformed.
 * `weekday` uses the Google convention (0=Sunday..6=Saturday) — same as
 * JS `Date.getDay()`, so no conversion is needed for a local `Date`.
 */
export function isOpenAt(
  hours: OpeningHours | null | undefined,
  weekday: number,
  minuteOfDay: number,
): boolean | null {
  try {
    if (!hours || !Array.isArray(hours.periods) || hours.periods.length === 0) {
      return null;
    }
    const t = weekday * 1440 + minuteOfDay;

    for (const period of hours.periods) {
      const openMinute = periodOpenMinute(period);
      if (openMinute === null) continue;
      const closeMinute = periodCloseMinute(period, openMinute);
      if (closeMinute === null) return true;
      if (
        (openMinute <= t && t < closeMinute) ||
        (openMinute <= t + WEEK_MINUTES && t + WEEK_MINUTES < closeMinute)
      ) {
        return true;
      }
    }
    return false;
  } catch {
    return null;
  }
}

/** Parse an "HH:MM" clock string into minutes after midnight, or `null`. */
export function parseClock(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(value.trim());
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (Number.isNaN(hours) || Number.isNaN(minutes)) return null;
  return hours * 60 + minutes;
}

/**
 * Google weekday (0=Sunday) for a "YYYY-MM-DD" date string. Parses via the
 * local-time `Date(year, monthIndex, day)` constructor rather than
 * `new Date(iso)`, which parses as UTC midnight and can land on the wrong
 * calendar day once shifted to the viewer's local timezone.
 */
export function googleWeekdayFromDateString(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value.trim());
  if (!match) return null;
  const [, year, month, day] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  if (Number.isNaN(date.getTime())) return null;
  return date.getDay();
}

/** The `weekdayDescriptions` line for `weekday` (0=Sunday), or `null`. */
export function hoursLineFor(
  hours: OpeningHours | null | undefined,
  weekday: number,
): string | null {
  const lines = hours?.weekdayDescriptions;
  if (!Array.isArray(lines) || lines.length !== 7) return null;
  // weekdayDescriptions is Monday-first; weekday is Sunday-first (0=Sunday).
  return lines[(weekday + 6) % 7] ?? null;
}
