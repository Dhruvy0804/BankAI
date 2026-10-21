# Testing

## Phase 1 checks

Backend: `backend/.venv/Scripts/python.exe -m pytest -q` from `backend`.
Tests exercise process health during DB failure, readiness probe success,
sanitized/traceable 503 failure, and allowed versus disallowed CORS origins.
Probe injection in unit tests is not evidence of live database readiness;
verify that separately through `/ready` with PostgreSQL running.

Frontend: `npm.cmd test` and `npm.cmd run build` from `frontend`.
Tests verify backend outage/retry behavior and distinguishing database
outage from healthy API. Build performs strict TypeScript checking.

Lint: `.venv/Scripts/python.exe -m ruff check app tests` from `backend`.

Live checks: startup, GET `/health`, GET `/ready`, proxied frontend
endpoints, and a database query for installed pgvector. Compose config
validation does not substitute for building/running containers.

Current commands and outcomes are recorded in IMPLEMENTATION_STATUS.md.
Later phases add business, authorization, workflow, provider and
evaluation tests. No agent accuracy or latency has been measured yet.

## Phase 2 database suite

From `backend`, with Docker PostgreSQL running:

```powershell
$env:BANKAI_RUN_DB_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests alembic
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m pip check
```

Without the environment flag, 14 integration cases are explicitly skipped;
6 unit/infrastructure tests run. With it, all 20 tests pass. Each database
test uses a generated `bankai_test_<uuid>` schema, including its own
Alembic version table, and cleans up only that schema. It does not drop
or reset the public demo tables. Test connection needs schema creation
permission and pgvector installed; the local Docker setup provides both.

The integration suite checks migration reversibility and metadata drift,
repeat seeds preserving changes, password hashes, decimal ledger totals,
timezone roundtrips, foreign keys, status/range constraints and vector
storage. It tests the actual PostgreSQL engine, not SQLite substitutes.
No frontend changes were needed in Phase 2; the Phase 1 UI results remain
the last frontend checks.

## Phase 3 security and API suite

Final Phase 3 run: **57 tests passed** with PostgreSQL enabled (one
non-failing upstream Starlette deprecation warning).

Use the same database-test command above. Added tests cover authentication
claims and expiration, wrong signatures, missing signing configuration,
registration/login, inactive users, cross-customer access, transaction
filters, confirmation state transitions, expiry/replay, exact action
binding, changed card/KYC state, support ownership, sanitized errors and
audits, throttling, authenticated browser preflight, and EMI edge cases.
Concurrency uses separate PostgreSQL connections and simultaneous requests
to the service: only one loan is created. An injected audit-storage failure
verifies that neither the card change nor pending-action consumption persists.

Unit tests do not require PostgreSQL. Integration tests are opt-in via
`BANKAI_RUN_DB_TESTS=1` and never reset demo data. Current counts/results
are in IMPLEMENTATION_STATUS.md. Frontend tests/build were not repeated
because this phase changes no frontend files; visual UI testing remains
for Phase 4. Docker build and actual HTTP login/account/EMI checks are
separate evidence beyond TestClient tests.

## Phase 4 frontend and real-browser QA

From `frontend`: `npm.cmd test` (12 tests passed) and `npm.cmd run build`
(strict TypeScript and production build passed). The earlier 2 infrastructure
shell tests were replaced with 12 banking behavior tests. Native dialog APIs
have a jsdom-only shim; actual focus behavior is validated in Edge.

Tests cover login/logout, restored and expired sessions, stale-read clearing,
read retry/error states, pagination/filter/empty views, cancel versus confirm,
duplicate/expired confirmations, server-bound loan details, and ticket form
input preservation on failure. Existing backend code is unchanged and its
previous 57 passing tests remain the last backend regression result.

Optional repeatable browser check (Windows, installed Microsoft Edge):

```powershell
# Run from the project root with the backend environment installed and database running.
.\backend\.venv\Scripts\python.exe -m pip install --target .qa-tools playwright
$env:PYTHONPATH=(Resolve-Path '.qa-tools').Path
.\backend\.venv\Scripts\python.exe frontend/tests/browser_smoke.py
```

The script generates a unique local `bankai_ui_test_<uuid>` database,
migrates/seeds it, starts isolated API/Vite processes and uses a fresh Edge
context. It never resets the demo database and removes its own processes/
database in cleanup. The database user needs CREATE DATABASE permission
(provided by the local Docker setup). No browser profile or tokens are saved.
Tooling is installed only in ignored `.qa-tools`, outside application manifests.
Screenshots are in ignored `.artifacts`.

Docker frontend build/start was verified separately: HTTP 200 at the root,
and the frontend proxy returned database readiness from the backend. Wait
for Vite's ready message before probing a newly started container.

Passed on Edge at 1440px desktop and 390px mobile: login/refresh, all pages,
card/loan confirmations, keyboard modal cancellation/focus return, EMI,
support, customer switching, 401 clearing and no page overflow/errors.
Screenshots were visually inspected. Safari, Firefox and physical-phone
testing have not been performed. Browser channel setup follows the
[official Playwright documentation](https://playwright.dev/python/docs/browsers).

## Plan 2 Phase 5 verification

Run the existing backend/full-database and frontend commands above. On 2026-10-20:
74 backend tests, 15 frontend tests, Ruff, pip check, and the frontend build passed.
The database suite checks migration `0003` against SQLAlchemy metadata and runs
an upgrade/downgrade roundtrip in disposable schemas. Chat tests use the shared
BankSim fixture and do not reset the application's database.

`tests/test_llm.py` exercises the installed official SDK using httpx MockTransport
to inspect the actual outgoing request and validate returned JSON, usage, invalid
output, timeouts, sanitized provider failures, and the absence of retries.
`tests/integration/test_chat.py` separately tests real PostgreSQL ownership,
history, idempotency, rollback/auditing, limits, and concurrent row locks using
independent database connections. Its fake provider is test-only and cannot be
selected through runtime configuration. Frontend tests check submission/history,
plain-text HTML escaping, same-ID retry, and missing-configuration behavior.

The existing Edge smoke script now creates/reopens a real empty conversation,
checks the missing-provider state, and checks Text assistant on mobile along with
the banking regression flows. It explicitly clears provider configuration in
its subprocess environment, makes no paid model request, and creates only its
disposable QA database. `.artifacts/chat-mobile.png` was visually inspected.

Live model acceptance subsequently passed using locally configured
`gemini-3.5-flash-lite`: three real HTTP chat requests verified a general answer,
a contextual follow-up, and a safe account/action limitation response. Pydantic
validation, provider usage metadata, saved reload, retry deduplication, and
unchanged card/loan records passed. Edge reopened these live responses after
refresh at desktop/mobile sizes with no page errors or overflow. Local evidence
is in ignored `.artifacts/phase5-live-chat.json` and `phase5-live-*.png`.

Live integration revealed that `response_schema` encoded `additionalProperties`
using a provider-rejected field. The adapter now sends the Pydantic JSON schema
through `response_json_schema`; the outgoing-field regression assertion and all
11 adapter tests passed after the fix. The existing 74-test backend and 15-test
frontend results above precede this narrow follow-up; unchanged UI tests/build
were not repeated. MockTransport alone cannot verify live API compatibility.
The live smoke samples do not establish broad answer accuracy, prompt-injection
resistance, provider uptime, or invoiced charges; those evaluations remain later work.

## Plan 2 Phase 6 verification

Final checks: **85 backend tests passed**, with two opt-in tests skipped by
default; **16 frontend tests passed**, and the TypeScript/production build passed.
The opt-in live-provider and Edge checks were run separately and passed. Ruff,
pip check, migration consistency/roundtrip and the rebuilt Docker application
also passed. Mobile screenshots were visually inspected.

Run the normal full-database backend suite and frontend tests/build as above.
Phase 6 uses disposable PostgreSQL schemas and independent connections. Protocol
integration tests launch a loopback Uvicorn server and run actual ADK and CrewAI
agents over official A2A/MCP transports; only external model responses are mocked
in the default suite. No runtime mock provider option is exposed to users.

Checks cover typed tool arguments/results (including a malformed raw MCP request),
ownership and role restrictions, scoped task lookup, Blackboard revision conflicts
and consumer IDs, bounded budgets/concurrency, expiry/cancellation, completed-run
message replay, tool receipt reuse, protected card/loan confirmation, support
ticket creation, existing loans, and recent transactions. The custom CrewAI SDK
adapter also tests stop-sequence serialization, usage callbacks and key exclusion
from model serialization. Stable event sequence ordering is asserted even when
database timestamps tie. The migration test round-trips through `0005` and compares
the ORM metadata with the actual database schema.

Explicit real-provider acceptance (charges/quota may apply):

```powershell
cd backend
$env:BANKAI_RUN_DB_TESTS='1'
$env:BANKAI_LIVE_AGENT_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_agents.py::test_live_five_roles -q
```

This test creates a disposable schema, uses the configured local Gemini model,
invokes all four specialists through ADK/A2A, checks actual tool facts and shared
context, and writes a local ignored evidence report. Do not enable it in ordinary
CI runs. The successful sample used 12 model calls, three tool executions and
22,493 tokens; it is acceptance evidence, not the 2/3/5-agent benchmark.

Optional browser QA with the existing ignored Playwright installation:

```powershell
# From the project root; .qa-tools Playwright and Edge must already be installed.
$env:BANKAI_RUN_DB_TESTS='1'
$env:BANKAI_BROWSER_AGENT_TESTS='1'
$env:PYTHONPATH=(Resolve-Path '.qa-tools').Path
cd backend
.\.venv\Scripts\python.exe -m pytest tests/integration/test_agents.py::test_agent_chat_browser -q
```

The browser test starts an isolated Vite server pointed at the disposable API,
uses real frameworks/protocols with test-only model responses, and makes no paid
model calls. It verifies trace expansion, confirmation details, cancel versus
confirm, actual card state, desktop/mobile layout and absence of browser errors.
Screenshots are local ignored artifacts. The original banking browser smoke also
passed after the framework dependency changes.

The live Docker smoke separately verifies actual provider calls through the
frontend proxy, ownership-scoped account facts, the EMI calculator, saved history,
replay deduplication, typed finalization, and ordered trace events. Its JSON
evidence stays in ignored `.artifacts/phase6-docker-live.json` without credentials.
Local configuration is not a provider-health guarantee; key expiry/quota changes
must produce safe errors. Non-failing upstream annotation/deprecation warnings
are retained rather than hidden. At the Phase 6 checkpoint, RAG grounding, prompt/architecture comparisons,
load/cost benchmarks and cloud/phone acceptance remain later phases.

## Plan 2 Phase 7 verification

From `backend`, run the full database-backed suite or only policy checks:

```powershell
$env:BANKAI_RUN_DB_TESTS='1'
.\.venv\Scripts\python.exe -m pytest -q --disable-warnings
.\.venv\Scripts\python.exe -m pytest tests/test_policy_contracts.py tests/integration/test_policies.py -q
```

Policy tests use the existing disposable PostgreSQL schemas and real ADK,
CrewAI, A2A HTTP and MCP transports. Model and embedding responses are mocked
unless explicitly enabled. Checks cover ingestion/repeat behavior, relevant and
irrelevant retrieval, wrong model/missing index, unapproved and tampered source
rejection, named-section conflicts, tool permissions/receipts, citation
fabrication, missing/conflicting policy answers, history and provenance.
Final default result: **98 passed, 4 opt-in tests skipped**. The policy Edge test
was separately enabled and passed. Frontend: **17 passed**, strict TypeScript
and Vite build passed; Ruff, dependency and whitespace checks passed.

Explicit paid provider acceptance (uses configured local keys):

```powershell
$env:BANKAI_LIVE_POLICY_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests/integration/test_policies.py::test_live_policy_answer -q
```

This ingests a disposable corpus and verifies a cited answer through the real
framework/protocol workflow. Leave the flag unset for ordinary tests. Two local
frontend-proxy acceptance samples additionally checked a grounded loan document
answer and an unpublished fee, saved history and retry deduplication. Evidence:
ignored `.artifacts/phase7-live.json`; embeddings report unknown usage as `null`.
A real-provider Docker frontend-proxy request also verified an exact cited
loan-document section, protocol events and Blackboard publication; repeat
ingestion embedded zero chunks. Evidence: `.artifacts/phase7-docker-live.json`.

Optional Edge source UI check, from the project root:

```powershell
$env:BANKAI_RUN_DB_TESTS='1'
$env:BANKAI_BROWSER_POLICY_TESTS='1'
$env:PYTHONPATH=(Resolve-Path '.qa-tools').Path
cd backend
.\.venv\Scripts\python.exe -m pytest tests/integration/test_policies.py::test_policy_citation_browser -q
```

This starts an isolated Vite/API workflow with test-only provider responses.
It verifies expandable source excerpts, retrieval traces, desktop/mobile layout
and absence of browser errors. Screenshots stay in ignored `.artifacts`.
The frontend citation test also verifies HTML-like excerpts render as plain text.
No comparative retrieval, cost, prompt or architecture benchmark is claimed.
