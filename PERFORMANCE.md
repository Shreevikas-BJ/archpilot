# Local generation performance

The local pipeline still runs Requirements → Research → Evaluation → Architecture
→ Critic → Revision → Final review when changes are required. It uses the same
Bonsai model, OpenAI-compatible endpoint, temperature, search
limits, evidence selection and six-plane review policy.

## Changes that reduce work

- Requirements analysis classifies the request instead of writing an early
  architecture, preserving explicit constraints and quantities. Normal JSON
  formatting is allowed; the model is not forced to serialize on one line.
- Clarification blocks only unresolved fundamental choices. Usable answers such
  as "several seconds" are preserved instead of repeatedly requesting more
  precision. Conservative assumptions are recorded explicitly; contradictions
  and material unresolved choices can still require the user's answer.
- Plain text is streamed through PydanticAI. An incremental syntax check cancels
  an attempt when its JSON is already irrecoverably invalid, or a complete object
  fails the existing schema. This avoids waiting for the rest of a broken response.
  Partial parser values are never accepted. Valid responses still run to their
  natural end and pass the ordinary `json.loads` and `model_validate` path.
- The revision agent returns an internal `ArchitectureRevision` containing only
  changes. Python preserves omitted fields and untouched components exactly.
  Changed lists replace the entire list; removals are explicit. A revision can
  add or remove components and redesign connections, without regenerating the
  unchanged parts of a design.
- The merged result is validated using the existing `ArchitecturePlan`, including
  its connection and size constraints. Invalid, conflicting and empty revisions
  enter the same retry handler as malformed JSON. The optimization mode cannot
  be changed by the revision.
- The final critic sees the **complete merged architecture**, the original
  request, research and evaluation. All component, plane and messaging checks
  remain mandatory. Failed or missing findings still prevent approval.
- The critic's internal schema names the exact component IDs in separate
  responsibility and disappearance maps and requires every plane and messaging
  check. All four maps use the same simple check shape. Duplicate JSON keys are
  rejected instead of silently overwriting an earlier finding. Missing or extra reviews retry in the critic,
  rather than sending an incomplete audit to architecture revision.
- Stable request, requirements, evaluation and evidence appear before the changed
  architecture in both critic prompts, allowing the local server to reuse their
  common prompt prefix when its cache is available. No content is removed.
- Design and revision allow up to 4,096 reasoning tokens instead of cutting thinking off
  after 1,024. Captured critic failures at the old limit contained unfinished
  reasoning in the final text. This allowance addresses those wasted retries;
  it is not a promise that every individual attempt is faster. Configure the
  llama.cpp-only `LLM_REASONING_BUDGET_TOKENS` extension in `backend/.env`;
  leave it unset for other compatible servers. It is never sent to Ollama.
- Review uses 2,048 tokens with the complete, simpler audit shape. The optional
  `LLM_REASONING_BUDGET_MESSAGE` asks for final JSON when thinking reaches its
  allowance, using a llama.cpp request option. It does not edit the chat template.
  Failed attempts retain the full 4,096-token allowance. The live negative fixture
  still rejected all nine deliberately unsafe messaging contracts.
- Classification, research planning and evaluation keep their original 1,024-token
  allowance through `LLM_PLANNING_REASONING_BUDGET_TOKENS`. A failed attempt retries
  with the full allowance and the same original input, schema and validation
  feedback. Architecture and both critic passes always see the full user request.
- Demo startup uses an 18,432-token context, configurable with `--context-size`.
  The live 8 GB GPU remained within its memory capacity with the existing model
  and cache precision. An already healthy server is reused, so changing startup
  options requires restarting that server while no generation is active.

Public request/response schemas, database records, exports, progress stages and
the frontend remain compatible. Model output remains plain text parsed with
`json.loads` and `model_validate`; there are no tool calls, provider structured
output, grammar changes or chat-template changes.

## Measure a real request

After starting the demo, this command creates one additional round beneath an
existing saved query using the exact request from its latest completed round:

```powershell
.\backend\.venv\Scripts\python.exe scripts/benchmark_query.py QUERY_UUID
```

The script waits for completion, compares per-stage and total durations, and
saves the accepted response, full result and comparison in `.demo/performance/`.
It also reports component/source counts, audit coverage and failed findings.
A completed generation is not necessarily an approved design.
Use `--baseline-run RUN_UUID` to compare against a particular completed round
instead of the latest completed round. Its exact request, including clarification
answers, is reused.

Every model attempt logs its run, stage, schema, elapsed seconds, input/output
tokens, output length, finish reason and validation outcome. Logs contain no
prompt or response contents. For the demo, inspect `.demo/backend.stderr.log`.
This makes retries and output-heavy stages visible without collecting private
request text in telemetry.

Compare the same request, including clarifications and optimization mode. Model
outputs, search results, GPU load and prompt-cache state vary between runs; one
timing comparison is an observation, not a guaranteed latency bound or proof of
semantic equivalence. Inspect the design and its review as well as elapsed time.

## Measured full-system result

The September 29, 2026 local test replayed the **exact same request**, including
all four clarification answers and `high_performance` mode, through the frontend
proxy to FastAPI, local Bonsai and PostgreSQL. It completed every stage, including
revision and final review, and saved the result under the original query.

**Overall latency did not improve in this comparison:** 25m 15.94s versus
24m 16.97s, or 4.0% slower. The smaller review format and partial-revision support
reduce avoidable work, but do not guarantee shorter generations. The evaluation
retry and larger architecture/revision outweighed the faster requirements stage.

| Stage | Original baseline (seconds) | Current run (seconds) |
| --- | ---: | ---: |
| Requirements | 398.86 | 84.85 |
| Research planning | 58.06 | 51.36 |
| Search | 2.88 | 5.79 |
| Evaluation, including retries | 149.52 | 385.83 |
| Architecture | 238.66 | 302.56 |
| Critic | 181.08 | 176.17 |
| Revision | 259.63 | 296.35 |
| Final review | 168.18 | 212.93 |
| Total, including queue and save | **1456.97** | **1515.94** |

The current run had one evaluation retry for an invalid enum value: the rejected
attempt took 139.06s and the successful retry 246.76s. All other model stages
validated on their first attempt. The original baseline also included one retry,
in requirements. GPU generation throughput varied during testing. These are
observations from individual runs, not a statistically established speedup.

The final design contains 13 components, 30 research sources and **41 audit
findings**: two per component, six planes and nine messaging contracts. Fifteen
findings failed, so the design is **not approved**. Remaining concerns include
unsupported consensus/fencing and atomic outbox claims, and insufficiently
specified durability/replication guarantees. The model's findings remain visible
for human review; complete coverage does not establish their semantic correctness.

Verification passed across frontend, API and database: all 11 rounds, their
classifications, saved answers, stage events and archived responses matched
PostgreSQL exactly. The real browser displayed all 41 findings identically to
the API, showed "Review recommended", loaded the supplied logo, and had no
browser errors or horizontal overflow. Live progress and opening a prior saved
design during generation were also verified.

- Query: `d8c3aa90-cafe-43b5-829e-87450f06909b`
- Baseline run: `24aff760-f9a6-47be-adbd-780d9137238f`
- Current run: `90b14363-abc4-4d7b-8264-ef894526f05c`
- Local captures: `.demo/performance/90b14363-abc4-4d7b-8264-ef894526f05c-{accepted,result,summary}.json`
- Browser screenshot: `.demo/performance/final-review.png`

Earlier intermediate runs took 26m 16s and 26m 50s; those are not used as the
baseline to inflate the speed comparison. A subsequent 84-second round stopped
for unnecessary clarifications and is not counted as a completed timing result.
The requirements prompt was corrected before the final run above. Further total
latency reduction, especially avoiding full evaluation regeneration for enum
errors, remains unfinished; no validation or responsibility checks were relaxed
to make the benchmark faster.

## Regression checks

The final backend suite passed **115 tests**, including PostgreSQL checks. Targeted
Ruff checks passed. The unchanged frontend previously passed its 16 tests,
TypeScript check and production build.

The live Bonsai negative fixture passed with the configured 2,048-token review:
all seven components were assessed and all nine deliberately unsafe messaging
contracts were rejected (165.9 seconds). A 1,024-token review experiment omitted
required component findings and was rejected; that setting is not enabled.

On the same saved 12-component design, the complete 2,048-token review took
194.33 seconds versus 266.11 seconds for the earlier 4,096-token nested review
format. Both reported 39 findings and withheld approval. This isolated result is
not an end-to-end latency measurement or proof that semantic judgments are equal.

The backend suite verifies every prefix of representative valid JSON, including
Unicode escapes and code fences, and proves that an invalid stream is closed
without consuming its tail before a fresh plain-chat retry. It also verifies that
unchanged design content survives a revision,
invalid references/removals/conflicting edits retry, the public contract is
unchanged, and the full architecture reaches the final critic. Existing tests
cover all nine messaging checks and incomplete or contradictory audits. The live
negative fixture can be run separately while the model is idle:

```powershell
.\backend\.venv\Scripts\python.exe scripts/verify_responsibilities.py
```

It must reject all nine unsafe messaging contracts. Run
`scripts/verify_query.py QUERY_UUID` to compare the completed benchmark round
and its full history with PostgreSQL through the frontend proxy.

## Implementation map

| Files | Change |
| --- | --- |
| `backend/app/agents/factory.py`, `backend/app/config.py`, `backend/.env.example` | Configurable planning/design/review reasoning allowances; plain-text PydanticAI generation |
| `backend/app/agents/json_output.py`, `backend/app/agents/json_stream.py` | Early invalid-stream cancellation, strict JSON parsing, validated retries and timing metadata |
| `backend/app/agents/revision.py`, `backend/app/agents/orchestrator.py` | Validated partial revisions, full-budget retries and complete final review |
| `backend/app/agents/review_output.py`, `backend/app/agents/prompts.py` | Exact audit coverage and concise, responsibility-aware instructions |
| `backend/tests/test_agent_json.py`, `test_agent_revision.py`, `test_json_stream.py`, `test_review_output.py` | Wire format, retry, merge, streaming and audit regressions |
| `scripts/start_demo.py`, `benchmark_query.py`, `profile_review.py`, `verify_responsibilities.py` | Local runtime settings and reproducible live checks |

The local `backend/.env` enables the documented Bonsai allowances. Existing API
and database schemas are unchanged. `README.md` and `ARCHITECTURE_REVIEW.md` link
the workflow and its quality checks.
