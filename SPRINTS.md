# Sprint Roadmap — GuideGenie

Incremental build plan. Only the current sprint is active. Future sprints are
placeholders and may change.

---

## Sprint 1 — Trip Creation Foundation  **← CURRENT**

Core full-stack trip creation foundation.

**Goal:** a user can create a trip request, save it to PostgreSQL, view saved
trips in a dashboard, and open a trip detail page.

Scope:
- Project planning + setup files (this task)
- PostgreSQL via Docker Compose
- FastAPI backend with a Trip model and CRUD endpoints
- Next.js frontend: trip creation form, dashboard list, trip detail page
- No auth, no AI, no external APIs

---

## Sprint 2 — Trip Preferences & Validation (planned)

- Richer trip preference fields (dates, budget, interests, pace)
- Input validation and error handling
- Improved UI/UX

## Sprint 3 — Places & Data Sources (planned)

- Integrate real place/restaurant/event data sources
- Store and display candidate locations per trip

## Sprint 4 — Route Optimization (planned)

- Build route-optimized itineraries from selected places
- Rest stops and time-aware ordering

## Sprint 5 — AI Itinerary Generation (planned)

- AI agent to generate itineraries from preferences
- Provider/orchestration decisions deferred to this sprint

## Sprint 6 — Calendar Sync & Auth (planned)

- Authentication
- Google Calendar sync
