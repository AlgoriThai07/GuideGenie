# GuideGenie — Quick Reference

Stable cheat sheet for working sessions. For per-task handoffs see
`docs/session-notes/`. For scope/rules see `CLAUDE.md` and `SPRINTS.md`.

## Project
AI travel planning agent (portfolio project, built in small sprints).
**Current:** Sprint 1 — trip creation foundation (create → Postgres → dashboard → detail).
No AI / auth / Google / Redis yet (see CLAUDE.md rules).

## Stack
- Backend: FastAPI, Python, Pydantic, SQLAlchemy 2, psycopg v3
- Frontend: Next.js 15, TypeScript, Tailwind v4, App Router (`frontend/`)
- DB: PostgreSQL 16 via Docker Compose
- Config: pydantic-settings

## Layout
```
backend/app/main.py          FastAPI app + GET /health
backend/app/core/config.py   Settings (pydantic-settings), DATABASE_URL
backend/app/database.py      engine, SessionLocal, Base, get_session
docker-compose.yml           Postgres service
.env.example                 copy to .env
```

## Ports
- Postgres host port: **5433** (container-internal 5432). 5433 avoids a native
  PostgreSQL 18 install that owns host 5432.
- Backend dev server: 8001

## Run

Database:
```bash
docker compose up -d            # start Postgres
docker compose ps               # expect 0.0.0.0:5433->5432
docker compose down             # stop (add -v to wipe data volume)
```

Backend (run from `backend/`):
```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1      # PowerShell
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001  # http://localhost:8001
```

Frontend (run from `frontend/`):
```bash
cd frontend
npm install                     # first time only
npm run dev                     # http://localhost:3000
```

## Test / Verify
```bash
# liveness
curl http://localhost:8001/health        # {"status":"ok","service":"guidegenie-backend"}

# DB connection (from backend/, venv active)
python -c "from app.database import engine; from sqlalchemy import text; print(engine.connect().execute(text('SELECT 1')).scalar())"   # -> 1

# DB auth inside container
docker exec guidegenie-postgres psql -U guidegenie -d guidegenie -c "SELECT 1;"
```

## DB Connection (current default)
```
postgresql+psycopg://guidegenie:guidegenie@localhost:5433/guidegenie
```
Override via `DATABASE_URL` in `backend/.env`.

## Gotchas
- Run `uvicorn` from `backend/` or `app` imports fail.
- Native PG18 on 5432 intercepts connections — always use 5433 for the container.
- `git add` paths are relative to cwd (often `backend/`); use `../` for repo-root files.
- `.gitignore` ignores `.env*` but keeps `.env.example`.
- `README.md` is UTF-16 (legacy Windows write) — not standard UTF-8.

## Conventions
- Conventional Commits (`feat`, `fix`, `docs`, `chore`, ...).
- Small scoped tasks; one sprint task per commit.
- End each task with a `docs/session-notes/sN-NN-*.md` handoff note.
