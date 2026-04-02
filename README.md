<<<<<<< HEAD
# Infovision Prompt Validator - Complete Repo

This package is the expanded repository layout for the Prompt Validator MVP and phased rollout.

## What is inside
- Current FastAPI MVP backend and web UI
- Source-of-truth documents copied into the repo
- Complete repo structure for Day 1 to Day 5 rollout
- Placeholder folders for auth, MCP, Teams, and deployment
- BRD and architecture notes

## Delivery mapping
- Day 1: `app/`, `app/config/`, `app/services/`, `app/api/`
- Day 2: `docs/data_strategy/`, `app/db/`, `app/repositories/`
- Day 3: `app/auth/`, `app/integrations/oauth/`, `app/middleware/`
- Day 4: `app/integrations/mcp/`, `deploy/`
- Day 5: `app/integrations/teams/`, `docs/teams/`

## Source of truth docs
See `docs/source_of_truth/`.

## Run (local — MongoDB Atlas default)

1. Copy `.env.example` to `.env` and fill in Atlas credentials (see variables below). The app loads `.env` from the project root automatically. You can instead export variables in your shell.
2. Start the API:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## MongoDB Atlas (default backend)

1. Create a cluster in Atlas and a database user.
2. **Network access:** allow your IP (local) and `0.0.0.0/0` (or Vercel’s egress) if appropriate for your security model.
3. Provide either a full **SRV connection string** or the separate host/user/password variables (see `app/core/settings.py`).

Environment variables:

| Variable | Meaning |
|----------|---------|
| `DATABASE_BACKEND` | Default is `mongodb`. Set to `sqlite` for optional local file DB only. |
| `MONGODB_URI` | Full Atlas URI. If set, used as-is (highest priority). |
| `MONGODB_USER` | Atlas DB user (used with password + host if `MONGODB_URI` is unset). |
| `MONGODB_PASSWORD` | Atlas DB user password. |
| `MONGODB_CLUSTER_HOST` | Host only, e.g. `cluster0.xxxxx.mongodb.net` (no `mongodb+srv://`). |
| `MONGODB_APP_NAME` | Optional. `appName` query param from the Atlas connect dialog. |
| `MONGODB_DB_NAME` | Optional. Database name (default: `prompt_validator`). |

Example (PowerShell) with a single URI:

```powershell
$env:DATABASE_BACKEND = "mongodb"
$env:MONGODB_URI = "mongodb+srv://user:pass@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority"
$env:MONGODB_DB_NAME = "prompt_validator"
uvicorn app.main:app --reload
```

Example with split Atlas credentials (no URI):

```powershell
$env:MONGODB_USER = "myuser"
$env:MONGODB_PASSWORD = "secret"
$env:MONGODB_CLUSTER_HOST = "cluster0.xxxxx.mongodb.net"
$env:MONGODB_APP_NAME = "Cluster0"
uvicorn app.main:app --reload
```

## SQLite (optional)---No need to use this

Set `DATABASE_BACKEND=sqlite` to use the local file `prompt_validator.db` next to the project root. No Mongo variables are required in that mode.

## Verify backend + database

After starting `uvicorn`, open the web UI at `http://127.0.0.1:8000/` (same origin as the API).

- **`GET /api/v1/health`** — process is up (does not touch the database).
- **`GET /api/v1/health/db`** — pings MongoDB or runs `SELECT 1` on SQLite; confirms the active backend can read the database. Expect JSON with `"status": "ok"` and `"backend": "mongodb"` or `"sqlite"`.

Ensure Atlas credentials in `.env` are filled in before relying on the MongoDB default; empty `MONGODB_URI` and empty `MONGODB_USER` / `MONGODB_PASSWORD` / `MONGODB_CLUSTER_HOST` will prevent startup when `DATABASE_BACKEND=mongodb`.

## Deploy on Vercel
- Connect this repo and use the **Python / FastAPI** preset (see [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)).
- `pyproject.toml` declares `[project.scripts] app = "app.main:app"` so Vercel finds the ASGI app.
- Set **environment variables** in the project: at minimum `MONGODB_URI` (or `MONGODB_USER` + `MONGODB_PASSWORD` + `MONGODB_CLUSTER_HOST`) and `PROMPT_VALIDATOR_API_KEY` for protected routes. Default is already MongoDB; you do not need `DATABASE_BACKEND` unless switching to SQLite locally.
- Do not rely on SQLite on Vercel: the filesystem is ephemeral; use Atlas for production data.
- Optional: tune bundle size with `excludeFiles` in `vercel.json` (see [Python bundle limits](https://vercel.com/docs/functions/runtimes/python)).

## Extract Source-of-Truth DOCX
If your framework files are in `docs/source_of_truth/**`, run:

```bash
python scripts/extract_source_truth_docx.py
```

This generates:
- `app/config/source_of_truth_extracted.json` (raw extracted text)
- `app/config/persona_criteria_source_truth.json` (auto-generated Persona 0-4 runtime criteria from `Infovision_Prompt_Validator_v11.docx`)
- `app/config/prompt_guidelines_source_truth.json` (strict global prompt-guideline checks from provider guideline docs)

## Notes
Keep the backend engine as the single source of truth. Channel adapters must stay thin.

## Day 2-5 API Additions
- Auth + persona mapping:
  - `POST /api/v1/auth/resolve`
  - `POST /api/v1/auth/map-persona`
- MCP wrapper:
  - `POST /api/v1/mcp/validate`
- Teams bot adapter:
  - `POST /api/v1/teams/message`
- Data analytics:
  - `GET /api/v1/analytics/summary`

Protected endpoints require header: `x-api-key` (default `infovision-dev-key`, configurable with `PROMPT_VALIDATOR_API_KEY`).

## Teams Bot Bridge (Day 5)

The repository includes a Bot Framework bridge service under `teams_bot/` that receives Teams activities and forwards messages to the validator backend.

- Run locally:
  - `python -m teams_bot.app`
- Bot endpoint:
  - `POST /api/messages`
- Configuration docs:
  - `docs/teams/teams_bot_backend_setup.md`
  - `docs/teams/go_live_checklist.md`
- Teams app package template:
  - `teams_app_manifest/`
- Local container orchestration:
  - `deploy/docker-compose.yml`
=======
# Prompt_eValidator_Code
Prompt Validator MVP: FastAPI backend for persona-based prompt scoring, auto-improvement, analytics, and Teams integration.
>>>>>>> a0bd1cf3db60bd97441bd5e1ba657d8ab5e384b3
