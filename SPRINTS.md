# GuideGenie Sprint Plan

## Sprint 1: Core Full-Stack Trip Creation

Goal:
User can create, save, view, update, and delete trip requests.

Deliverables:
- Next.js frontend
- FastAPI backend
- PostgreSQL database
- Trip CRUD APIs
- Create trip form
- Dashboard page
- Trip detail page

Definition of Done:
- User can create a trip from the frontend.
- Trip is saved to PostgreSQL.
- Dashboard displays saved trips.
- Trip detail page displays preferences.
- API endpoints work in FastAPI Swagger UI.

## Sprint 2: Basic AI Itinerary Generation

Goal:
Generate a structured day-by-day itinerary from trip preferences.

Do not start until Sprint 1 is done.

## Sprint 3: Real Place / Restaurant Search

Goal:
Use real APIs or mock APIs to ground recommendations.

## Sprint 4: Route Optimization

Goal:
Order itinerary stops logically and calculate walking time.

## Sprint 5: Rest Stop Insertion

Goal:
Insert cafes/convenience stores/rest areas if walking is too long.

## Sprint 6: Events / Festivals Discovery

Goal:
Find local events during trip dates.

## Sprint 7: Constraint Validation

Goal:
Validate walking, budget, opening hours, and time feasibility.

## Sprint 8: Editable Itinerary + Approval

Goal:
Allow user edits and final approval before external actions.

## Sprint 9: Google Calendar Sync

Goal:
Sync approved itinerary items to Google Calendar.

## Sprint 10: Redis + Background Jobs

Goal:
Add caching and async processing.

## Sprint 11: Observability Dashboard

Goal:
Show agent steps, tool calls, latency, and cache hits.

## Sprint 12: Cloud + CI/CD + Polish

Goal:
Deploy and prepare project for resume/demo.