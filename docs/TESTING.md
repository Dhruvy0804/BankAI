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
