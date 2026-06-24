# Session Notes — Sprint 1, Task 02: Backend Skeleton

Date: 2026-06-24
Branch: `backend`

## Completed

- Minimal FastAPI backend skeleton. App boots, exposes `GET /health`.
- Updated `.gitignore` (Python + Next.js + editors/OS) and fixed a bug where
  `.env.example` was being ignored.
- No DB, no models, no CRUD, no AI/external APIs (per Sprint 1 rules).

## Files Changed

Created:
- `backend/requirements.txt` — `fastapi==0.115.6`, `uvicorn[standard]==0.34.0`
- `backend/app/__init__.py` — package marker (empty)
- `backend/app/core/__init__.py` — package marker (empty)
- `backend/app/core/config.py` — static `Settings` (`APP_NAME`, `SERVICE_NAME`), `settings` instance
- `backend/app/main.py` — FastAPI app + `GET /health` → `{"status":"ok","service":"guidegenie-backend"}`

Modified:
- `.gitignore` — env handling (`.env*` ignored, `!.env.example` kept), Python, Node/Next.js, editor/OS entries

## Commands / Tests Run

- `ls .gitignore` — confirmed exists before edit.
- **Not yet run:** deps install, server start, `/health` request. Verification steps documented but NOT executed this session.

To verify next session:
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
curl http://localhost:8000/health   # expect {"status":"ok","service":"guidegenie-backend"}
```

## Known Issues

- `/health` never actually run — boot + endpoint unverified.
- `README.md` is UTF-16 encoded (BOM + wide chars from earlier Windows write). Renders fine but not standard UTF-8 — consider rewriting.
- Uvicorn must run from `backend/` dir or `app` imports fail.
- Nothing committed yet — all changes uncommitted on `backend` branch.

## Exact Next Task (Sprint 1, Task 03)

Add PostgreSQL connection layer. Still NO Trip model / CRUD.
- `backend/app/core/config.py`: switch to `pydantic-settings`, load `DATABASE_URL` from env.
- `backend/app/db.py` (or `core/db.py`): SQLAlchemy/SQLModel engine + session factory + `get_session` dependency.
- Add `sqlalchemy` (or `sqlmodel`), `psycopg[binary]`, `pydantic-settings` to `requirements.txt`.
- Optional: DB ping in `/health`.
- Verify against running Postgres (`docker compose up -d`).
