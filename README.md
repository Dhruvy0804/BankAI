# BankAI

A local, fictional banking assistant and private agent-evaluation workspace.
Main architecture: **5 total agents**, including Supervisor. Evaluation
variants: **2, 3, and 5 total agents**, using the same banking capabilities.

## Current checkpoint

Phases 0–2: documentation, health/readiness, frontend shell, PostgreSQL/
pgvector setup, database models, Alembic migrations, and fictional seed data.
Login, banking APIs/UI, AI, voice, and evaluation execution are subsequent
phases. The frontend does not display banking records yet.
See [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Prerequisites

- Python 3.11+
- Node.js 22.12+ and npm
- Docker Desktop running Linux containers (or local PostgreSQL 16 with pgvector)
- Available local ports 55432, 8000, 5173 (PostgreSQL uses 55432 on the
  host to avoid interfering with an existing local PostgreSQL service)

## Local setup (PowerShell)

From the project root, optionally copy configuration. Defaults already
support local Phase 1. Never put real banking information in this project.

```powershell
Copy-Item .env.example .env
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-dev.lock.txt -e '.[dev]'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.seed.demo_data
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, from the project root:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. API docs: http://127.0.0.1:8000/docs.
`/health` reports process status. `/ready` returns 200 only when a real
database query succeeds, otherwise a sanitized 503 with request ID.
The Vite dev proxy forwards frontend `/api/health` and `/api/ready` to
the backend. Browser credentials are not needed at this infrastructure phase.

## Docker alternative

```powershell
docker compose up --build -d
docker compose ps
```

This is local development, with ports bound to loopback and a Vite dev
server. It is not a production deployment. PostgreSQL data persists in
the `bankai_data` volume. `infra/init.sql` enables pgvector on first startup.

## Checks

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests
cd ../frontend
npm.cmd test
npm.cmd run build
```

See [testing](docs/TESTING.md) for verified results and limitations.
The frontend lockfile and Python constraints record the versions used
at this checkpoint. If npm 10 encounters an `edgesOut` error while
changing dependencies, use a temporary npm 11 invocation; do not force
dependency upgrades or disable peer checks.

## Shutdown and troubleshooting

Stop local servers with Ctrl+C. From the root, `docker compose stop`
stops containers while retaining data; `docker compose down` removes
containers/network while retaining the database volume. Do not delete
the volume to solve an ordinary connection error.

- Docker pipe/daemon error: start Docker Desktop and wait for the engine.
- Port already used: stop the conflicting service or adjust both Compose
  and `DATABASE_URL` / proxy settings consistently.
- Backend connected, database unavailable: check `docker compose ps` and
  `docker compose logs db`; confirm database connection settings locally.
- Backend unavailable: start Uvicorn on port 8000, then refresh status.
- PowerShell script restrictions: use `npm.cmd` and the virtual environment's
  Python executable; activation is unnecessary.

## Demo database (Phase 2)

Run migration and seed commands from `backend` as shown above. Migration
`0001` creates ten application tables and enables pgvector. Seeds include
3 customers, 4 accounts, 20 transactions, 4 cards, 3 KYC records, 3 loans,
3 support tickets, 1 audit event, and 1 synthetic policy with 1 chunk.
Money is stored as exact decimals, timestamps include timezone, and
transaction totals match the initial account balances.

For local development only, the fictional emails are
`demo.asha@bankai.example`, `demo.ravi@bankai.example`, and
`demo.mira@bankai.example`. Their shared demo password is
`BankAI-demo-only-2026!`, stored in PostgreSQL only as salted Argon2 hashes.
**Login is not implemented yet.** These are not production credentials.

Repeat seeding safely: existing IDs, passwords, balances and card states
are preserved. A repeated unchanged seed reports zero inserted records.
There is no destructive reset command. Test fixtures are disposable; do
not downgrade or delete the demo database to rerun seeds. Local seed CLI
rejects remote hosts and non-development mode. This guard is not a
replacement for future authentication.

Docker backend images now include the migration tooling and mount the
sample corpus read-only. After starting Compose:

```powershell
docker compose exec backend python -m alembic upgrade head
docker compose exec backend python -m app.seed.demo_data
```

Policy storage is prepared, but embeddings remain NULL until the RAG
phase configures a provider. No fabricated embeddings are seeded.
Provider adapters and voice setup will be added in their phases. No
provider keys are required for Phase 2; blank values are not integrations.
Replace the placeholder app secret before authentication is implemented.

## Documentation

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API_SPEC.md)
- [Security](docs/SECURITY.md)
- [Demo guide](docs/DEMO_GUIDE.md)

Implementation references: [Vite](https://vite.dev/guide/),
[Tailwind Vite integration](https://tailwindcss.com/docs/installation/using-vite),
and [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
