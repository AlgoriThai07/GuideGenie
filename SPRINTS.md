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

### Goal

Generate a structured day-by-day itinerary from an existing trip request.

Sprint 2 should turn GuideGenie from a basic full-stack CRUD app into an AI-powered itinerary generator.

The user should be able to:

1. Create a trip using the Sprint 1 form.
2. Open the trip detail page.
3. Click **Generate Itinerary**.
4. Wait while the backend calls the LLM.
5. See a structured day-by-day itinerary saved and displayed in the app.

Definition of Done

Sprint 2 is complete when:

User can create a trip.
User can open trip detail page.
User can click Generate Itinerary.
Backend creates an agent_run.
Backend logs agent_steps.
LLM returns structured JSON.
Backend validates the JSON.
Itinerary is saved to PostgreSQL.
Frontend displays the itinerary grouped by day.
Failed LLM calls show a clean error.
README explains Sprint 2 setup and demo steps.

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