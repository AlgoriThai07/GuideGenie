# GuideGenie Project Context

GuideGenie is an end-to-end AI travel planning agent.

## Product Goal

Users enter a natural-language travel request or structured trip preferences. GuideGenie creates a personalized day-by-day itinerary using real places, restaurants, hotels, events, and route data. The system should optimize routes to reduce walking, insert rest stops when walking segments are too long, validate constraints, and allow approved itineraries to sync to Google Calendar.

## Tech Stack

Frontend:
- Next.js
- TypeScript
- Tailwind CSS
- App Router

Backend:
- FastAPI
- Python
- PostgreSQL
- SQLAlchemy or SQLModel
- Pydantic
- Alembic

Future AI/Infra:
- LangGraph for agent workflow
- OpenAI or Gemini for LLM
- Redis for caching and background jobs
- Google Places / Routes APIs
- Ticketmaster Discovery API for events
- Google Calendar API
- Docker
- AWS ECS / RDS / ElastiCache
- GitHub Actions CI/CD

## Current Sprint

Sprint 1: Core full-stack trip creation.

Do not build AI features yet.

Sprint 1 goal:
A user can create a trip request, save it to PostgreSQL, view saved trips in the dashboard, and open a trip detail page.

## Sprint 1 Features

Backend:
- FastAPI app
- PostgreSQL connection
- Trip model
- TripPreference model
- CRUD endpoints for trips

Frontend:
- Landing page
- Dashboard page
- New trip form
- Trip detail page
- API helper functions

Database:
- users
- trips
- trip_preferences

## Important Rules

- Keep code clean and modular.
- Do not add LangGraph, OpenAI, Google APIs, Redis, or Calendar sync in Sprint 1.
- Use simple fake user_id for now.
- Prefer working full-stack functionality over overengineering.
- Keep files organized.
- Add comments only where helpful.
- Update README when major setup steps change.