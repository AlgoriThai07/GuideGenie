/**
 * Frontend API client for the GuideGenie backend trip CRUD endpoints.
 *
 * The backend base URL is read from `NEXT_PUBLIC_API_URL` (e.g.
 * "http://localhost:8000"). Trip routes live under `/api/trips`.
 */

import type {
  CreateTripInput,
  Trip,
  UpdateTripInput,
} from "@/types/trip";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const TRIPS_PATH = "/api/trips";

/** Error thrown when the backend responds with a non-2xx status. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/**
 * Issue a JSON request against the backend and parse the response.
 *
 * Throws `ApiError` on non-2xx responses. Returns `undefined` for empty
 * bodies (e.g. 204 No Content).
 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await readErrorMessage(res));
  }

  // 204 and other empty bodies have no JSON to parse.
  if (res.status === 204 || res.headers.get("content-length") === "0") {
    return undefined as T;
  }

  return (await res.json()) as T;
}

/** Best-effort extraction of a human-readable error from a failed response. */
async function readErrorMessage(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

/** Create a new trip. POST /api/trips */
export function createTrip(input: CreateTripInput): Promise<Trip> {
  return request<Trip>(TRIPS_PATH, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** List all trips, newest first. GET /api/trips */
export function getTrips(): Promise<Trip[]> {
  return request<Trip[]>(TRIPS_PATH);
}

/** Fetch a single trip by id. GET /api/trips/{id} */
export function getTripById(id: number): Promise<Trip> {
  return request<Trip>(`${TRIPS_PATH}/${id}`);
}

/** Partially update a trip. PUT /api/trips/{id} */
export function updateTrip(
  id: number,
  input: UpdateTripInput,
): Promise<Trip> {
  return request<Trip>(`${TRIPS_PATH}/${id}`, {
    method: "PUT",
    body: JSON.stringify(input),
  });
}

/** Delete a trip. DELETE /api/trips/{id} */
export function deleteTrip(id: number): Promise<void> {
  return request<void>(`${TRIPS_PATH}/${id}`, { method: "DELETE" });
}
