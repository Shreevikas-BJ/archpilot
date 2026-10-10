# ArchPilot local demo

Open **http://127.0.0.1:3000**. API documentation is at http://127.0.0.1:8000/docs.

## Start everything

From this repository in PowerShell:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\start_demo.py
```

The launcher starts Docker PostgreSQL and SearXNG, checks your configured local
Bonsai endpoint, starts FastAPI, and builds/starts the production frontend when
needed. It reuses healthy running services. It preserves the existing database,
model configuration, and chat template. Dependencies must already be installed
(see README.md). New background process logs are written to `.demo/`.

On this machine the configured GGUF and `runtime/llama/llama-server.exe` are under
`C:\Models\Bonsai2`. If those paths change, start Prism yourself or provide
`--llama-server PATH --model-file PATH`. A server started by the launcher uses
one inference slot and a 16K context to fit this demo's local GPU. It also sets
`--reasoning-budget 1024` so unrestricted thinking cannot consume the entire
context before the model produces its JSON answer. This is a runtime limit; the
model and chat template are unchanged. If you start Prism yourself, use the same
reasoning budget in its server arguments.

After editing code, stop the affected Next.js/FastAPI process and rerun the
launcher. It deliberately does not terminate existing processes. Use `--build`
to force a frontend rebuild after stopping Next.js.

## Show the product

1. Click a query in **Saved queries**. Each original brief contains its classified
   requirements, clarification rounds, and complete design versions. The existing
   RAG query includes all seven earlier rounds.
2. Show **Overview**: system diagram, components, deployment, and cost estimate.
3. Show **Decisions**, **Delivery**, and **Sources** for the evaluated choices,
   critic's review, implementation steps, and research links.
4. Expand **Classified requirements** to inspect ten categories for the selected
   round. **Export entire query** downloads every round and complete response;
   **Export this design** downloads only the selected architecture response.
5. For a live run, click **New query**, **Use demo brief**, then **Design architecture**.
   The live panel shows the actual backend stage: requirements, research, search,
   evaluation, architecture, critic, and revision if needed. Local generation takes
   several minutes; the timer shows elapsed time, not an estimated percentage.
6. Refresh while generation is running. The query URL reconnects to the same run;
   it does not start another generation. Classifications appear as soon as the
   requirements stage finishes, and the completed design is saved before display.

If the requirements agent asks for clarification, answer the displayed questions
and click **Continue design**. A critic may recommend further review; the UI shows
the real approval state rather than treating every completed response as approved.

## Connections

| Service | Local address |
| --- | --- |
| Next.js frontend | `127.0.0.1:3000` |
| FastAPI | `127.0.0.1:8000` |
| Bonsai OpenAI-compatible endpoint | Existing `LLM_BASE_URL` in `backend/.env` |
| PostgreSQL | `127.0.0.1:5433` |
| SearXNG | `127.0.0.1:8081` |

The browser uses same-origin Next.js `/api/queries` routes. Next.js forwards
requests to FastAPI using `BACKEND_API_URL` in `frontend/.env.local`. Starting a
design returns HTTP 202 immediately. The browser polls saved progress every two
seconds; the backend runs the existing agent pipeline in the background.
The green connection badge checks FastAPI and PostgreSQL, not model readiness.
The model is checked separately by the startup command.

Browser refreshes and closed tabs do not interrupt generation. PostgreSQL stores
the original query, each round's request and classifications, timestamped stages,
and complete design responses. Clarification answers accumulate under the same
query. Earlier versions remain available after retries or later designs.

Run one FastAPI worker for this local demo. Its background queue permits one
generation at a time. Restarting FastAPI interrupts active jobs, marks them failed,
and retains their saved snapshots so they can be retried inside the same query.
It does not resume inference across backend restarts.

The original synchronous `/v1/architectures` and `/api/architect` APIs remain
compatible. `BACKEND_TIMEOUT_SECONDS=3600` applies to that legacy generation
proxy; each model call still uses `LLM_TIMEOUT_SECONDS=1800`.

## Checks

Verify the frontend proxy, saved-design API, Pydantic validation, and exact
PostgreSQL request/response persistence without another model generation:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_demo.py
```

```powershell
Invoke-RestMethod http://127.0.0.1:3000/api/health
Invoke-RestMethod http://127.0.0.1:8000/v1/architectures
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q
$env:ARCHPILOT_DATABASE_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/test_query_persistence.py -q
Set-Location ..\frontend
npm.cmd run test
npm.cmd run typecheck
npm.cmd run build
```

PydanticAI still orchestrates the full requirements → research → evaluation →
architecture → critic → revision flow. Agent output is plain text, parsed with
`json.loads` and validated against the existing Pydantic models. Invalid output
gets bounded retries without tool messages or extra system messages.

## Earlier synchronous API verification

- Before the query workspace update: backend **45 tests passed** and frontend
  **12 tests passed**. The updated workspace verification is recorded below.
- Real browser submission: **HTTP 200 in 565.3 seconds** through Next.js → FastAPI
  → local Bonsai/SearXNG → PostgreSQL → browser.
- Saved run: `b602d58f-579a-44eb-91b4-5f2d41ba3dc7`, **Cost-Effective Internal Staff
  Directory**, three components, five research sources, critic approved.
- The critic produced malformed JSON on two attempts; the existing bounded retry
  path recovered on the third attempt. No tool/structured-output metadata or chat
  template edits were needed.
- The browser's original request and returned response exactly matched the API
  readback and PostgreSQL record. A full page reload reopened the new design and
  rendered its diagram. Desktop/mobile layout, result tabs, source links, and JSON
  export passed browser checks with no JavaScript errors.
- [Completed desktop screenshot](frontend/demo-complete.png),
  [mobile screenshot](frontend/demo-mobile-result.png), and
  [recorded browser response](frontend/demo-e2e-result.json).

Recheck the recorded response against the running system:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_demo.py --capture .\frontend\demo-e2e-result.json
```

## Query workspace verification

- Backend: **51 tests passed**, including six tests against isolated PostgreSQL
  schemas. Frontend: **16 tests passed**. TypeScript, production build, and Ruff
  checks on changed backend files passed.
- The supplied logo is the main brand image; the UI has no duplicate app-name text.
- Real browser submission returned **HTTP 202 in about 1.2 seconds**. The local
  Bonsai pipeline completed in **1,130.6 seconds**, including critique, revision,
  and final review. Final critic: **approved**.
- Query: `00af4ae8-292a-4394-bbe2-935ceacdd129`; run:
  `17aac42f-6da2-4dbc-8e93-9c34bc28732f`, **Internal Staff Directory on Existing VPN**.
- A browser refresh during research restored the same run with its classifications;
  no duplicate generation was created. All actual stage events were persisted.
- The frontend record, original browser submission, requirements, events, and full
  architecture exactly matched PostgreSQL. The design remained available after
  restarting the demo services.
- The existing RAG query has **seven classified rounds and 17 clarification answers**
  under one original brief. Whole-query JSON export matched the complete saved
  record. Desktop and mobile layout checks passed with no horizontal overflow or
  browser JavaScript errors.
- Screenshots: [completed live design](frontend/query-complete.png),
  [saved RAG query](frontend/query-saved-rag.png), and
  [mobile workspace](frontend/query-mobile.png).

Recheck the completed query and its original browser submission:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_query.py 00af4ae8-292a-4394-bbe2-935ceacdd129 --accepted .\frontend\query-e2e-accepted.json
```

Verify every round of the existing RAG query:

```powershell
.\backend\.venv\Scripts\python.exe .\scripts\verify_query.py d62d6a9b-d8fc-41bb-84fd-fe0b0f5e349b
```
