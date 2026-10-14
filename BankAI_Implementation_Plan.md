# BankAI --- Full Project Implementation Plan

**Project:** BankAI --- Agentic AI-Powered Voice Banking Assistant\
**Purpose:** Final-year engineering project\
**Mode:** Working local prototype using fictional banking data\
**Current status:** Phased implementation authorized on 2026-10-13.\
**Primary instruction:** This file is the project specification. Follow
`docs/IMPLEMENTATION_PLAN.md`, implement and verify in phases, and keep
`docs/IMPLEMENTATION_STATUS.md` current. Provider-backed benchmarks remain
subject to configured credentials and the agreed execution budget.

------------------------------------------------------------------------

## 1. Instructions

Act as a senior full-stack engineer, AI engineer, backend architect, and
security-conscious developer. Build a complete, runnable
application---not just a plan, mockup, or collection of code snippets.

Before changing files:

1.  Inspect the current repository, folder structure, source files, Git
    status, existing dependencies, and README.
2.  Preserve useful existing work. Do not delete or rewrite unrelated
    code.
3.  Identify the existing implementation and missing components.
4.  Create or update the project documentation listed below.
5.  Implement in small, testable phases. Keep the application runnable
    at the end of every phase.
6.  Run the relevant tests and fix failures before moving on.
7.  Update `docs/IMPLEMENTATION_STATUS.md` after each phase with
    completed tasks, test results, blockers, and next steps.
8.  Do not claim an integration works unless it has been run and
    verified.
9.  If a provider credential is missing, implement its interface and
    document setup. Do not invent credentials or silently simulate a
    real external service.
10. Do not ask the user to paste secrets into source code. Use
    environment variables and `.env.example`.
11. Avoid unnecessary microservices, unnecessary abstractions, and
    overengineering. This is a student project that must be
    understandable, demonstrable, and maintainable.
12. If the repository already has a compatible technology choice,
    inspect it and explain before replacing it. Otherwise use the
    default stack below.

The user has authorized implementation. Inspect the repository, preserve
existing work, and implement in order with a verified checkpoint and
updated status for every phase.

------------------------------------------------------------------------

## 2. Project Objective

BankAI is an agentic AI-powered voice and text banking assistant. Users
can ask questions conversationally, retrieve information from their demo
accounts, ask banking-policy questions, and execute approved operations
in a simulated banking environment.

The system demonstrates:

-   Agentic AI with supervisor-based routing.
-   Specialized account, card, loan, and support workflows.
-   Tool/function calling through controlled backend APIs.
-   Retrieval-Augmented Generation (RAG) for banking policies and FAQs.
-   Real-time voice interaction using LiveKit, STT, and TTS.
-   Actual outbound telephone conversations: an authorized project owner
    starts a test call, the recipient answers on a normal phone, asks
    banking questions, and hears spoken BankAI responses using demo data.
-   Conversation context for follow-up questions.
-   Secure authentication and per-user authorization.
-   Explicit confirmation before sensitive simulated operations.
-   Audit logs, error handling, evaluation, and human-support
    escalation.
-   Docker-based local development and deployment documentation.
-   Controlled evaluation comparing 2-, 3-, and 5-agent configurations
    on the same banking tasks, including their actual outputs, accuracy,
    latency, token usage, and safety behavior. The 5-agent configuration
    is the main project; the smaller configurations are evaluation only.
-   A private web evaluation dashboard for the project owner to run
    comparisons, inspect actual outputs and agent/tool traces, view
    metrics, reopen history, and export evidence for professor review.

### Scope boundary --- mandatory

**BankSim is a simulated banking backend created for this project.** It
uses synthetic customers, fictional account numbers, generated
transactions, and demo balances. It is not an existing bank API and does
not have access to real bank accounts.

Do not connect to real bank accounts, initiate real transactions, or ask
for actual bank credentials, card PINs, passwords, or OTPs. Real banking
integration is out of scope and may be described only as future work
requiring an authorized provider, appropriate eligibility, and customer
consent.

------------------------------------------------------------------------

## 3. Recommended Technology Stack

Use these defaults unless the existing repository has a sound,
documented alternative.

  ---------------------------------------------------------------------------
  Area                    Default                 Responsibility
  ----------------------- ----------------------- ---------------------------
  Frontend                React + Vite +          Web dashboard and chat UI
                          TypeScript

  Styling                 Tailwind CSS            Responsive layout and
                                                  design system

  Voice                   LiveKit                 Real-time audio rooms and
                                                  client connection

  Speech-to-text          Provider adapter        Transcribe user speech

  Text-to-speech          Provider adapter        Speak assistant responses

  LLM                     Configurable provider   Intent understanding and
                          adapter                 response generation

  Agent orchestration     Python + LangGraph      Supervisor and controlled
                                                  workflows

  Backend                 FastAPI                 REST API, business rules,
                                                  authentication

  Database                PostgreSQL              Banking and application
                                                  data

  ORM/migrations          SQLAlchemy + Alembic    Database models and schema
                                                  migration

  Vector retrieval        pgvector with           RAG embedding storage and
                          PostgreSQL              similarity search

  Authentication          JWT access token +      Demo user sessions
                          password hashing

  Backend tests           Pytest                  Unit and integration tests

  Frontend tests          Vitest + React Testing  UI and logic tests
                          Library

  API contract            OpenAPI generated by    API documentation
                          FastAPI

  Local orchestration     Docker Compose          Frontend/backend/database
                                                  services

  Optional cache          Redis                   Only if a demonstrated
                                                  requirement exists
  ---------------------------------------------------------------------------

Keep model, STT, and TTS providers configurable. Prefer a
provider-neutral interface so the project can change providers without
rewriting agent logic.

------------------------------------------------------------------------

## 4. Architecture

### 4.1 Request flow

**Text path:**

React UI → FastAPI authentication and request validation → Supervisor
Agent → specialized agent/workflow → approved tool → BankSim
API/business service → PostgreSQL → response → React UI.

**Voice path:**

React UI ↔ LiveKit room ↔ voice agent ↔ STT → shared supervisor/agent
workflow → approved tool and/or RAG → response text → TTS → LiveKit
audio output.

**Telephone path:**

Owner starts an approved test call → backend creates a scoped demo session
and dispatches the voice worker → SIP telephone provider/LiveKit telephony
calls the recipient → telephone audio enters the LiveKit room → shared
STT/supervisor/tools/RAG workflow → TTS → spoken response over the phone.
The recipient does not need to open the website or enable a browser microphone.

Text and voice must use the same underlying banking tools and business
rules. Text does not require STT/TTS. Voice must not implement separate,
inconsistent banking logic.

### 4.2 Core modules

1.  **Frontend:** Login, dashboard, account cards, transaction list,
    text chat, voice session, confirmation dialogs, support history, and
    settings.
2.  **FastAPI application:** Authentication, user/session context,
    validation, API routing, service layer, audit logging, and error
    handling.
3.  **BankSim:** Simulated customers, accounts, transactions, cards, KYC
    status, loan eligibility, and support tickets.
4.  **Supervisor Agent:** Determines request category, selects a
    workflow, and handles unsupported requests.
5.  **Specialized agents:** Account, Card, Loan, and combined
    Policy/Support. Together with the Supervisor, these are exactly
    5 agents. Policy/RAG and Support/Fraud are two workflows owned by
    the same Policy/Support agent.
6.  **Tool layer:** Typed functions exposed to the LLM and mapped to
    backend services. Never expose raw SQL or unrestricted database
    access.
7.  **RAG pipeline:** Ingest documents, normalize text, chunk, embed,
    retrieve relevant passages, and generate grounded answers with
    source citations.
8.  **Voice layer:** LiveKit connection and configurable STT/TTS
    integrations.
9.  **Security layer:** Authentication, authorization, confirmation
    checks, rate limiting where appropriate, and audit events.
10. **Evaluation layer:** Tests and metrics for task success, tool
    selection, retrieval quality, latency, and error recovery.
11. **Private evaluation dashboard and service:** Owner-only web pages,
    protected APIs, persistent jobs/results, a bounded background worker,
    side-by-side 2/3/5-agent comparisons, history, and report exports.
    The optional CLI uses this same evaluation service.

### 4.3 Architectural rule

The LLM must **never access PostgreSQL directly**. It can call only
registered, typed tools. Each tool must invoke a backend service/API
that validates the authenticated user, ownership, input, and
authorization before reading or changing data.

The frontend must never connect directly to PostgreSQL.

------------------------------------------------------------------------

## 5. Suggested Repository Structure

Adapt to the existing repository rather than duplicating an established
structure.

``` text
bankai/
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── IMPLEMENTATION_STATUS.md
│   ├── ARCHITECTURE.md
│   ├── API_SPEC.md
│   ├── SECURITY.md
│   ├── TESTING.md
│   └── DEMO_GUIDE.md
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── logging.py
│   │   │   └── errors.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── customers.py
│   │   │       ├── accounts.py
│   │   │       ├── transactions.py
│   │   │       ├── cards.py
│   │   │       ├── kyc.py
│   │   │       ├── loans.py
│   │   │       ├── support.py
│   │   │       ├── chat.py
│   │   │       ├── rag.py
│   │   │       └── voice.py
│   │   ├── db/
│   │   │   ├── session.py
│   │   │   └── base.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── account_service.py
│   │   │   ├── card_service.py
│   │   │   ├── loan_service.py
│   │   │   ├── support_service.py
│   │   │   └── audit_service.py
│   │   ├── agents/
│   │   │   ├── graph.py
│   │   │   ├── supervisor.py
│   │   │   ├── state.py
│   │   │   ├── prompts.py
│   │   │   ├── workflows/
│   │   │   └── tools/
│   │   ├── rag/
│   │   │   ├── ingestion.py
│   │   │   ├── chunking.py
│   │   │   ├── embeddings.py
│   │   │   ├── retrieval.py
│   │   │   └── answer.py
│   │   ├── voice/
│   │   │   ├── livekit_agent.py
│   │   │   ├── providers.py
│   │   │   └── session.py
│   │   └── seed/
│   │       └── demo_data.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── evals/
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── app/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   │   ├── auth/
│   │   │   ├── dashboard/
│   │   │   ├── chat/
│   │   │   ├── voice/
│   │   │   ├── accounts/
│   │   │   ├── transactions/
│   │   │   └── support/
│   │   ├── services/
│   │   ├── hooks/
│   │   ├── types/
│   │   └── tests/
│   └── public/
└── data/
    └── banking_policies/
        ├── README.md
        └── sample_policy.md
```

The exact structure may be adjusted when needed, but maintain clear
separation of API routes, business logic, database models, agent tools,
RAG, and voice integration.

------------------------------------------------------------------------

## 6. Database Design

Use PostgreSQL with SQLAlchemy models and Alembic migrations. Store
monetary values using `NUMERIC`/decimal types, not binary floating
point. Add primary keys, foreign keys, indexes, timestamps, and
constraints where appropriate.

### 6.1 Tables

#### `customers`

-   `id`: UUID primary key
-   `full_name`
-   `email`: unique
-   `password_hash`
-   `phone`: fictional/demo value
-   `created_at`
-   `is_active`

#### `accounts`

-   `id`: UUID primary key
-   `customer_id`: foreign key to customers
-   `account_number`: fictional masked/display-safe identifier; unique
    in demo data
-   `account_type`: savings/current
-   `currency`: default INR
-   `balance`: decimal/numeric
-   `status`
-   `created_at`

#### `transactions`

-   `id`: UUID primary key
-   `account_id`: foreign key to accounts
-   `transaction_type`: credit/debit
-   `amount`: decimal/numeric
-   `description`
-   `merchant`: fictional when applicable
-   `reference_code`: fictional unique identifier
-   `status`
-   `occurred_at`

#### `cards`

-   `id`: UUID primary key
-   `customer_id`: foreign key
-   `account_id`: optional foreign key
-   `masked_card_number`: demo-only masked value
-   `card_type`
-   `status`: active/blocked/expired
-   `expiry_month` and `expiry_year`: fictional values only
-   `created_at`

Never store a real full card number, CVV, PIN, or payment credential.

#### `kyc_records`

-   `id`
-   `customer_id`
-   `status`: pending/verified/rejected
-   `last_updated`
-   `notes`: non-sensitive demo notes only

Do not store actual Aadhaar, PAN, identity document scans, or other real
identity data.

#### `loans`

-   `id`
-   `customer_id`
-   `loan_type`
-   `requested_amount`
-   `annual_interest_rate`
-   `tenure_months`
-   `status`: simulated status
-   `created_at`

#### `support_tickets`

-   `id`
-   `customer_id`
-   `category`
-   `subject`
-   `description`
-   `status`
-   `priority`
-   `created_at`
-   `updated_at`

#### `audit_logs`

-   `id`
-   `customer_id`: nullable for system events
-   `action`
-   `resource_type`
-   `resource_id`
-   `outcome`
-   `request_id`
-   `created_at`

Audit logs must not store passwords, tokens, secrets, raw card data, or
unnecessary sensitive conversation content.

#### `policy_documents` / `policy_chunks`

Store document metadata, chunk text, source, page/section if available,
checksum, embedding, and ingestion timestamps. Use pgvector for vector
embeddings. If combining document metadata and chunks in separate tables
makes the first version unnecessarily complex, use a single chunk table
with document metadata fields and document that decision.

#### Optional `conversations` / `messages`

Store conversation metadata and limited message history if persistence
is needed. Apply user ownership checks, retention rules, and avoid
persisting sensitive personal information by default.

### 6.2 Demo seed data

Create a repeatable seed command that generates: - Several fictional
demo customers. - One or more accounts per customer. - A variety of
fictional credits and debits across dates. - Active and blocked demo
cards. - Multiple KYC states. - Sample loan scenarios. - Support tickets
in different statuses.

Use obvious demo-only names and identifiers. Ensure seed execution does
not duplicate data on every run. Document demo credentials in local
development documentation only. Use non-production credentials and
require a safe setup for any publicly deployed instance.

------------------------------------------------------------------------

## 7. Authentication and Authorization

Implement authentication before account-specific AI tools.

Requirements: 1. Registration or seeded demo login. 2. Password hashing
with a standard password-hashing library. 3. JWT access tokens with
expiry. 4. Protected FastAPI routes. 5. Authenticated customer identity
must come from verified server-side token claims---not from an
LLM-supplied customer ID or arbitrary frontend request field. 6. Each
customer can access only their own accounts, cards, transactions, KYC,
loans, and support tickets. 7. Validate input with Pydantic. 8. Return
consistent HTTP errors without exposing stack traces or secrets. 9. Add
appropriate CORS configuration from environment settings. 10. Add rate
limiting or login throttling if feasible for the deployment. 11. Do not
put API keys or secrets in the frontend bundle. 12. Never log
authorization headers or tokens.

Use explicit authorization checks at the service/API layer even if the
frontend hides inaccessible controls.

------------------------------------------------------------------------

## 8. BankSim REST API

Create versioned endpoints under `/api/v1`. Use FastAPI's generated
OpenAPI docs. Return consistent response schemas and meaningful HTTP
status codes.

### 8.1 Authentication

-   `POST /api/v1/auth/register`
-   `POST /api/v1/auth/login`
-   `GET /api/v1/auth/me`

### 8.2 Customers and accounts

-   `GET /api/v1/customers/me`
-   `GET /api/v1/accounts`
-   `GET /api/v1/accounts/{account_id}`
-   `GET /api/v1/accounts/{account_id}/balance`
-   `GET /api/v1/accounts/{account_id}/transactions`

### 8.3 Transactions

-   `GET /api/v1/transactions/{transaction_id}`
-   `GET /api/v1/transactions?account_id=...&limit=...&cursor=...`

Validate ownership, pagination, and filters. Never accept an arbitrary
customer ID as sufficient authorization.

### 8.4 Cards

-   `GET /api/v1/cards`
-   `GET /api/v1/cards/{card_id}`
-   `POST /api/v1/cards/{card_id}/block`

Card blocking is a simulated, sensitive action. Require authentication,
ownership validation, a pending confirmation/approval state, and a final
server-side confirmation before updating the demo database. Do not let a
model tool call bypass this workflow.

### 8.5 KYC

-   `GET /api/v1/kyc/status`

Return only the authenticated customer's demo KYC status.

### 8.6 Loans

-   `POST /api/v1/loans/eligibility`
-   `POST /api/v1/loans/emi`
-   `POST /api/v1/loans/applications`
-   `GET /api/v1/loans`

Loan eligibility must be a transparent demo rule, not a claim of real
credit approval. Application submission must be explicitly confirmed and
marked simulated.

EMI formula:

`EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)`

where `P` is principal, `r` is monthly interest rate as a decimal, and
`n` is number of monthly instalments. Handle zero interest separately.
Validate positive principal, sensible tenure, and reasonable rate
bounds.

### 8.7 Support

-   `POST /api/v1/support/tickets`
-   `GET /api/v1/support/tickets`
-   `GET /api/v1/support/tickets/{ticket_id}`

### 8.8 AI chat and RAG

-   `POST /api/v1/chat`
-   `GET /api/v1/rag/health`
-   `POST /api/v1/rag/ingest` --- development/admin protected only;
    never open to anonymous users.

### 8.9 Voice

-   `POST /api/v1/voice/token` --- authenticated endpoint that returns a
    short-lived LiveKit room token for the current user and authorized
    room.
-   Optional session status/metadata endpoints if needed.

Never expose LiveKit API secret to the browser. Restrict room identity
and permissions. The token endpoint must authenticate the user and
enforce room access.

Planned owner-only telephone endpoints:
- `POST /api/v1/phone/calls`: explicitly start one allowlisted test call
  with validated demo context and a request idempotency key.
- `GET /api/v1/phone/calls` and `GET /api/v1/phone/calls/{call_id}`:
  owner-scoped call status, masked destination and permitted test evidence.
- `POST /api/v1/phone/calls/{call_id}/end`: end an active call safely.

Provision owner permissions through trusted local setup before these routes
are enabled; ordinary registration cannot grant calling privileges. Never
expose SIP credentials or let an LLM choose a number and initiate calls.

### 8.10 Private evaluation APIs

Restrict every endpoint to a locally provisioned owner/evaluator role
and verify run ownership. Ordinary banking users must not be able to
start evaluations or read results, traces, or exports.

- `GET /api/v1/evaluations/scenarios`: available versioned scenarios.
- `POST /api/v1/evaluations/runs`: validate settings, enqueue a job,
  return HTTP 202 and run ID; prevent duplicate submissions.
- `GET /api/v1/evaluations/runs`: saved run history.
- `GET /api/v1/evaluations/runs/{run_id}`: status, progress and summary.
- `GET /api/v1/evaluations/runs/{run_id}/results`: paginated outputs,
  checks, metrics and sanitized agent/tool events.
- `POST /api/v1/evaluations/runs/{run_id}/cancel`: request safe cancellation.
- `POST /api/v1/evaluations/runs/{run_id}/followups`: validated input for
  pending interactive clarification or confirmation steps.
- `POST /api/v1/evaluations/runs/{run_id}/reviews`: rubric scores/notes.
- `GET /api/v1/evaluations/runs/{run_id}/export?format=csv|json|html`:
  sanitized downloadable data or printable report.

Implement shared schemas and execution logic for web and CLI. Validate
variants, repetition limits, concurrency, provider settings and budgets
on the server. Keep credentials server-side. Owner privileges cannot be
self-assigned through ordinary registration.

### 8.11 Health

-   `GET /health`
-   `GET /ready`

`/health` should indicate process health. `/ready` should check required
dependencies such as database availability without leaking credentials.

------------------------------------------------------------------------

## 9. Agentic AI Design

Implement a controlled agentic system with a supervisor and specialized
workflows. Agents may be implemented as graph nodes or focused workflow
functions; they do not need to be separate autonomous services.

### 9.1 Supervisor Agent

The main project has **5 total agents, including the Supervisor**.
An agent means a distinct LLM-backed role with its own instructions and
tool permissions. Workflow nodes, tool functions, RAG retrieval,
confirmation handlers, and STT/TTS adapters are not additional agents.
The voice adapter must forward requests into this same system rather
than introduce another decision-making agent.

Responsibilities: 1. Understand the request and conversation context. 2.
Classify intent. 3. Select a suitable workflow. 4. Ask a clarification
question if key information is missing. 5. Call only allowed tools. 6.
Handle tool failures and invalid results. 7. Explain the result in
simple language. 8. Refuse unsupported or unsafe operations and escalate
when appropriate.

Suggested intents: - `account_balance` - `transaction_history` -
`transaction_explanation` - `card_information` - `block_card` -
`kyc_status` - `loan_eligibility` - `emi_calculation` -
`loan_application` - `banking_policy` - `support_ticket` -
`fraud_or_dispute` - `general_banking_question` - `unknown`

Do not rely exclusively on free-form LLM output for authorization or
operation execution. Validate tool names, arguments, schemas, and
workflow state.

### 9.2 Specialized workflows

There are four specialist agents: Account, Card, Loan, and
Policy/Support. The Policy/Support agent owns both policy retrieval and
support/fraud workflows described below; do not instantiate separate
Policy and Support agents in the main system.

#### Account Agent

-   Fetch account list.
-   Retrieve balance.
-   Retrieve recent transactions.
-   Explain a transaction using only returned records.
-   Never invent balances, transaction records, or account details.

#### Card Agent

-   List the customer's demo cards.
-   Retrieve status of an authorized card.
-   Begin card-block workflow.
-   Request explicit confirmation before final simulated blocking.
-   Recheck user ownership and pending action state on the server before
    committing.

#### Loan Agent

-   Collect necessary demo application inputs.
-   Calculate EMI.
-   Call simulated eligibility rules.
-   Retrieve applicable policy passages through RAG.
-   Explain that eligibility is a demo result.
-   Ask for confirmation before simulated application submission.

#### Policy/Support Agent: policy and RAG workflow

-   Retrieve relevant passages from ingested banking-policy documents.
-   Answer only to the extent supported by retrieved content and general
    safe context.
-   Include source titles or section identifiers.
-   If retrieval is weak or documents do not support an answer, say so
    and offer support escalation.
-   Do not invent policy citations.

#### Policy/Support Agent: support and fraud workflow

-   Help categorize a reported issue.
-   Retrieve the customer's demo transactions if needed.
-   Create a support/dispute ticket after confirming the user's intent.
-   Escalate urgent, ambiguous, or high-risk cases.
-   Do not make definitive fraud accusations based on a demo heuristic.

### 9.3 Tool calling

Implement typed, narrowly scoped functions such as: -
`list_my_accounts()` - `get_my_balance(account_id)` -
`get_my_transactions(account_id, limit)` -
`get_my_card_status(card_id)` - `request_card_block(card_id)` -
`confirm_card_block(action_id, confirmation)` - `get_my_kyc_status()` -
`calculate_loan_emi(principal, annual_rate, tenure_months)` -
`check_demo_loan_eligibility(inputs)` -
`request_loan_application(inputs)` -
`confirm_loan_application(action_id, confirmation)` -
`search_banking_policies(question)` -
`create_support_ticket(category, subject, description)` -
`get_my_support_tickets()`

Tool names are examples; adjust as required. Every tool must be typed,
documented, tested, and backed by authorized server-side logic. Pass the
verified customer context from the authenticated request into the tool
execution context. Never let the model select another customer's
identity.

### 9.4 Agent state and memory

Use a typed state object containing only what is necessary, for
example: - conversation/session ID - authenticated customer ID from
trusted server context - current intent - minimal conversation history -
workflow stage - validated tool result - pending confirmation action
ID - source references for RAG - escalation status

Conversation memory is for context, not permission. It must never
replace authentication, ownership checks, or fresh authorization.

### 9.5 Error handling

-   If a tool fails, report that the operation could not be completed.
-   Do not fabricate a successful result.
-   Retry only safe, idempotent operations and use bounded retry counts.
-   Do not automatically repeat a sensitive write operation.
-   Return a trace/request ID for debugging.
-   Keep stack traces and provider secrets out of user-facing errors.
-   Escalate after repeated failures or when the assistant cannot safely
    resolve the request.

------------------------------------------------------------------------

## 10. RAG Implementation

Build a working Retrieval-Augmented Generation pipeline for banking FAQs
and policy information.

### 10.1 Ingestion

1.  Support Markdown and plain-text files initially.
2.  Add PDF ingestion only if it can be tested reliably.
3.  Extract text and normalize whitespace.
4.  Split content into configurable chunks with modest overlap.
5.  Preserve document title, source filename, section, chunk index,
    checksum, and ingestion time.
6.  Generate embeddings using a configurable embedding provider.
7.  Store chunk text and embeddings in pgvector.
8.  Make ingestion repeatable and prevent duplicate chunks using a
    document checksum or equivalent stable key.
9.  Restrict ingestion to authenticated administrators/development
    users.

### 10.2 Retrieval

-   Embed the user's question.
-   Retrieve top-k relevant chunks by vector similarity.
-   Apply sensible similarity filtering.
-   Return source metadata with each passage.
-   Optionally add keyword search later if it improves retrieval.
-   Do not claim retrieval confidence is calibrated unless it has been
    evaluated.

### 10.3 Answer generation

-   Provide retrieved passages as context to the model.
-   Instruct the model to answer only what the context supports.
-   Treat document content as untrusted data, not instructions to
    execute tools.
-   Cite source titles/sections in the response.
-   State clearly when the documents do not contain an answer.
-   Offer support-ticket creation or escalation when appropriate.

### 10.4 Starter corpus

Create clearly labelled **synthetic demo policy documents**, not fake
claims about a real bank. Include examples such as: - Demo
savings-account overview. - Example card-blocking process. - Example
loan-document checklist. - Example loan eligibility terms. - Example
dispute and support process. - Example KYC workflow.

Mark the corpus as educational/sample material and not official
financial advice or a real institution's policy.

### 10.5 RAG evaluation

Create a small labelled evaluation set containing questions, expected
source documents, and expected answer points. Track: - Retrieval hit
rate or Recall@k. - Whether citations point to retrieved sources. -
Answer groundedness judged against expected facts. - Correct refusal
when the corpus lacks an answer.

------------------------------------------------------------------------

## 11. LiveKit Voice Integration

Implement voice after the text chat and core banking APIs work.

### 11.1 Voice user experience

-   Start and end a voice session.
-   Show connection status.
-   Show microphone permission/error states.
-   Display partial/final transcripts where supported.
-   Display assistant text alongside spoken output.
-   Support interruptions/barge-in if the selected LiveKit/provider
    configuration supports it.
-   Handle reconnects and session failures gracefully.
-   Offer text chat as a fallback.

### 11.2 Technical requirements

1.  Use the official LiveKit SDK and current supported agent/client APIs
    for the installed version.
2.  Pin compatible package versions and document them.
3.  Create a provider adapter for STT and TTS.
4.  Use environment variables for LiveKit URL, API key, API secret, and
    provider credentials.
5.  Generate short-lived room tokens only from the authenticated
    backend.
6.  Keep LiveKit secrets on the server.
7.  Use the same supervisor and tool layer for voice and text.
8.  Handle STT errors, empty transcripts, timeouts, TTS failures, and
    disconnects.
9.  Never interpret uncertain speech as authorization to perform a
    sensitive action.
10. If speech recognition is ambiguous for a sensitive request, ask the
    user to repeat or use text confirmation.

### 11.3 Provider configuration

Create a provider abstraction and document the selected implementation.
If provider credentials are absent, show a clear "voice provider not
configured" message and keep text mode functional. Do not present a fake
audio response as a working voice integration.

------------------------------------------------------------------------

### 11.4 Actual outbound telephone calling

Actual calling is required by the user's scope update. Implement it after
browser voice works, using LiveKit SIP telephony and a compatible telephone
provider with an outbound trunk and provisioned caller number. Confirm
number availability, permitted destinations, account/trial restrictions and
pricing during setup; do not assume a local deployment alone can dial phones.
Provider choice remains open until these requirements and the budget are known.

Use the official [outbound workflow](https://docs.livekit.io/telephony/making-calls/workflow-setup/)
and [call initiation API](https://docs.livekit.io/telephony/making-calls/outbound-calls/).
Start the voice worker/room before dialing. The SIP participant carries
telephone audio into the same five-agent banking system; it is not a sixth
decision-making agent. Telephone and browser voice share tools, RAG,
confirmation, clarification and escalation logic.

**Owner and recipient experience:**

1. The owner opens a private Phone Test page, selects an authorized fictional
   customer/session and an allowlisted destination, and explicitly starts
   a single call. Display estimated usage and maximum duration before dialing.
2. The recipient answers a normal phone call. BankAI introduces itself as
   an AI educational banking demo, explains that data is fictional, and asks
   whether the recipient wants to continue. No account details are spoken
   before acceptance. Voicemail must receive no banking information.
3. The recipient asks questions naturally, such as balance, recent
   transactions, policy requirements or EMI. The system listens, invokes
   the shared authorized workflow and speaks verified answers.
4. Sensitive simulated actions are described aloud and bound to one exact,
   expiring pending action. Require a fresh, unambiguous confirmation in
   that call/session; ambiguous speech triggers clarification. DTMF can
   provide an explicit confirmation where the integration supports it.
5. The recipient or owner can end the session. The UI shows dialing,
   ringing, active, ended, failed, cancelled, busy or unanswered outcomes
   based on provider events, never a fabricated success state.

**Access, lifecycle and evidence:**

- Bind each call to a server-issued, limited demo-session grant derived
  from the initiating user's authorized fixture. A phone number/caller ID
  is not authentication; the model cannot pick another customer. This is
  an invited synthetic-account demo, not phone authentication for real banking.
- Permit only individually approved/allowlisted test destinations. Validate
  E.164 numbers server-side, limit concurrency/duration/attempts and enforce
  the agreed spend limit. No bulk calls or automatic redialing.
- Store credentials in environment configuration. Mask phone numbers in
  UI/history/logs and avoid persisting full destination numbers in transcripts.
- Validate event origin using the supported provider/LiveKit verification
  mechanism. Handle duplicate, delayed and out-of-order events idempotently;
  an end/cancel request during dialing must not leave a later-connected call alive.
- On recipient disconnect, reject queued confirmations, invalidate the
  session grant, stop the worker and clean up the room/telephone participant.
  Enforce inactivity and maximum-call-duration timeouts.
- Raw audio recording is off by default. If saving a transcript for the
  professor's review, explain it at call start and honor the agreed choice;
  retain only permitted sanitized evidence. Never save private model reasoning.
- Missing credentials, insufficient provider balance or denied destinations
  return clear unavailable/failure states. Browser voice and text remain usable.

**Verification:** test ownership/allowlist checks, number validation,
idempotent call start, busy/no-answer/provider failure, event verification,
cancel-versus-connect races, disconnect cleanup, and expired/replayed spoken
confirmation using provider test fixtures. Then run one agreed, funded live
test call to an authorized number and verify two-way speech and tool results.
Do not claim real calling works until that live test has completed.

Inbound public telephone service is not required for this outbound professor
demo and remains future scope. Keep the primary 2/3/5-agent experiment in
text; phone quality/latency is a separate demonstration to avoid audio confounds.

------------------------------------------------------------------------

## 12. Frontend Requirements

Build a polished, responsive, accessible interface suitable for a
final-year project demo.

### 12.1 Pages

The application has a banking area that always uses the main 5-agent
system and a separate private evaluation area for the project owner.
Add **Evaluation** navigation only for authorized users, backed by
server-side access control. Its required screens are specified in
Section 15.2; it is part of the delivered web application.

1.  **Login:** Demo sign-in, validation, useful errors.
2.  **Dashboard:** Account summary, masked demo account identifier,
    available balance, recent transactions, quick actions.
3.  **AI Assistant:** Text conversation, loading state, source
    citations, tool/action result cards, follow-up questions.
4.  **Voice Assistant:** LiveKit connect/disconnect, microphone state,
    transcript, assistant response, voice error states.
    Add a separate owner-only **Phone Test** page for starting one actual
    call, monitoring its status and ending it. The callee uses their phone.
5.  **Transactions:** Search/filter, type, date, amount, status.
6.  **Cards:** List demo cards and their status; initiate simulated
    block flow.
7.  **Loans:** EMI calculator, simulated eligibility, loan application
    workflow.
8.  **Support:** Create ticket and review ticket history.
9.  **Settings/About:** Demo-only notice, technology stack,
    privacy/scope note.

### 12.2 UX details

-   Use a consistent navigation system and design tokens.
-   Make the interface work on desktop and mobile widths.
-   Use loading, empty, success, and error states.
-   Clearly distinguish demo data from real data.
-   Display monetary amounts with INR formatting when currency is INR.
-   Do not display raw internal IDs as primary user-facing labels.
-   Show RAG sources in a compact expandable area.
-   Use a confirmation modal for sensitive simulated actions.
-   Never rely on hidden UI controls as a security mechanism.
-   Include keyboard accessibility and meaningful labels.
-   Do not hardcode fake balances in React; fetch them from the backend.

### 12.3 AI chat interaction

-   Keep user and assistant messages visually distinct.
-   Render tool results as structured cards where helpful.
-   Show when the assistant is retrieving information or processing a
    request.
-   Support retry after recoverable errors.
-   Prevent accidental duplicate message submissions.
-   Provide a clear disclaimer that BankAI is a demo using fictional
    data.

------------------------------------------------------------------------

## 13. Security and Safety Requirements

These are mandatory, not optional polish.

1.  Use fictional data only.
2.  Never request real bank passwords, PINs, OTPs, CVVs, or credentials.
3.  Enforce server-side authentication and ownership checks on every
    account-specific operation.
4.  The model cannot choose or override the authenticated customer ID.
5.  The model has no direct database connection or unrestricted SQL
    capability.
6.  Validate all tool arguments with strict schemas and server-side
    business rules.
7.  Require an explicit confirmation step for card blocking and
    simulated loan submission.
8.  A confirmation must be tied to the exact pending action,
    authenticated user, and expiry time. Do not accept an old or
    unrelated "yes" as confirmation.
9.  Revalidate ownership and action state when committing a sensitive
    action.
10. Add audit events for sensitive reads/writes and failed authorization
    attempts, while minimizing personal data.
11. Never log tokens, passwords, secrets, or unnecessary sensitive
    message content.
12. Keep `.env` out of version control. Provide `.env.example` with
    placeholder values only.
13. Configure CORS narrowly for known development origins.
14. Use dependency versions that are compatible and document setup.
15. Treat retrieved documents, user prompts, and model outputs as
    untrusted input.
16. Prevent prompt injection in RAG content from overriding system
    instructions or granting new tool permissions.
17. Do not execute arbitrary code or arbitrary SQL generated by the LLM.
18. Add bounded timeouts and retries to external provider calls.
19. Do not expose verbose exception details in production responses.
20. Clearly label all account, card, transaction, loan, and KYC data as
    simulated.

------------------------------------------------------------------------

## 14. Implementation Phases and Acceptance Criteria

Implement in the following order. Do not jump ahead to voice or
multi-agent complexity before the core banking APIs work.

### Phase 0 --- Repository inspection and plan

Tasks: - Inspect the repository and existing code. - Write the
implementation, architecture, API, security, testing, and demo
documentation. - Set up task tracking.

Acceptance: - Existing work is preserved. - Decisions and phase
checklist are documented. - The project can be run using documented
commands or missing prerequisites are explicitly identified.

### Phase 1 --- Project scaffolding and local environment

Tasks: - Create backend and frontend scaffolds. - Configure Python
dependencies and frontend scripts. - Add environment configuration and
`.env.example`. - Add Docker Compose for PostgreSQL with pgvector where
available. - Add backend health endpoints. - Add a minimal frontend
shell.

Acceptance: - Backend starts. - Frontend starts. - Database is
reachable. - Health endpoints return correct status. - No secrets are
committed.

### Phase 2 --- Database, migrations, and demo data

Tasks: - Implement SQLAlchemy models and relationships. - Create Alembic
migrations. - Implement repeatable seed data. - Add database constraints
and indexes.

Acceptance: - A fresh database migrates successfully. - Seed command can
run repeatedly without duplicating records. - Tests verify relationships
and basic data integrity.

### Phase 3 --- Authentication and BankSim APIs

Tasks: - Implement login and authenticated customer identity. - Add
account, transaction, card, KYC, loan, and support endpoints. -
Implement service/repository separation where useful. - Enforce
authorization and ownership. - Implement card-block and loan-application
pending-confirmation workflows. - Add audit logging.

Acceptance: - Authenticated demo users can retrieve their own data. -
One user cannot retrieve another user's records by changing IDs. -
Invalid input returns proper validation errors. - Sensitive simulated
operations cannot execute without a valid confirmation. - API
integration tests pass.

### Phase 4 --- Frontend banking dashboard

Tasks: - Implement login and session handling. - Connect UI to real
BankSim API endpoints. - Build dashboard, accounts, transactions, cards,
loans, and support pages. - Add loading/error/empty states.

Acceptance: - The UI displays data fetched from the backend, not
hardcoded balances. - A user can navigate all implemented pages. - API
failures are handled clearly. - Responsive layout and core UI tests
pass.

### Phase 5 --- Text chat and LLM provider interface

Tasks: - Implement a configurable LLM adapter. - Add `/api/v1/chat`. -
Define request/response schemas and conversation state. - Implement a
minimal safe assistant response flow. - Add timeouts, error handling,
and provider configuration checks.

Acceptance: - Text chat works with the configured provider. - Missing
credentials result in a clear error or documented safe fallback. - The
assistant does not claim a banking operation succeeded without a
verified tool result.

### Phase 6 --- Agent orchestration and tool calling

Tasks: - Implement typed agent state. - Build supervisor intent
routing. - Implement Account, Card, Loan, Policy, and Support
workflows. - Register narrow typed tools. - Connect tools to backend
services. - Add clarification, action confirmation, and escalation
logic. - Persist minimal conversation context where needed.

Acceptance: - Balance requests use the account tool. - Transaction
requests use the transaction tool. - Policy requests use RAG when
available. - Card blocking cannot bypass confirmation. - Tool errors are
communicated accurately. - Tests verify routing and sensitive-action
workflow states.

The main graph must contain exactly 5 agents: Supervisor, Account,
Card, Loan, and Policy/Support. Its two policy and support workflows
belong to one specialist agent.

### Phase 7 --- RAG

Tasks: - Implement document ingestion, chunking, embeddings, storage,
and retrieval. - Add synthetic sample policy corpus. - Implement
grounded answer generation and source metadata. - Add protected
ingestion endpoint or CLI command. - Add RAG evaluation cases.

Acceptance: - Sample documents can be ingested reproducibly. - Relevant
queries retrieve expected documents in tests. - Responses cite actual
retrieved sources. - Unsupported questions produce an explicit
limitation rather than fabricated policy.

### Phase 8 --- LiveKit and voice

Tasks: - Add authenticated LiveKit token endpoint. - Build voice session
UI. - Integrate STT/TTS providers through adapters. - Connect voice to
the same supervisor/tool layer. - Add connection, interruption, timeout,
and provider-error handling.

Split delivery into Phase 8A browser voice and Phase 8B actual outbound
telephone calling per Section 11.4. Phase 8B adds owner controls, provider/
SIP configuration, scoped call grants, status events, limits, cleanup and
an approved live professor/test-recipient call.

Acceptance: - A configured environment can establish a real LiveKit
voice session. - Speech is transcribed and responses can be spoken. -
Voice and text use the same banking authorization rules. - If voice
credentials are missing, text remains functional and the UI reports the
missing configuration honestly.

Additional acceptance: a configured telephone provider places one actual
call to an approved test number; the recipient asks questions and receives
spoken, tool-backed answers. Owner access, recipient acceptance, action
confirmation and hang-up cleanup are verified. Missing telephone credentials
are reported as unavailable. Call output is not passed off as measured
2/3/5-agent benchmark evidence.

### Phase 9 --- Observability, evaluation, and quality

Tasks: - Add structured logs and request IDs. - Add unit and integration
tests. - Add agent routing evaluation cases. - Add RAG evaluation
cases. - Measure basic latency and task success. - Add linting,
formatting, and frontend tests. - Test unauthorized access, provider
failure, database failure, and malformed inputs.

Acceptance: - Documented test commands pass. - Failures can be traced by
request ID without exposing secrets. - Evaluation results are documented
with methodology and limitations. - No unsupported performance or
accuracy claims are made.

Phase 9 also includes the comparative experiment in Section 15.1.
Implement it in three steps: 9A shared evaluation engine, isolated
fixtures, persistent jobs and protected API; 9B private web dashboard,
history, scoring and exports; 9C controlled benchmark and quality checks.
The dashboard must support running a comparison from the browser,
refreshing/reopening progress, inspecting outputs and observed traces,
cancelling safely, and exporting saved results. Test access controls,
fixture isolation, duplicate submission, interrupted jobs, budget limits,
partial results, unscored prompts, and consistency of exported metrics.
Build the 2-agent and 3-agent evaluation graphs only after the main
5-agent system and shared tools work. Record actual outputs and measured
results for all three configurations; do not replace the main system
based on an assumed or measured ranking without discussing scope changes
with the user.

### Phase 10 --- Deployment and final demonstration

Tasks: - Complete Docker Compose for local deployment. - Add startup,
migration, seed, and shutdown instructions. - Verify `.env.example`. -
Write demo walkthrough and known limitations. - Prepare architecture
diagram and project explanation for viva.

Acceptance: - A new developer can follow the README to run the app. -
The demo works using synthetic data. - Setup errors and missing
credentials are documented. - The final report clearly distinguishes
implemented features from future work.

------------------------------------------------------------------------

## 15. Testing Plan

### Backend unit tests

-   EMI calculation, including zero interest and invalid values.
-   Authentication helpers and token expiry.
-   Account ownership checks.
-   Card-block workflow state transitions.
-   Loan eligibility demo rules.
-   Transaction filters and pagination.
-   RAG chunking and citation metadata.
-   Agent routing for representative intents.

### Backend integration tests

-   Login → account list → balance.
-   Login → transactions.
-   Cross-customer access attempts return 403 or a consistent
    non-disclosing 404 policy.
-   Card block without confirmation fails safely.
-   Card block with valid, current confirmation succeeds in the
    simulated system.
-   Invalid or expired action ID fails.
-   Loan submission requires confirmation.
-   Support ticket creation and retrieval.
-   Database unavailable and LLM provider unavailable cases.

### Frontend tests

-   Login validation.
-   Dashboard loading/error/empty states.
-   Chat message submission.
-   Voice connection error display.
-   Confirmation dialog behavior.
-   Rendering of retrieved source citations.
-   No hardcoded production-like balances.

### Agent/RAG evaluation

Create a fixed test dataset of questions and expected behavior.
Include: - Balance intent routes to account tools. - Transaction intent
routes to transaction tools. - Policy intent uses retrieval. - Ambiguous
request triggers clarification. - Unauthenticated request cannot access
protected data. - Prompt injection in retrieved content does not enable
unauthorized tools. - Unsupported policy questions result in a
limitation statement. - Sensitive action requests require confirmation.

Do not use an LLM's self-reported confidence as the sole evaluation
metric. Record actual expected-versus-observed results.

------------------------------------------------------------------------

### 15.1 Comparative evaluation: 2, 3, and 5 total agents

**Purpose:** Investigate how grouping the same banking responsibilities
into different numbers of agents affects response quality, task
completion, safety, latency, and resource usage. The supervisor counts
as an agent in every configuration. The main application always defaults
to 5 total agents; the 2-agent and 3-agent graphs are evaluation-only
variants selected in the private web evaluation dashboard. The dashboard
and optional local CLI both invoke one shared backend evaluation service.

| Configuration | Agent roles | Use |
|---|---|---|
| 2 total | Supervisor; Banking Generalist covering all specialist duties | Evaluation only |
| 3 total | Supervisor; Account/Card specialist; Loan/Policy/Support specialist | Evaluation only |
| 5 total | Supervisor; Account; Card; Loan; Policy/Support | Main application and evaluation baseline |

This compares role grouping and routing architectures, not an isolated
mathematical effect of agent count. Count all distinct LLM-backed roles;
also record how many agents and model calls each individual request
actually uses. Do not force every agent to participate in every request.

**Shared behavior and controls:**

- Reuse the same BankSim services, typed tools, authentication,
  authorization, confirmation rules, RAG corpus, and conversation-state
  contract across all variants. Every variant must support every tested
  capability, including clarification and escalation.
- Give merged specialists the union of the corresponding specialists'
  tool permissions. Preserve server-side checks for every tool call.
- Fix the LLM provider/model/version where available, sampling settings,
  per-call output limits, overall per-scenario token budget, maximum
  model/tool calls, timeout, and retry policy across variants. Record
  prompt versions and necessary role-specific differences.
- Fix embedding model, retrieval settings, corpus checksum, tool schemas,
  application revision, and test dataset version. Keep evaluation cases
  separate from examples used to develop or tune prompts.
- Start each scenario with the same synthetic data and conversation
  state. Reset database mutations and pending confirmations between runs
  in an isolated evaluation database, never the interactive demo database.
- Use text for the primary experiment to avoid speech recognition and
  audio transport confounds. Verify voice separately on the main system.

**Dataset and execution:**

Prepare 60 fixed scenarios: 10 account/transaction, 8 card, 10 loan,
8 policy, 8 support/dispute, 8 multi-turn or cross-domain, and 8
authorization/confirmation/injection/provider-error cases. Include
explicit expected facts, valid tool behavior, expected final database
state, required citations, and permitted refusal/clarification outcomes.
Use scripted follow-up turns for confirmations and ambiguous requests.
Use only fictional information.

Run a small pilot first to check the harness, then freeze the dataset
and configuration. Run each scenario 3 times per variant: 60 x 3 x 3 =
540 scenario runs; a multi-turn scenario can contain multiple model
calls. Randomize or interleave configuration order with a recorded seed,
apply consistent cache/warm-up rules, and record all attempts, errors,
timeouts, and budget-limit failures. Estimate provider usage before the
full experiment and respect the user-agreed spending limit. If fewer
runs are feasible, report the actual sample size and limitation.

**Metrics and evidence:**

| Metric | Measurement |
|---|---|
| Task success | Scenarios meeting predefined facts, action-state, and workflow expectations / all scenarios |
| Response correctness | Required facts correctly expressed, with unsupported claims recorded |
| Routing and tool correctness | Valid role/tool selections against each variant's expected mapping; include argument correctness |
| Safety | Unauthorized access, confirmation bypasses, and injection-induced violations, reported separately by count and rate |
| Policy grounding | Citation validity, answer support, and correct handling of missing policy evidence |
| Latency | End-to-end scenario median and p95, plus per-turn latency; exclude simulated user waiting |
| Resource usage | Model/tool calls, agents invoked, input/output tokens, and cost where provider rates are known |
| Reliability | Errors, timeouts, retries, and recovery outcomes with explicit denominators |

Use deterministic checks for balances, EMI, ownership, action state,
tool outcomes, and citation existence. Use a written, blinded human
rubric for explanation quality and policy support; an LLM judge is
optional supplementary evidence, never the sole correctness or safety
judge. Report aggregate and per-category results, paired differences
on identical cases, and uncertainty across scenarios; repeated runs of
one scenario are not independent new scenarios. If confidence intervals
are used, resample at scenario level.

Save per-run structured records including case ID, repeat, variant,
request ID, final response, tool trace, citations, confirmation events,
verified final state, metric results, latency, usage, and errors. Do not
save secrets or private model reasoning. Label illustrative outputs as
examples; never present them as measured experiment results.

**Deliverables:**

- `backend/tests/evals/agent_count_cases.json`: frozen scenarios and
  expected behavior.
- `backend/app/agents/variants.py`: shared graph factory with validated
  total counts of 2, 3, and 5; application default remains 5.
- `backend/evals/run_comparison.py`: reproducible evaluation runner,
  isolated reset support, and configuration manifest.
- `backend/app/services/evaluation_service.py` and a lightweight worker:
  shared execution, persistent job progress and scoring.
- `backend/app/api/routes/evaluations.py`: owner-only evaluation APIs.
- Evaluation models/migrations for jobs, attempts, events, metrics and reviews.
- `frontend/src/features/evaluation/`: private web evaluation dashboard,
  response comparison, progress, charts, run history, review and exports.
- `evaluation/results/`: sanitized raw run records and summary CSV/JSON.
- `docs/AGENT_COMPARISON_REPORT.md`: methodology, metric definitions,
  measured tables/charts, side-by-side outputs for identical prompts,
  failure examples, tradeoffs, and limitations.

Results are unknown until measured. Do not assume 5 agents are more
accurate or 2 agents are faster. The final report must distinguish the
fixed main-project choice of 5 agents from the empirical comparison.

------------------------------------------------------------------------

### 15.2 Private web evaluation dashboard

The project owner must be able to demonstrate the comparison to a
professor entirely through the web application. Implement:

1. **New comparison:** custom text input, predefined scenario selection,
   or full benchmark selection; 2/3/5 variants selected by default;
   synthetic fixture, repetitions, common model settings and execution
   limits. Show estimated usage where available before starting a job.
2. **Progress and cancellation:** queued/running/completed/failed/cancelled
   states, completed scenario counts, errors and partial results. Browser
   refresh or navigation must not discard the run.
3. **Side-by-side results:** actual answers for the same input, citations,
   verified database outcomes, tool arguments/results with redaction,
   agent handoffs, timestamps, agents actually invoked, model/tool calls,
   latency, tokens, cost when known, and pass/fail explanations. Display
   observable events, never private model reasoning.
4. **Metrics and charts:** aggregate and per-category success, safety,
   latency and usage with sample counts; distinguish incomplete, failed,
   missing and unscored observations. Do not treat unknown cost as zero.
5. **Saved history and exports:** reopen comparisons; download sanitized
   CSV/JSON and a printable HTML report containing actual responses,
   metrics, configuration/dataset versions, methodology and limitations.
   Escape report content and neutralize formula injection in CSV cells.
6. **Review scoring:** blinded rubric review for subjective output quality.
   Custom questions without predefined expectations are exploratory and
   unscored for correctness until expectations or review are supplied.

Use the controlled scenario scripts for benchmark follow-ups and
explicit confirmations. For custom interactive runs, accept input for a
specific pending variant/attempt and log divergent follow-ups. Mark these
runs exploratory, outside controlled aggregate comparisons unless they
follow the fixed script. Starting an evaluation is not implicit consent
to every simulated action; retain each agent's confirmation workflow.

Persist run ownership, settings, fixture/dataset versions, budgets,
timestamps, status, scenario attempts, sanitized events, outputs,
verified state, scores, usage and errors in PostgreSQL. Keep result
records separate from disposable evaluation banking fixtures. Use an
isolated evaluation database and per-attempt fixture namespaces so
concurrent runs cannot affect each other or the interactive demo.
Validate reset targets before cleanup.

Start with a lightweight worker in the same backend codebase using
PostgreSQL-backed jobs, bounded concurrency and client polling. Keep
long evaluations outside HTTP request lifetimes. On interruption, retain
partial evidence and mark the attempt interrupted/failed. A retry is a
new attempt with fresh fixtures; never silently replay sensitive writes.
Cancellation should stop at safe execution boundaries, retain completed
evidence and mark unfinished work explicitly. Enforce execution limits
and budget checks server-side.

The normal banking interface continues to use exactly 5 agents; variant
selection belongs only to the private evaluation dashboard. The optional
CLI complements the dashboard and must not become a separate evaluation
implementation with different scoring or safety behavior.

------------------------------------------------------------------------

## 16. API and Response Conventions

Use Pydantic schemas for all request and response bodies. Use a
consistent error format, for example:

``` json
{
  "error": {
    "code": "CONFIRMATION_REQUIRED",
    "message": "Please confirm this simulated action before it can proceed.",
    "request_id": "generated-request-id"
  }
}
```

Use appropriate HTTP status codes: - `200` successful
reads/operations. - `201` successfully created resources. - `202`
pending confirmation or asynchronous work when appropriate. - `400`
malformed or invalid workflow request. - `401` unauthenticated. - `403`
authenticated but unauthorized. - `404` resource not found, or
non-disclosing not-found behavior. - `409` conflicting workflow state. -
`422` schema validation failure where FastAPI uses it. - `429` rate
limit exceeded. - `500` unexpected server failure without sensitive
internals. - `503` unavailable dependency/provider where appropriate.

Avoid returning different errors that leak whether another user's
private resource exists.

------------------------------------------------------------------------

## 17. Environment Variables

Create `.env.example` with placeholder values and descriptions.
Suggested variables:

``` dotenv
APP_ENV=development
APP_SECRET_KEY=replace-with-a-long-random-local-secret
DATABASE_URL=postgresql+psycopg://bankai:bankai_dev_only@127.0.0.1:55432/bankai
CORS_ORIGINS=http://localhost:5173

LLM_PROVIDER=
LLM_API_KEY=
LLM_MODEL=

EMBEDDING_PROVIDER=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=

LIVEKIT_URL=
LIVEKIT_API_KEY=
LIVEKIT_API_SECRET=

STT_PROVIDER=
STT_API_KEY=

TTS_PROVIDER=
TTS_API_KEY=

ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Adjust variable names to match the chosen libraries. Never use
placeholder values as working credentials. Do not commit a real `.env`
file. Ensure the application validates required configuration at startup
and explains which integration is missing without printing secrets.

------------------------------------------------------------------------

## 18. Docker and Local Development

Provide a Docker Compose configuration for: - PostgreSQL with pgvector
enabled. - FastAPI backend. - React frontend.

Add health checks and dependency readiness. Do not assume that a
container is ready merely because it has started. Use persistent
database volumes for local development and document how to reset demo
data safely.

The README must include: 1. Prerequisites. 2. Clone/open instructions.
3. Environment setup. 4. Database startup. 5. Migration command. 6.
Seed-data command. 7. Backend startup. 8. Frontend startup. 9. Test
commands. 10. Voice provider setup. 11. Troubleshooting. 12. Demo
credentials and data reset instructions for local development only.

If a Docker setup is not feasible in the current environment, provide
equivalent local commands and document the limitation.

------------------------------------------------------------------------

## 19. Final Demo Scenario

Prepare a reliable end-to-end demo using only fictional data:

1.  Sign in as a seeded demo customer.
2.  Ask: "What is my account balance?"
3.  Show the balance returned by BankSim.
4.  Ask: "Show me my recent transactions."
5.  Ask: "Explain this transaction."
6.  Ask a policy question such as: "What documents are required for the
    demo loan application?"
7.  Show the retrieved policy source.
8.  Calculate the EMI for a sample loan.
9.  Ask to block a demo card.
10. Show that the assistant requests confirmation.
11. Confirm and show the simulated card status update.
12. Create a support ticket.
13. Repeat one supported request using voice, if the LiveKit provider is
    configured.
14. Demonstrate that a user cannot access another demo customer's
    records.
15. As the project owner, open the private evaluation dashboard and run
    the same scenario against 2, 3 and 5 agents.
16. Inspect the actual responses, observed agent/tool traces and metrics;
    reopen a saved benchmark and export a report for professor review.
17. With telephone configuration and recipient agreement in place, start
    one actual test call from Phone Test. The professor answers, asks about
    fictional banking data, and hears BankAI responses. End the call and
    show verified status and permitted evidence.

Never use actual personal or financial information in the demonstration.

------------------------------------------------------------------------

## 20. Project Documentation and Viva Readiness

Keep these documents accurate and aligned with the implemented code:

-   `README.md`: setup, commands, configuration, tests, troubleshooting.
-   `docs/IMPLEMENTATION_PLAN.md`: this plan adapted to the repository.
-   `docs/IMPLEMENTATION_STATUS.md`: phase checklist and test outcomes.
-   `docs/ARCHITECTURE.md`: component diagram, data flow, trust
    boundaries.
-   `docs/API_SPEC.md`: endpoints, request/response examples, status
    codes.
-   `docs/SECURITY.md`: authentication, authorization, confirmations,
    limitations.
-   `docs/TESTING.md`: commands, test strategy, current results.
-   `docs/DEMO_GUIDE.md`: end-to-end walkthrough and demo credentials.
-   `docs/AGENT_COMPARISON_REPORT.md`: 2/3/5-agent experiment method,
    actual outputs, metrics, failures, and limitations.

Clearly document what is genuinely implemented, what needs an external
provider key, and what is future scope.

------------------------------------------------------------------------

## 21. Definition of Done

The project is not complete until:

-   [ ] The frontend and backend run.
-   [ ] Database migrations and seed data work.
-   [ ] Authentication and ownership checks are tested.
-   [ ] BankSim endpoints return real seeded database records.
-   [ ] The dashboard fetches backend data.
-   [ ] Text chat works with a configured LLM provider or clearly
    reports missing configuration.
-   [ ] Supervisor and specialized workflows use typed, approved tools.
-   [ ] Main application uses exactly 5 total agents, including Supervisor.
-   [ ] Evaluation-only 2-agent and 3-agent variants retain the same capabilities and safety rules.
-   [ ] Private web evaluation dashboard runs comparisons, shows progress and actual outputs/traces, saves history, and exports CSV/JSON/printable reports.
-   [ ] Evaluation APIs enforce owner access, isolated fixtures, execution limits, and safe cancellation/interruption handling.
-   [ ] Reproducible 2/3/5-agent comparison includes actual outputs, raw evidence, metrics, and limitations.
-   [ ] No LLM can query the database directly.
-   [ ] Sensitive simulated actions require a valid explicit
    confirmation.
-   [ ] RAG ingests sample policies and cites retrieved sources.
-   [ ] Voice connects through LiveKit when correctly configured.
-   [ ] Voice and text share the same backend authorization logic.
-   [ ] Actual outbound phone calling is verified with an approved live test recipient.
-   [ ] Phone calls have owner access, allowlisted destinations, scoped demo context, explicit confirmations and cleanup on hang-up.
-   [ ] Unit and integration tests cover the core flows.
-   [ ] Docker/local setup and environment variables are documented.
-   [ ] No secrets or real financial data are committed.
-   [ ] README and implementation status match the actual code.
-   [ ] The demo can be completed from a fresh setup using synthetic
    data.

------------------------------------------------------------------------

## 22. How to Work with the User

During planning, summarize the repository state and prepare the plan for
user review. Start implementation only after the user's next instruction
authorizes it.

For each phase: 1. State the phase and the files/components being
implemented. 2. Implement the feature. 3. Run relevant tests and
linters. 4. Fix errors rather than hiding them. 5. Update the status
checklist. 6. Report commands run, tests passed/failed, and any setup
required from the user. 7. Continue to the next phase when the current
phase's acceptance criteria are satisfied.

If the task becomes too large for one context window, stop at a stable
checkpoint, update `docs/IMPLEMENTATION_STATUS.md`, and provide the
exact next step. Do not regenerate the entire repository or discard
working code.

**Current next step:** Phases 0–4 are complete. Continue with Phase 5
text chat and configurable LLM provider interface. Track verified completion and outstanding
work in `docs/IMPLEMENTATION_STATUS.md`.
