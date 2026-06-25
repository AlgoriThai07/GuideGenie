# Session Note: Sprint 1 Task 04 — Database Models & Schemas

## Date
2026-06-24

## Goal
Add SQLAlchemy models (User, Trip, TripPreference) and matching Pydantic
schemas. Fake default user, no auth, no CRUD endpoints, no AI, no external APIs.

## Completed
- User, Trip, TripPreference ORM models (SQLAlchemy 2.0 `Mapped`/`mapped_column`).
- Pydantic schemas: Create / Update / Read for Trip + TripPreference, plus User.
- `init_db.py`: `create_all` table creation + idempotent default-user seed.
- Tables created live against Docker Postgres; default user (id=1) seeded.

## Files Changed
- `backend/app/models/__init__.py` — NEW. Re-exports models (populates `Base.metadata`).
- `backend/app/models/user.py` — NEW. `User`, `DEFAULT_USER_ID = 1`.
- `backend/app/models/trip.py` — NEW. `Trip`, `TripPreference`, `TripStatus` enum.
- `backend/app/schemas/__init__.py` — NEW. Re-exports schemas.
- `backend/app/schemas/user.py` — NEW. `UserCreate`, `UserRead`.
- `backend/app/schemas/trip.py` — NEW. `Trip*` + `TripPreference*` schemas.
- `backend/app/init_db.py` — NEW. `create_tables()`, `seed_default_user()`, `main()`.
- `backend/requirements.txt` — added `email-validator==2.2.0` (for `EmailStr`).

## Commands / Tests Run
```bash
cd backend
./.venv/Scripts/python.exe -m pip install email-validator==2.2.0 -q
./.venv/Scripts/python.exe -c "import app.models, app.schemas; from app.schemas import TripCreate; print(TripCreate(title='t', destination='Paris').model_dump())"
./.venv/Scripts/python.exe -m app.init_db
docker exec guidegenie-postgres psql -U guidegenie -d guidegenie -c "\dt" -c "SELECT id,email,display_name FROM users;"
```
Result:
- import OK; schema validates.
- `Tables created and default user seeded.`
- `\dt` → trip_preferences, trips, users. users row: 1 / default@guidegenie.local / Default User. PASS.

## Important Decisions
- Sprint 1 uses `Base.metadata.create_all` (in `app/init_db.py`), NOT Alembic — deferred.
- All trips owned by seeded default user (`DEFAULT_USER_ID = 1`) until auth sprint.
- Trip↔TripPreference is one-to-one (unique `trip_id` FK, cascade delete).
- List preference fields stored as JSON arrays (portable, readable).
- `budget` = `Numeric(10,2)`; `status` = `TripStatus` enum (draft/planned/completed/archived).
- Schema convention: `*Base` / `*Create` / `*Update` (all optional) / `*Read` (`from_attributes`).

## Known Issues / TODOs
- `create_all` does NOT alter existing tables on model change — drop/recreate or adopt Alembic later.
- No CRUD endpoints yet.
- Commit not made yet for Task 04 (branch `backend`, not pushed).

## Next Session Should Do
1. Sprint 1 Task 05: Trip CRUD endpoints (create / list / get / update) using `get_session`. No auth, no AI.
2. Wire trips to `DEFAULT_USER_ID`; accept inline `preference` on create.

## Suggested Next Prompt
```text
Read CLAUDE.md, docs/QUICK_REF.md, and docs/session-notes/s1-04-models.md. Then continue with: Sprint 1 Task 05 — Trip CRUD endpoints (create/list/get/update), no auth, no AI. Do not edit yet; first give me a short plan.
```
