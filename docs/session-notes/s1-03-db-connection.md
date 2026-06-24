# Session Note: Sprint 1 Task 03 — PostgreSQL Connection Layer

## Date
2026-06-24

## Goal
Connect the FastAPI backend to the Docker Compose PostgreSQL. Session setup +
`DATABASE_URL` env support. No Trip model/CRUD, no AI, no auth.

## Completed
- `backend/app/database.py`: SQLAlchemy engine, `SessionLocal`, `Base`, `get_session` dependency.
- `config.py` switched to `pydantic-settings`; loads `DATABASE_URL` from env/`.env`.
- Added `sqlalchemy`, `psycopg[binary]`, `pydantic-settings` to requirements.
- Fixed port conflict: native PostgreSQL 18 on host owns 5432; remapped container to host port **5433**.
- Verified host → container connection works.
- Committed: `533372a feat(backend): connect FastAPI to PostgreSQL` (5 files, branch `backend`, not pushed).

## Files Changed
- `backend/app/database.py` — NEW. Engine + session factory + `Base` + `get_session`.
- `backend/app/core/config.py` — `BaseSettings`, `DATABASE_URL` (default psycopg v3 URL, port 5433).
- `backend/requirements.txt` — added sqlalchemy 2.0.36, psycopg[binary] 3.2.3, pydantic-settings 2.7.0.
- `docker-compose.yml` — host port default `5432` → `5433`.
- `.env.example` — `POSTGRES_PORT=5433`, `DATABASE_URL` driver `postgresql+psycopg`, port 5433.

## Commands / Tests Run
```bash
docker compose up -d --force-recreate
docker compose ps        # mapped 0.0.0.0:5433->5432
docker exec guidegenie-postgres psql -U guidegenie -d guidegenie -c "SELECT 1;"
# host engine test:
python -c "from app.database import engine; from sqlalchemy import text; print(engine.connect().execute(text('SELECT 1')).scalar())"
```
Result:
- in-container auth: OK
- host `SELECT 1` → `1` (pass)

## Important Decisions
- Host port 5433, NOT 5432 — native PG18 service owns 5432; container-internal port stays 5432.
- `/health` left as pure liveness, decoupled from DB (no DB ping). Optional `GET /health/db` route declined for now.
- `docs/` directory left untracked / out of the Task 03 commit (separate concern).

## Known Issues / TODOs
- `docs/QUICK_REF.md` referenced in prompts but does NOT exist — create or stop referencing.
- Container healthcheck shows `health: starting` briefly; internal-only, does not affect connections.
- `.gitignore` ignores `.env*` but keeps `.env.example` (verified earlier).
- `README.md` is UTF-16 (from earlier note) — still not rewritten.
- Commit `533372a` not pushed to origin.

## Next Session Should Do
1. Sprint 1 Task 04: add the Trip SQLAlchemy model + table creation (e.g. `Base.metadata.create_all` or Alembic decision).
2. Then Trip CRUD endpoints (create/list/get) — still no auth, no AI.

## Suggested Next Prompt
```text
Read CLAUDE.md, SPRINTS.md, and docs/session-notes/s1-03-db-connection.md. Then continue with Sprint 1 Task 04: add the Trip model and table creation (no CRUD endpoints yet, no auth, no AI). Do not edit yet; first give me a short plan.
```
