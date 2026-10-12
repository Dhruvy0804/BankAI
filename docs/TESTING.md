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
