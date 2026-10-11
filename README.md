# ArchPilot

Evidence-driven multi-agent architecture decision engine for local or private cloud compute.

**Demo:** see [DEMO.md](DEMO.md) for the one-command local startup and presentation walkthrough.

## System

- Next.js 16 frontend, deployable to Vercel
- FastAPI backend
- PydanticAI agents
- Local Bonsai 2 27B through either llama.cpp/OpenAI-compatible API or Ollama
- SearXNG for free web search
- PostgreSQL for saved queries, classified requirements, and complete design history
- Mermaid for deterministic architecture diagrams

## Agent pipeline

1. Requirements agent extracts constraints and asks only material clarifying questions.
2. Research planner creates focused search queries.
3. Python executes those queries through SearXNG.
4. Evaluation agent compares established and emerging tools against evidence.
5. Architecture agent designs for cost-effective, balanced, or high-performance mode.
6. Critic agent challenges the design; one revision pass is allowed.
7. Python converts the validated architecture JSON into Mermaid.

The architect and critic also separate six responsibility planes and audit every
component for acknowledged-data loss. Messaging designs require explicit ordering,
durability, offline sync, idempotency, ACK, routing, failover, client E2EE and direct
media upload contracts. See [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) for the
approval rules, saved audit details and regression checks.

Revisions preserve unchanged design content and generate only the needed edits.
See [PERFORMANCE.md](PERFORMANCE.md) for timing logs, quality safeguards and a
repeatable benchmark against a saved request.

## 1. Start infrastructure

```powershell
Set-Location C:\path\to\archpilot
docker compose up -d --wait
```

This starts Docker PostgreSQL on `127.0.0.1:5433` (container port `5432`) and
SearXNG on `8081`. Port `5433` keeps Docker separate from a Windows PostgreSQL
service on `5432`. PostgreSQL is only published on the loopback interface.
The Compose health check authenticates over TCP and runs `SELECT 1`.

## 2. Start your local model

### Option A: llama.cpp / Prism OpenAI-compatible server

Expose your Bonsai GGUF at an OpenAI-compatible endpoint such as:

```text
http://localhost:8080/v1
```

Set `backend/.env` from `.env.example` and keep:

```env
LLM_PROVIDER=openai_compatible
LLM_MODEL=bonsai2-27b
LLM_BASE_URL=http://localhost:8080/v1
LLM_API_KEY=local
```

The exact model name must match the name your server accepts.

### Option B: Ollama

Create/import the Bonsai GGUF in Ollama, then set:

```env
LLM_PROVIDER=ollama
LLM_MODEL=bonsai2-27b
LLM_BASE_URL=http://localhost:11434/v1
```

Both providers use plain chat with one leading system message containing the
agent instructions and expected JSON schema. PydanticAI returns text; the backend
strips accidental JSON fences, parses it with `json.loads`, and validates it with
the existing Pydantic models. Agent result schemas are never sent as tools or
native structured-output requests, keeping Prism/Bonsai chat templates compatible.
Invalid JSON, empty output, or schema validation failures receive up to two retries, each as a
fresh system/user conversation with validation feedback. If all three attempts
fail, the saved run records a clear error with retry guidance. The legacy
synchronous architecture API returns HTTP `500` for this failure.
`LLM_TIMEOUT_SECONDS` defaults to `1800` per model call so slow local generations
are not interrupted by the client's usual ten-minute timeout. This is separate
from the JSON validation retry limit.

## 3. Backend

```powershell
Set-Location C:\path\to\archpilot\backend
if (!(Test-Path .env)) { Copy-Item .env.example .env }
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m app.db.check
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend: `http://localhost:8000`
Docs: `http://localhost:8000/docs`

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

### Database configuration and troubleshooting

`backend/.env` is resolved relative to `app/config.py`, regardless of the launch
directory. `DATABASE_URL` is required; there are no fallback database credentials
in Python. For this Docker setup, use:

```env
DATABASE_URL=postgresql+asyncpg://archpilot:archpilot@127.0.0.1:5433/archpilot
```

Pydantic Settings intentionally gives process environment variables precedence
over `.env` (including values inherited from Windows user/machine settings).
Startup logs print the effective host, port, database, username, and configuration
source, but never the password or full URL. A process override produces a warning.
If an old `DATABASE_URL` is set in your current PowerShell session, clear it before
starting the backend:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

If a persistent Windows user/machine variable is set, update or remove it in
Windows Environment Variables, then open a new terminal. Restart FastAPI after
configuration changes; settings and the engine are cached for the process lifetime.

Check connectivity without starting FastAPI (from `backend`):

```powershell
.\.venv\Scripts\python.exe -m app.db.check
```

Success prints `Database connectivity OK`, plus the actual server version and
server address, and exits with code `0`. Failure exits with code `1`.
The target log should show `host=127.0.0.1 port=5433 database=archpilot username=archpilot`.
The server's internal port remains `5432`.

After startup, check the API and database together in another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/health
```

Success returns `status`, `database`, and safe runtime display metadata. This
endpoint executes `SELECT 1` with a five-second timeout and returns HTTP `503`
if the database cannot be reached; it does not expose endpoints, connection
errors, or credentials.

Validate all external integrations before a new deployment:

```powershell
.\.venv\Scripts\python.exe -m app.preflight
```

The preflight checks PostgreSQL, the configured OpenAI-compatible model API,
and SearXNG without printing secret values or endpoint URLs.

Useful infrastructure checks (from the project root):

```powershell
docker compose ps
docker compose port postgres 5432
docker compose logs --tail 50 postgres
docker compose exec postgres psql -U archpilot -d archpilot -c "SELECT current_database(), current_user, version();"
Get-NetTCPConnection -State Listen -LocalPort 5432,5433 | Select-Object LocalAddress,LocalPort,OwningProcess
```

After changing the port mapping, run `docker compose up -d --wait postgres`.
The existing database volume is preserved. `POSTGRES_*` initialization values only
apply to an empty data directory; recreating a container does not reset an existing
database password. Do not delete the volume to fix host port routing.

## 4. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Frontend: `http://localhost:3000`

The browser posts to Next.js `/api/queries`, which forwards the request to
`BACKEND_API_URL` (locally `http://127.0.0.1:8000`). FastAPI saves the query and
returns HTTP `202`, then runs the local agent pipeline in the background. The
frontend polls real stage updates and persisted classifications every two seconds.
Query URLs restore the workspace after a refresh without repeating generation.
Database credentials stay in the backend.

Each original user query contains its requirement classifications, cumulative
clarification answers, and full design versions. Continue a query through
`POST /v1/queries/{query_id}/runs`; retrieve the whole record through
`GET /v1/queries/{query_id}`. The UI provides both whole-query and individual-design
JSON exports. Existing saved runs are imported without changing their payloads;
legacy clarification rounds sharing the exact original query are grouped together.

For the local demo, run one backend worker. It serializes background jobs for the
local model. Browser disconnects do not cancel generation; backend restarts mark
unfinished runs as failed and preserve their snapshots for a retry. A durable
external job worker is a production follow-up.

Set `BACKEND_TIMEOUT_SECONDS=3600` in `frontend/.env.local` for local Bonsai runs.
The original synchronous `/api/architect` and `/v1/architectures` contracts remain
available. Their generation proxy applies this timeout to header/body waits and the overall request;
the normal five-minute HTTP header timeout is too short for this pipeline.
Restart Next.js after changing its environment file.

Frontend checks: `npm run test`, `npm run typecheck`, and `npm run build`.
On Windows PowerShell, use `npm.cmd` if execution policy blocks `npm.ps1`.

## Vercel deployment

Deploy only `frontend/` to Vercel. The local FastAPI backend must be reachable from Vercel, so use a secure public endpoint/tunnel during development and set:

```env
BACKEND_API_URL=https://your-backend-host.example
ARCHPILOT_PROXY_TOKEN=use-the-same-random-server-only-secret-as-fastapi
```

Do not expose your raw LLM endpoint publicly. Vercel talks to FastAPI; FastAPI talks to the local LLM. The token is optional for loopback-only development and required for the public tunnel used by the demo.

See [VERCEL_GPU_DEMO.md](VERCEL_GPU_DEMO.md) for the one-command Windows bridge,
Vercel variables, security boundary, and temporary-tunnel lifecycle.

## Bring your own compute and services

ArchPilot also ships standard backend and frontend Docker images plus a
self-hosted Compose profile. It can use PostgreSQL, SearXNG, and any
OpenAI-compatible model endpoint on AWS, another cloud, an on-premises cluster,
or a local machine. The UI reports the configured compute profile without
exposing endpoint URLs or credentials.

See [DEPLOYMENT.md](DEPLOYMENT.md) for the integration contract, preflight
validation, Docker commands, AWS reference architecture, Kubernetes guidance,
network boundaries, and current scaling limit.

## Production follow-ups

For the first MVP, tables are created automatically at backend startup. Before a real multi-user deployment, add Alembic migrations, authentication, request quotas, secret management, source-domain weighting, deeper webpage fetching, evaluation datasets, and an optional local image-generation adapter.
