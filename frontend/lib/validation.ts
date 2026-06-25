/**
 * Client-side validation for the trip create/edit forms.
 *
 * The backend (Pydantic) is the source of truth, but validating here gives
 * fast, friendly feedback before a request is made. Returns the first error
 * message found, or `null` when the input is valid.
 */

export interface TripFormValues {
  title: string;
  destination: string;
  startDate: string;
  endDate: string;
  travelers: string;
  budget: string;
  maxWalkBetween: string;
  maxWalkPerDay: string;
}

/** Validate raw form field values. Returns an error message or `null`. */
export function validateTripForm(values: TripFormValues): string | null {
  if (values.title.trim() === "") {
    return "Title is required.";
  }
  if (values.destination.trim() === "") {
    return "Destination is required.";
  }

  if (
    values.startDate &&
    values.endDate &&
    values.endDate < values.startDate
  ) {
    return "End date must be on or after the start date.";
  }

  const travelers = Number(values.travelers.trim());
  if (
    values.travelers.trim() !== "" &&
    (!Number.isInteger(travelers) || travelers < 1)
  ) {
    return "Travelers must be a whole number of 1 or more.";
  }

  if (!isBlankOrNonNegativeNumber(values.budget)) {
    return "Budget must be a number of 0 or more.";
  }
  if (!isBlankOrNonNegativeNumber(values.maxWalkBetween)) {
    return "Max walking minutes between stops must be 0 or more.";
  }
  if (!isBlankOrNonNegativeNumber(values.maxWalkPerDay)) {
    return "Max total walking minutes per day must be 0 or more.";
  }

  return null;
}

/** True when blank, or a valid number >= 0. */
function isBlankOrNonNegativeNumber(value: string): boolean {
  const trimmed = value.trim();
  if (trimmed === "") return true;
  const n = Number(trimmed);
  return !Number.isNaN(n) && n >= 0;
}
