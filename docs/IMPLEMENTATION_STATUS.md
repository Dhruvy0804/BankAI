# Implementation status

Updated: 2026-10-21. Active implementation: `BankAI_Implementation_Plan_2.md`.
Original implementation-plan documents remain preserved; phased delivery.

| Phase | Status |
|---|---|
| 0: Repository inspection and documentation | Complete |
| 1: Local scaffold and infrastructure | Complete; live API/database and frontend checks passed |
| 2: Models, migrations and fictional seed data | Complete; live migration, repeat seed and integration tests passed |
| 3: Authentication and BankSim APIs | Complete; 57 tests and live Docker API checks passed |
| 4: Banking dashboard | Complete; 12 UI tests, build and Edge desktop/mobile flows passed |
| 5: LLM adapter and text chat | Complete; local tests, live Gemini conversation, saved history, and browser checks passed |
| 6A: Frameworks, A2A and shared state | Complete; real ADK/CrewAI interoperability and ownership/revision tests passed |
| 6B: MCP banking tools | Complete; 10 scoped tools, real protocol calls and validation checks passed |
| 6C: Main five-agent system | Complete locally; live five-role workflow, protected actions, callbacks, trace UI and Docker verified |
| 7: RAG | Complete locally; approved corpus, embeddings, MCP retrieval, validated citations, live answers and desktop/mobile checks passed |
| 8A: Browser voice; 8B: actual outbound telephone calling | Not started |
| 9A–9C: Evaluation engine, web dashboard and benchmark | Not started |
| 10: Final deployment/demo verification | Not started |

## Plan 2 Phase 7: fictional policy retrieval

Implemented on `plan2-phase7` and included in this Git checkpoint. Next phase:
**8A, browser voice**. The Word abstract and original implementation plans are
preserved; no banking records are reset.

Three approved Markdown documents provide ten bounded, named citation sections.
`app.services.policies` offers an explicit idempotent ingestion command using
the existing policy tables and the direct Google embedding SDK. Live
`gemini-embedding-001` document/query requests with normalized 768-dimensional
vectors passed. The ignored local configuration reuses the existing provider
key; no secret is added to the repository. No dependency or migration is added.

Support's eleventh MCP tool, `search_policies`, returns a typed found/missing/
conflict result with document/chunk IDs, checksums, exact excerpts and similarity.
Only checked-in approved file versions qualify. Exact pgvector search is bounded
to four results above 0.60 cosine similarity. Old versions, arbitrary database
sources, and modified chunk text cannot become evidence. Query size, model,
vector dimensions/values and corpus completeness are validated.

Specialist and supervisor guardrails reject invented citations and answered
policy questions without retrieval. Missing/conflicting results require a
non-answer status. Source metadata is assembled from trusted MCP receipts and
persists with chat history and Blackboard artifacts. The final prompt version is
`phase7-rag-v1`; Phase 5/6 history remains readable. Source excerpts expand in the
chat UI, and retrieval events record source IDs, checksums, embedding model and
available usage without credentials or private reasoning.

Verification: the final backend suite passed **98 tests, with 4 opt-in tests
skipped**; the default suite excludes paid provider and optional Edge tests.
The frontend's 17 tests and production build passed. Two real-provider chat
samples passed through the local frontend proxy: loan document requirements
returned one citation (4 model calls, 1 tool, 7,431 model tokens); an unpublished
foreign-exchange fee returned `needs_tools` with no fabricated source (5 model
calls, 1 tool, 7,064 model tokens). Saved history and retry deduplication passed.
Evidence is local and ignored: `.artifacts/phase7-live.json`.

Edge desktop/mobile source expansion, real protocol retrieval timeline,
absence of horizontal overflow and browser errors passed with deterministic test
model/embedding responses. Screenshots: `.artifacts/phase7-policy-*.png`.
Docker's initial build hit a temporary Docker Hub DNS error; retry built both
images and the application started successfully. A real-provider Docker chat
then returned a valid document-policy citation through A2A/MCP/Blackboard
(4 model calls, 1 tool, 7,339 model tokens). Docker repeat ingestion embedded zero
chunks. Evidence: `.artifacts/phase7-docker-live.json`. Ruff, dependency checks,
Git whitespace and secret scans passed; original plan hashes are unchanged.
See `docs/TESTING.md` for reproduction commands and final checks.

Limits: fixed small fictional corpus; no upload interface or general web search.
Known instruction-like patterns are rejected and prompts treat passages as data,
but this is not exhaustive injection detection or proof of semantic entailment.
Conflicts use equal section names, so differently worded contradictions need
operator review. The similarity cutoff has smoke-test evidence, not a completed
retrieval benchmark. Embedding token counts were unavailable from the provider
and remain `null`; generative model totals exclude embedding usage. No cloud,
voice, telephone, or 2/3/5 comparative benchmark is claimed.

## Plan 2 Phase 6: ADK/CrewAI banking agents

Implemented on branch `plan2-phase6`. The original plan files remain unchanged.
Phase 6 is included in Git checkpoint `80d3535`. At that checkpoint, Phase 7 was next.

The main configuration has one Google ADK supervisor and four CrewAI specialists:
Account, Card, Loan, and Policy/Support. No hidden manager/planner/reviewer agents
or other agentic frameworks are used. Specialist roles execute only when needed.
An ADK delegation tool uses the official A2A client to consume authenticated Agent
Cards and JSON-RPC task/artifact exchanges with CrewAI executors over real HTTP.
The typed finalization tool validates `SupervisorAnswer` and ends summarization;
protocol adapters and tools are not extra agents.

Ten MCP tools reuse BankSim's ownership-scoped service: account/KYC lookup,
recent transactions, card lookup, pending card block, loan lookup, EMI, eligibility,
pending loan application, support ticket lookup and explicit ticket creation.
Tool arguments/results use Pydantic. Sensitive tools only prepare actions;
confirmation uses the existing exact-parameter, expiry/replay-protected APIs.
Card confirmations now include the server-derived masked number in their payload.

Migrations `0004` and `0005` add PostgreSQL run/artifact/event records and a stable
event sequence. The local database is at `0005`. Blackboard writes check revisions,
consumers record exact artifact IDs/revisions, and identity is server-established.
Service grants are short-lived and bound to customer, run and specialist role;
normal customer JWTs cannot access protocol endpoints. Protocol task lookup is
also grant-scoped and bounded, preventing cross-user/run/role task retrieval.

Callbacks record agent/model/tool flow, validation failures, errors, retries,
artifact publication/consumption, model usage and framework/prompt versions.
Prompts, credentials and private reasoning are not written to application events.
Tool facts come from authenticated service results, never model-supplied data.
Each run allows 20 model calls and 16 successful tool executions, with a default
150-second deadline and two concurrent workflows per API process. Cancellation
revokes subsequent tool/state access. Identical tool requests reuse run receipts;
completed specialists return their existing artifact on delegation replay.

The chat page now exposes an accessible, bounded event timeline and Blackboard
artifacts. Pending actions open a separate review dialog with meaningful banking
details; cancelling changes nothing, while confirming calls the protected API.
The local ignored `.env` has `CHAT_MODE=agents`; `guidance` preserves Phase 5 mode.

Dependency versions tested together: Google ADK 2.12.0, CrewAI 1.15.28, A2A SDK
0.3.26, MCP 1.28.1, Google Gen AI SDK 2.31.0, FastAPI 0.141.1, Pydantic 2.12.5
and OpenTelemetry 1.42.1. CrewAI uses its supported custom `BaseLLM` adapter with
the shared Google SDK. Optional provider-extra conflicts were avoided without
introducing another framework. CrewAI import-time dotenv loading and vendor
telemetry are disabled: Pydantic Settings owns configuration, and traces stay
local. Docker caches the dependency layer separately from source code.

Verification evidence:

- The previous 74-test backend suite continued to pass after dependency changes.
  The expanded suite covers both real frameworks over HTTP with model responses
  mocked, MCP ownership/types/permissions, Blackboard revisions/dependencies,
  task-store isolation, expiry/cancellation, budgets/capacity, protected card/loan
  confirmation, transaction/loan/support tools, and input guardrails. See
  `docs/TESTING.md` for final totals and opt-in commands.
- A live provider workflow invoked **all five roles**, including Account -> Loan
  -> Support artifact consumption. It made 12 model calls and three MCP tool
  executions, recorded 22,493 provider tokens and 82 events, and returned account,
  card and EMI facts matching BankSim. This is one acceptance sample, not a
  comparative benchmark. Evidence: ignored `.artifacts/phase6-live.json`.
- A live Docker request used ADK -> A2A -> CrewAI -> MCP for Account and Loan,
  verified balances against the banking API, calculated EMI **INR 1,066.19**, saved
  history and reused the same response on retry. Ordered events and typed final
  output were verified. Evidence: ignored `.artifacts/phase6-docker-live.json`.
- Edge desktop/mobile exercised real authenticated APIs with test-only model
  responses: shared context/timeline, review/cancel without mutation, and explicit
  card confirmation all passed. Screenshots are in ignored
  `.artifacts/phase6-chat-*.png`. The existing banking browser smoke also passed.
- The frontend's 16 tests and production build passed. Ruff, dependency checks,
  migration/model consistency and Docker build/start passed.
- Final full backend suite: **85 passed, 2 opt-in tests skipped**. The real-provider
  and Edge tests were run separately and passed; they are deliberately skipped in
  the default suite to avoid paid calls and optional-browser dependencies.

Live checks identified two integration issues that were fixed: an Account answer
without tool evidence now fails its output guardrail, and supervisor finalization
uses a typed tool instead of relying solely on final-text JSON formatting. An
environment-isolation regression from framework dotenv auto-loading was also
fixed. Upstream MCP/CrewAI/A2A deprecation/annotation warnings remain non-failing.

Limits: input injection/abuse checks are heuristic, not a claim of exhaustive
attack prevention. Broad safety/performance/cost comparisons are Phase 9. Some
failed runs may leave unconfirmed requests that expire; automatic durable recovery
and exactly-once billing are not implemented. A cancelled external request may
still consume provider usage. At the Phase 6 checkpoint, no verified policy corpus, voice, phone calling,
2/3-agent execution, comparison dashboard, or cloud deployment is claimed here.

## Plan 2 Phase 5: text-chat foundation

Implemented on branch `plan2-phase5`; `plan2-phase4-checkpoint` retains the prior
tracked application. The original two implementation-plan files are unchanged.
Phase 5 publication is tracked in the repository's Git history.

Added a direct Google Gen AI SDK adapter (Gemini), backend-only configuration,
single-attempt bounded provider calls, sanitized errors, Pydantic guidance and
final responses, and model/prompt/run/token/timing metadata. No additional
agent framework is installed; CrewAI/ADK interoperability starts in Phase 6.

Authenticated chat APIs create/list/reopen customer-owned conversations and save
successful exchanges. Migration `0003` adds conversation/turn tables without
changing banking records. The current local database is upgraded to `0003`.
The last ten exchanges form model context, each conversation allows 100 turns,
and question length is bounded to 2,000 characters. Row locking prevents
simultaneous generation in one conversation. Replaying an existing message
ID/text reuses its saved response; changed text with that ID is rejected.

Added Text assistant navigation, provider availability state, saved history,
pagination, plain-text messages, JSON response details, retry handling, and
accessible loading/error/disabled states. Chat has no tools, account access,
policy retrieval, or banking mutation path. Existing banking pages remain usable.

| Verification | Result |
|---|---|
| Backend complete suite with isolated PostgreSQL schemas | 74 passed |
| SDK transport tests | Real SDK serialization/schema parsing exercised through httpx MockTransport; no external model call |
| Chat integration tests | Ownership, persistence/context, retry deduplication, input validation, failure rollback/auditing, context/turn limits, concurrent locking, and throttling passed |
| Ruff and pip check | Passed |
| Frontend behavior tests | 15 passed, including three chat tests |
| Frontend production build | Passed |
| Edge browser smoke | Desktop/mobile existing banking flows and missing-provider/saved-conversation chat flow passed; no browser errors or page overflow |
| Visual inspection | Mobile chat screenshot inspected |
| Migration consistency | Upgrade/downgrade/model comparison passed in isolated schema; local DB at `0003` |
| Docker | Backend/frontend images rebuilt, database/API healthy, frontend proxy/auth/chat availability/history and banking HTTP checks passed |

**Live Phase 5 acceptance passed:** The user supplied provider credentials, stored
only in the ignored root `.env`. Authenticated model discovery succeeded. The
initial model was unavailable to new users; the provider's replacement,
`gemini-3.5-flash-lite`, was verified and configured locally. No key is recorded in
tracked or non-ignored files.

Live testing exposed a protocol mismatch in the SDK's `response_schema` encoding
of Pydantic `additionalProperties`. The adapter now sends
`response_json_schema=Guidance.model_json_schema()` and still validates responses
through Pydantic. A regression assertion checks the actual outgoing JSON-schema
field. All 11 adapter tests and Ruff passed after this fix; no frontend changes
were needed in this follow-up.

Three real end-to-end requests through the Docker frontend proxy and authenticated
API passed: a general EMI explanation, a contextual fictional example, and an
account/card action request. The third response correctly reported `needs_tools`,
directed the user to the banking pages, and claimed no balance or completed action.
Card and loan records remained unchanged. Responses validated against `ChatReply`,
reported 251/347/408 total tokens respectively, and reopened as three persisted
turns. Retrying the first message ID returned the identical saved response.
These token totals are provider usage, not an invoiced cost estimate.

Edge verification reopened the live conversation after refresh, checked all
three replies, and passed desktop/mobile layout and browser-error checks. Evidence
is stored locally in ignored `.artifacts/phase5-live-chat.json`,
`.artifacts/phase5-live-desktop.png`, and `.artifacts/phase5-live-mobile.png`.
The backend Docker image was rebuilt with the schema fix. At the Phase 5
checkpoint, Phase 6 had not started. Broader prompt safety evaluation and cloud deployment
remain later phases. Because the credential was shared in conversation, the user
should rotate it and update local configuration after testing.

Limits: this is a local prototype. Prompt instructions do not guarantee factual
correctness; replies are labeled AI guidance and have no action authority.
Provider billing cannot be exactly-once across a crash after the provider responds
but before a database commit. The throttle is per process; distributed quotas,
full framework tracing/guardrails, retention controls, and cloud session hardening
belong to later Plan 2 phases. A pre-existing Starlette TestClient deprecation
warning remains; it does not fail the suite.

## Repository inspection

Initial workspace contained the specification and review plan only.
No app code, dependencies, tests or workspace AGENTS.md were found.
Existing documents were preserved. Git status could not be established
in the initial sandbox check; no Git initialization or commits performed.
Detected Python 3.11.6, Node 22.14.0, npm 10.9.2, Docker client 29.6.2.
Docker Desktop initially stopped; started for local verification.

## Implemented in Phase 1

FastAPI health/readiness, typed configuration, narrow CORS, request IDs,
bounded PostgreSQL checks, React/Vite/TypeScript/Tailwind workspace,
responsive overview/roadmap, actual service-status checks, Docker Compose,
pgvector initialization, environment template and focused tests.

## Verification

| Check | Result |
|---|---|
| Python install and `pip check` | Passed; no broken requirements |
| `python -m pytest -q` | 4 backend tests passed |
| `python -m ruff check app tests` | Passed |
| `npm.cmd test` | 2 frontend tests passed (Vitest 4.1.11) |
| `npm.cmd run build` | Strict TypeScript and Vite production build passed |
| npm audit after patched dependency installation | 0 reported vulnerabilities |
| `docker compose config --quiet` | Passed |
| `docker compose up -d db` and `docker compose ps` | Database running and healthy |
| Database extension query | vector 0.8.7 enabled on PostgreSQL 16 |
| Live Uvicorn `/health` | HTTP 200, status ok |
| Live Uvicorn `/ready` | HTTP 200, database connected |
| Vite `/api/health` and `/api/ready` | Proxy returns backend health and connected readiness |
| Vite root document | HTTP 200 |

Resolved setup issues: sandbox blocked downloads/build path access;
retried required commands with permission. npm 10 crashed resolving an
upgrade; temporary npm 11 installed patched Vitest without replacing
global npm. Host port 5432 was occupied by an existing service, so BankAI
uses 55432; the existing service/data were not modified. Backend and
frontend dependencies are captured in constraints/lock files.

Verification limitations: no connected browser was available (browser
inventory empty), so visual browser QA and mobile screenshot inspection
were not performed. UI behavior was tested in jsdom, and live serving/proxy
were checked over HTTP. Full backend/frontend Docker builds are supplied
but not verified yet; verified execution uses local Python/Node with the
Docker database. One upstream Starlette warning reports future migration
from httpx to httpx2 in its test client; current tests pass. No provider
integrations or agent performance claims have been made.

## Phase 2 implementation and verification

Implemented ten SQLAlchemy models with UUID keys, relationships,
foreign keys, unique constraints, status/range checks, decimal amounts,
timezone-aware timestamps and lookup indexes. A composite foreign key
prevents a card referencing another customer's account. Added Alembic
revision `0001`, PostgreSQL vector storage, Argon2 demo password hashing,
and a repeatable seed CLI using stable UUIDs and conflict-safe inserts.
An advisory transaction lock serializes concurrent seed invocations.

Seeded the local demo database: 3 customers, 4 accounts, 20 transactions,
4 cards, 3 KYC records, 3 loans, 3 support tickets, 1 audit event,
1 policy document and 1 chunk. Repeated seeding inserted zero rows.
Existing passwords, balances and blocked-card state are preserved.
Policy embeddings remain NULL; retrieval and model integrations are not
implemented. Conversation and pending-action storage belongs to later phases.

Verification: 20 backend tests passed, including 14 PostgreSQL integration
cases and 6 unit/infrastructure tests. Integration tests create randomly
named isolated schemas and remove only those schemas. Checks cover fresh
upgrade/downgrade/re-upgrade, model/migration drift, repeat seed, password
hash verification, decimal/transaction reconciliation, constraints,
cross-customer card linkage and vector storage. `alembic check`, Ruff and
`pip check` passed. The initial test harness exposed migration-version
schema fallback; corrected by explicitly isolating its version table.
Removed only the test-created stale public version marker after verifying
there were no application tables, then migrated and seeded the demo DB.

Docker verification also passed: `docker compose build backend`, then
one-off container runs of `python -m alembic upgrade head` and
`python -m app.seed.demo_data` (zero new inserts). The read-only corpus
mount and container project paths work. Frontend Docker build and visual
browser QA remain outside this phase's verified results. Public demo
counts remained 3 customers / 4 accounts / 20 transactions after tests,
and no `bankai_test_*` schemas remained.

No new banking endpoints or frontend banking pages are claimed. Phase 1
UI stays the foundation shell. Existing Starlette test-client deprecation
warning remains non-failing. No AI provider calls or paid experiments ran.

## Phase 3 implementation and verification

Implemented registration and JWT login, Argon2 password verification,
active-customer identity from signed token claims, ownership-protected
account/balance/transaction/card/KYC/loan/support APIs, strict request and
response schemas, transaction filters/pagination, decimal EMI and explicit
demo eligibility rules. Public registration creates no privileged role.

Migration `0002` adds expiring pending actions. Card blocking and simulated
loan submission require a separate explicit confirmation tied to the exact
action and owner. Confirmations recheck current state, lock rows and commit
action consumption, banking changes and audit events atomically. Repeated
or simultaneous confirmation cannot duplicate a loan or card operation.

Added minimal success/denial audits, consistent sanitized errors, request
IDs, local login throttling, authentication configuration checks, and a
helper that creates a random signing key in ignored `.env` without printing
it. Missing/placeholder signing keys fail closed. No credentials are committed.

Verification includes protected API integration flows, non-disclosing
cross-customer 404s, unknown/invalid/expired JWTs, inactive users, strict
confirmation input, expiry/replay/wrong-action/wrong-owner rejection, changed
card/KYC state, read/write audit evidence, simultaneous loan confirmation
using two independent PostgreSQL connections, and transactional rollback
when an audit write fails. Final run: **57 passed**, one upstream Starlette
deprecation warning; Ruff and dependency checks passed. Alembic reports
revision `0002` at head with no model drift. Test cleanup left zero
temporary `bankai_test_*` schemas. `.env` is confirmed ignored by Git.

Live checks: upgraded local PostgreSQL to `0002`, Alembic found no drift,
Docker backend built and started healthy with the local signing configuration.
Actual HTTP login returned a token (not printed), own-account retrieval
returned two accounts, EMI for INR 12000 at 12% over 12 months returned
1066.19, and `/docs` returned HTTP 200. These are simulated banking checks,
not external bank integrations.

Limits: frontend remains the Phase 1 shell (banking UI is Phase 4); auth
throttling is process-local; no refresh-token/logout revocation flow, MFA,
action cancellation, agent/voice provider or evaluation runtime exists.
The existing Starlette test-client deprecation warning remains non-failing.

## Phase 4 implementation and verification

Implemented the React banking application using existing dependencies and
APIs: login, session restoration/expiry/sign-out, dashboard, account details
and balance refresh, filtered/paged transactions, card blocking, EMI and
demo loan eligibility/application, ticket creation/history/details, and About.
All displayed balances, records and success outcomes come from backend data.
Transaction text search is explicitly limited to the displayed page.

Shared API requests have timeouts, abort stale reads on navigation, and
surface errors with request references. Signing out or receiving a protected
401 removes the tab token and unmounts all customer data. Confirmation dialogs
show exact server-returned details, prevent duplicate submissions, disable
expired actions, contain keyboard focus and restore it on dismissal.
Forms preserve input on errors; writes are never automatically retried.

Verification: **12 Vitest/React Testing Library tests passed**; strict
TypeScript and Vite production build passed. Tests cover login/failed login,
session restoration/expiry/sign-out, stale results, loading/error retry,
empty/filter/pagination states, card cancel/confirm, duplicate/expired
confirmation, bound loan confirmation and support error/success behavior.
No backend behavior changed, so the previously passed 57 backend tests
were not repeated for this phase.

Real-browser QA used installed Edge headless against a new disposable local
PostgreSQL database with its own API/Vite processes. Passed login/refresh,
account refresh, transactions, card cancel/confirm, keyboard return focus,
EMI/eligibility/confirmed loan, ticket creation, all navigation pages at
390px mobile width, customer switching and protected 401 session clearing.
No browser page errors or horizontal page overflow were detected. Desktop
and mobile screenshots were inspected. QA servers and generated databases
were removed; persistent demo records were not reset or changed.

Docker frontend build also passed (npm ci reported zero vulnerabilities).
The container served HTTP 200 on port 5173 and its `/api/ready` proxy
returned a connected database. A combined build initially hit a registry
TLS timeout for the unchanged backend image; building only the frontend
resolved verification without replacing the backend. The temporary frontend
container was stopped after checks; backend/database remain available.
Start the UI with `docker compose up -d frontend`, or use `npm.cmd run dev`.

Resolved verification issues: jsdom lacks native dialog APIs, so tests use
a dialog shim. Browser testing exposed a missing focus return after modal
close; fixed in the shared dialog and confirmed with a keyboard check.
Test locator ambiguities were corrected without changing data behavior.

Limits: browser validation covers Edge only, not Safari/Firefox or a physical
phone. SessionStorage is JavaScript-readable; keep this demo local. Sign-out
does not revoke copied JWTs. Modal Cancel dismisses locally and leaves the
pending server request to expire. Registration UI, AI/voice/evaluation pages
are not part of this phase. No new application dependencies were added;
optional browser QA tools and screenshots are ignored by Git.

## Initial GitHub handoff

On 2026-10-13, created a project-local Git repository on `main` and
configured `origin` as `https://github.com/Dhruvy0804/BankAI.git` at the
user's request. This isolates the project from an existing home-directory
repository. Only project source, documentation, dependency manifests and
lockfiles are included; environments, caches, build output and `.env`
files are excluded.

## Historical Phase 4 handoff

Phase 3 was pushed as commit `0033548`. The user requested the Phase 4
GitHub handoff on 2026-10-14. The renamed specification
`BankAI_Implementation_Plan.md` is preserved and documentation references it.

At that checkpoint, next was Phase 5: configurable LLM adapter and text chat with bounded provider
calls and honest configuration/failure reporting. No AI provider calls or
paid experiments were run during Phase 4.
