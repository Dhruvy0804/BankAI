# BankAI

A local, fictional banking assistant and private agent-evaluation workspace.
Main architecture: **5 total agents**, including Supervisor. Evaluation
variants: **2, 3, and 5 total agents**, using the same banking capabilities.

## Current checkpoint

Phases 0–4: a working local banking web application with JWT login,
dashboard, accounts, filtered transactions, cards, demo loans and support.
It uses the seeded PostgreSQL records and confirmed banking APIs.
Plan 2 Phase 5 now adds authenticated text chat, saved conversations, and a
direct Gemini SDK adapter with Pydantic responses. Live model verification passed
with the configured local provider. Agent orchestration, voice and evaluation execution
are later phases. Active implementation follows
[Implementation Plan 2](BankAI_Implementation_Plan_2.md); the original plans are preserved.
Phase 8 includes browser voice and actual outbound phone testing: the owner
starts an approved call and the professor/recipient speaks with BankAI on
their phone. This is planned, not implemented. Telephone credentials, an
appropriate provider/caller number and a call budget will be required.
See [implementation status](docs/IMPLEMENTATION_STATUS.md).

## Text assistant setup (Plan 2 Phase 5)

Update the ignored root `.env` on the backend only:

```dotenv
LLM_PROVIDER=gemini
LLM_API_KEY=your-provider-key
LLM_MODEL=your-supported-model-id
LLM_TIMEOUT_SECONDS=30
LLM_MAX_OUTPUT_TOKENS=1024
```

Use a model available to your Google Gemini API project that supports structured
JSON output. Placeholder values above are not working credentials. The adapter
uses the [official Google Gen AI SDK](https://github.com/googleapis/python-genai)
directly; no agent framework is added in this phase. Other providers are not yet
implemented. Installing the updated backend dependencies and running
`python -m alembic upgrade head` adds the conversation tables without resetting
banking data. Restart the backend after changing configuration. For Docker, run
the migration with `docker compose exec backend python -m alembic upgrade head`
and recreate the backend after environment changes.

Sign in and open **Text assistant**, then start a conversation. You can reopen
saved conversations and inspect structured response details. Model calls send
the current question and the latest ten exchanges to the configured provider;
do not enter real credentials or personal information. History is stored in the
local database and isolated by customer. The list pages through 50 conversations
at a time, with at most 100 exchanges per conversation and 2,000 characters per question.

This phase provides general AI-generated guidance only. It has no account tools,
verified policy sources, or banking-action capability. Use the existing banking
pages for those tasks. CrewAI/ADK, A2A, MCP, and shared Blackboard start in Phase 6.
Missing configuration produces a visible unavailable state and API 503; it never
silently returns a fake AI answer. Configured status checks the settings, not
provider reachability or available credit.

The API provides `GET /api/v1/chat/status`, `GET/POST /api/v1/chat/conversations`,
`GET /api/v1/chat/conversations/{id}`, and `POST /api/v1/chat`. Posting a question
requires a conversation ID, a client-generated UUID `message_id`, and `message`.
Retrying the same ID/text reuses a committed response; a changed message with the
same ID is rejected. Concurrent sends to one conversation receive 409. On a
connection failure, check saved history before changing and resending the text.
A provider response followed by a server/database failure can still incur a charge
without a saved answer; this prototype cannot guarantee provider-level exactly-once billing.

Provider requests have one attempt and a configurable timeout. Generation is
limited to ten new requests per minute per customer per API process. This local
throttle is not a distributed deployment quota. Failed generations are not added
to chat context; sanitized failure audit records retain the request ID. Replies
save model/prompt version, run ID, duration, and provider-reported tokens, with
missing usage marked unavailable. Cost reporting and full tracing arrive later.

## Prerequisites

- Python 3.11+
- Node.js 22.12+ and npm
- Docker Desktop running Linux containers (or local PostgreSQL 16 with pgvector)
- Available local ports 55432, 8000, 5173 (PostgreSQL uses 55432 on the
  host to avoid interfering with an existing local PostgreSQL service)

## Local setup (PowerShell)

From the project root, set up local configuration with the helper below.
It generates a signing key without printing it and refuses to overwrite an
existing `.env`. Never put real banking information in this project.

```powershell
docker compose up -d db
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements-dev.lock.txt -e '.[dev]'
.\.venv\Scripts\python.exe -m app.core.setup_local
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
Sign in with a fictional demo customer, then use the sidebar to navigate.
The current tab retains its session across refresh until token expiry or
sign-out. A 401 returns to login and clears displayed customer data. Closing
the tab ends its browser session; passwords are not stored. Sign-out clears
the browser token but does not revoke a separately copied JWT server-side.
`/health` reports process status. `/ready` returns 200 only when a real
database query succeeds, otherwise a sanitized 503 with request ID.
The Vite dev proxy forwards frontend `/api/health` and `/api/ready` to
the backend. Banking routes require a Bearer token; infrastructure checks
remain public. If `.env` already exists, preserve it and configure a random
`APP_SECRET_KEY` of at least 32 characters. The supplied placeholder is
rejected; missing/placeholder keys disable authentication with HTTP 503.

## Docker alternative

```powershell
docker compose up --build -d
docker compose ps
```

This is local development, with ports bound to loopback and a Vite dev
server. It is not a production deployment. PostgreSQL data persists in
the `bankai_data` volume. `infra/init.sql` enables pgvector on first startup.
Compose loads the ignored root `.env` for backend authentication and overrides
its database host with the internal `db` service. Prepare `.env` first.

## Checks

```powershell
cd backend
$env:BANKAI_RUN_DB_TESTS='1'
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
Login now works through `/api/v1/auth/login`. These are not production credentials.

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
## Try the banking web application (Phase 4)

- Dashboard shows balances and recent activity fetched from the backend.
- Accounts includes an account selector and balance refresh.
- Transactions supports account/type/status/date/amount filters, previous/next
  paging, and a clearly labelled search of the current page.
- Cards stages a block request, then shows the exact card in a confirmation
  dialog. Cancel dismisses the dialog without executing; the server's pending
  request expires automatically. No backend cancellation endpoint exists yet.
- Loans provides API-backed EMI, demo eligibility and confirmed applications.
- Support creates tickets and shows the customer's saved history and details.

Loading, empty and error states include retry for reads. Writes are never
retried automatically. After an interrupted write, refresh the relevant
records to verify its outcome before manually repeating it. Demo changes
persist; seed reruns do not reset them. AI/evaluation features are marked as
future work in About and are not simulated as working UI features.

## Try Phase 3 APIs directly

Start the backend, open `http://127.0.0.1:8000/docs`, and call
`POST /api/v1/auth/login` with a demo email and password. Copy the returned
access token into Swagger's **Authorize** Bearer field. Do not put tokens
in source files or share them. Tokens expire after 30 minutes by default.

- `GET /api/v1/accounts`, `/cards`, `/loans`, `/kyc/status` and `/support/tickets`
  return only the authenticated customer's fictional records.
- `GET /api/v1/transactions` supports `limit`, integer `cursor`, `account_id`,
  `transaction_type`, `status`, date and amount filters.
- `POST /api/v1/cards/{card_id}/block` returns HTTP 202 and a pending action.
  It does not change card status. Confirm at `/cards/{card_id}/block/confirm`
  with `{ "action_id": "returned-uuid", "confirmation": true }`.
- `POST /api/v1/loans/applications` stages validated demo inputs. Confirm at
  `/loans/applications/{action_id}/confirm` with `{ "confirmation": true }`.
- A pending action expires after 5 minutes. Expired, reused, mismatched or
  another user's confirmations cannot execute. Replays return 409, not a second write.
- `POST /api/v1/support/tickets` creates an open demo ticket from an explicit request.

See [API details and example bodies](docs/API_SPEC.md). No real transfers,
credit decisions, identity document collection, or external bank connections exist.

## Documentation

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API](docs/API_SPEC.md)
- [Security](docs/SECURITY.md)
- [Demo guide](docs/DEMO_GUIDE.md)

Implementation references: [Vite](https://vite.dev/guide/),
[Tailwind Vite integration](https://tailwindcss.com/docs/installation/using-vite),
and [FastAPI containers](https://fastapi.tiangolo.com/deployment/docker/).
