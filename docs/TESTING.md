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
