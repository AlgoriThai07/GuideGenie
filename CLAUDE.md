# CLAUDE.md

Project context and working rules for Claude Code.

## Project: GuideGenie

GuideGenie is an end-to-end AI travel planning agent. The long-term vision: users
enter travel preferences and receive route-optimized itineraries built from real
places, restaurants, events, and rest stops, with Google Calendar sync.

This is a software engineering portfolio project. It is built incrementally in
small, well-scoped sprints. Do not build the whole app at once.

## Tech Stack

- **Frontend:** Next.js, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Python, Pydantic
- **Database:** PostgreSQL with SQLAlchemy or SQLModel
- **Local infra:** Docker Compose (PostgreSQL only, for now)

## Current Sprint

**Sprint 1 — Core full-stack trip creation foundation.**

Goal: a user can create a trip request, save it to PostgreSQL, view saved trips in
a dashboard, and open a trip detail page.

See `SPRINTS.md` for the full roadmap.

## Rules

- Work in small tasks. Do not implement future sprints early.
- Do not implement AI features.
- Do not implement LangGraph.
- Do not implement OpenAI / Gemini or any LLM provider.
- Do not implement Google APIs.
- Do not implement Google Calendar.
- Do not implement Redis.
- Do not implement authentication yet.
- Do not add complex features. Keep scope tight.
- Prefer clear, conventional, portfolio-quality code over clever code.
