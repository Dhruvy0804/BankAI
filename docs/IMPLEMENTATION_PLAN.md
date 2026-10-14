# BankAI implementation plan for review

**Status:** Implementation authorized; proceeding through verified phases.
**Updated:** 2026-10-13.
**Specification:** `../BankAI_Codex_Implementation_Plan.md`.

**Current checkpoint:** Phase 3 authentication and BankSim APIs implemented.
Next: Phase 4 banking frontend. See `IMPLEMENTATION_STATUS.md` for verification evidence.

## 1. Agreed scope and current state

Build a local voice and text banking assistant using fictional data.
The main application uses **5 total agents including the Supervisor**.
Create 2-agent and 3-agent configurations only for evaluation, and compare
their actual outputs and measured performance against the main system.

Deliver one web application with two areas: the main banking interface
and a private evaluation dashboard for the project owner. The dashboard
must let the owner run, inspect, save, and export comparisons for the
professor. Evaluation is a required web feature, not just a CLI report.

The initial inspection found only planning documents, with no application
to extend. The user authorized phased implementation on 2026-10-13.
See `IMPLEMENTATION_STATUS.md` for completed work, verification and the
next checkpoint; this document defines the overall implementation sequence.

## 2. Agent architecture

| Configuration | Roles | Deployment purpose |
|---|---|---|
| 2 agents | Supervisor + Banking Generalist | Local evaluation only |
| 3 agents | Supervisor + Account/Card + Loan/Policy/Support | Local evaluation only |
| 5 agents | Supervisor + Account + Card + Loan + Policy/Support | Main application and evaluation |

The five-agent main system has these responsibilities:

1. **Supervisor:** interpret intent, route requests, coordinate multi-step
   work, ask clarification questions, and handle workflow failures.
2. **Account:** account lists, balances, transaction retrieval and
   explanations, and demo KYC status.
3. **Card:** card information and the confirmed simulated blocking flow.
4. **Loan:** EMI calculations, demo eligibility, and confirmed simulated
   applications; access shared policy retrieval when needed.
5. **Policy/Support:** grounded policy answers with citations, support
   and dispute tickets, and escalation. Policy and support are workflows
   inside this single agent.

All configurations have the same overall capabilities. Smaller variants
merge specialist responsibilities and their tool permissions. They do
not remove features or bypass security to reduce the agent count.
An agent is a distinct LLM-backed role with instructions and tool
permissions. Tools, graph control nodes, RAG retrieval, and voice
transcription/synthesis are not counted as extra agents.

Implement a common LangGraph state contract and graph factory. The web
banking interface constructs the 5-agent graph. The private evaluation
dashboard and optional CLI use the same evaluation service to construct
2-, 3-, or 5-agent graphs; ordinary users do not select a variant in the
banking interface. Record distinct agents invoked and
model calls per scenario because not every request visits every agent.

## 3. Shared application design

Text flows through React, authenticated FastAPI routes, the Supervisor,
specialists, typed tools, BankSim services, and PostgreSQL. Voice uses
LiveKit and speech adapters to enter the same workflow and speak its
response. No independent voice decision-making agent is added.

Use React/Vite/TypeScript and Tailwind for the interface, FastAPI and
Pydantic for the API, SQLAlchemy/Alembic for database access, PostgreSQL
with pgvector for storage and retrieval, and LangGraph for orchestration.
Keep LLM, embedding, speech-to-text, and text-to-speech providers
configurable. Choose compatible versions during implementation and
record them in dependency manifests.

BankSim stores synthetic customers, accounts, transactions, cards, KYC,
loans, tickets, and audit events. Use decimal money values. The backend
derives customer identity from authentication and checks ownership on
every protected operation. The model never executes SQL or chooses the
authenticated identity.

Card blocking and loan submission use expiring pending actions bound to
the user and exact operation. Revalidate ownership at confirmation and
prevent duplicate execution. All three graphs share these checks.

### Private evaluation dashboard

Provide a protected `/evaluation` area for the project owner with these
screens and interactions:

1. **New comparison:** enter a custom prompt, select a predefined scenario,
   or choose the benchmark suite. Default to all three variants (2/3/5).
   Choose a synthetic fixture and repetition count; show the common model
   settings, limits, and estimated usage before starting.
2. **Run progress:** display queued/running/completed/failed/cancelled
   status, scenario progress, and partial results. Run in a backend worker
   so navigation or browser refresh does not lose the experiment. Offer
   cancellation between safe execution steps and prevent double-submit.
3. **Comparison detail:** show three response columns for the same input,
   citations, verified action outcomes, observed agent/tool event timelines,
   pass/fail reasons, latency, calls, tokens, and estimated cost when known.
   Display which of the configured agents actually participated. Do not
   display private model reasoning as an execution trace.
4. **Summary:** show comparable tables and charts for task success, safety,
   latency, and resource use, with category filters and sample counts.
   Keep missing, failed, partial, and unscored results visible.
5. **History and export:** reopen saved runs and download sanitized CSV,
   JSON, and a printable HTML report suitable for the professor. Include
   settings, dataset versions, outputs, metric definitions, and limitations.
6. **Review scoring:** capture rubric scores for subjective quality with
   variant labels hidden during review. Custom prompts without expected
   results are exploratory and unscored for correctness until expectations
   or a review are supplied; never invent a success score from model output.

Multi-turn scenarios use a common scripted sequence, including explicit
confirmations. Custom prompts can show a pending clarification or
confirmation; the owner may supply follow-up input per variant, with
differences recorded. Mark such interactive runs exploratory and exclude
them from the controlled benchmark unless they use the fixed scenario
script. The dashboard must never automatically confirm banking actions
merely because a test was started.

### Evaluation backend, persistence, and access

Use a shared evaluation service behind both the dashboard API and CLI.
Start with one lightweight worker from the same Python codebase that
claims jobs stored in PostgreSQL; use bounded concurrency and polling
for web progress. No separate queue platform is required initially.
Persist job status and results. On worker interruption, mark the attempt
interrupted/failed and retain evidence; retry as a new attempt with fresh
fixtures rather than silently replaying writes.

Store evaluation runs (owner, settings, dataset/fixture versions, budget,
status and timestamps), scenario attempts (variant, repeat, outputs,
events, checks, usage and errors), and human-review scores. Keep these
records separate from disposable banking fixtures. Isolate mutable
fixtures by attempt in the evaluation database and clean up only the
attempt's namespace. Reject reset targets that refer to the demo database.

Provide owner-only backend endpoints under `/api/v1/evaluations`:

| Method and path | Purpose |
|---|---|
| `GET /scenarios` | List versioned scenarios and their descriptions |
| `POST /runs` | Validate settings and enqueue a run; return HTTP 202 and run ID |
| `GET /runs` | List the owner's saved runs |
| `GET /runs/{run_id}` | Retrieve progress, configuration, and summaries |
| `GET /runs/{run_id}/results` | Retrieve paginated scenario results and sanitized traces |
| `POST /runs/{run_id}/cancel` | Request cancellation and preserve completed evidence |
| `POST /runs/{run_id}/followups` | Submit a validated turn to a pending interactive attempt |
| `POST /runs/{run_id}/reviews` | Save rubric scores and reviewer notes |
| `GET /runs/{run_id}/export?format=csv\|json\|html` | Download a sanitized report |

Enforce a server-side owner/evaluator role on every endpoint and export,
plus run ownership. Do not rely on hiding navigation. Provision the
owner role through local setup, never ordinary self-registration. Store
provider credentials only on the backend. Validate allowed variants,
repetitions, concurrency, and token/cost budgets; limit actual execution,
not just the values shown in the browser. Escape untrusted report content
and neutralize spreadsheet formulas in CSV exports.

## 4. Implementation sequence after authorization

Each phase ends with relevant checks, fixes, and an update to
`docs/IMPLEMENTATION_STATUS.md`. Do not claim a provider integration is
working until it has been exercised with valid configuration.

| Phase | Work and primary files | Completion evidence |
|---|---|---|
| 0: Setup decisions | Recheck workspace; create README, architecture, API, security, testing, and status documents | Documented prerequisites, architecture, and phase checklist |
| 1: Scaffolding | `backend/`, `frontend/`, `.env.example`, `.gitignore`, Docker Compose, health/readiness routes | Frontend and backend start; database readiness succeeds; no committed secrets |
| 2: Data | SQLAlchemy models, Alembic migrations, repeatable fictional seed data | Fresh migration and repeated seed run; valid relationships and decimal amounts |
| 3: BankSim and authentication | Login, accounts, transactions, cards, KYC, EMI/eligibility, loans, support, confirmation and audit services | API tests cover own-data access, cross-user denial, valid calculations, expired confirmations, and duplicate writes |
| 4: Banking interface | Login, dashboard, transaction filters, cards, loans, support, confirmation dialogs | Backend data displayed; responsive layout and loading/error/empty states checked |
| 5: Text chat | LLM adapter, chat endpoint, typed conversation state, provider timeout/error handling | Configured provider responds; missing credentials and failures are reported accurately |
| 6: Main 5-agent graph | Supervisor, four specialists, registered tools, routing, clarification, confirmation and escalation | Exactly five distinct agent roles; representative intents and multi-turn flows pass; unsafe writes fail |
| 7: RAG | Synthetic policies, ingestion, chunking, embedding, pgvector retrieval, citations | Repeatable ingestion; expected sources retrieved; unsupported policy answers handled honestly |
| 8: Voice | Authenticated LiveKit tokens, speech adapters, voice UI, shared graph connection | Real configured voice session handles a banking request; text remains usable if voice is unavailable |
| 9A: Evaluation engine | Shared graph factory, 2/3/5 variants, isolated fixtures, persistent jobs/results, worker, owner-only API and optional CLI | Equivalent capabilities, identical safety rules, safe resets, durable progress and bounded execution |
| 9B: Evaluation web dashboard | New comparison, progress/cancel, response columns, observed traces, metric charts, history, review scoring, CSV/JSON/HTML exports | Owner can run and reopen comparisons from the browser; non-owner API access denied; exported data matches saved evidence |
| 9C: Benchmark and quality | Frozen dataset, repeated runs through the shared service, scoring, report, regression/security tests | Measured reproducible comparison; partial/unscored cases handled honestly; isolation, cancellation and refresh/restart cases verified |
| 10: Delivery | Complete Docker setup, README, demo guide, architecture diagram, final status | Fresh setup and end-to-end demo verified; implemented features and missing configuration clearly documented |

## 5. Comparative evaluation design

**Research question:** How do 2-, 3-, and 5-agent architectures differ in
banking task success, output correctness, safe execution, response time,
and resource use when they share the same capabilities and backend?

This experiment changes role grouping and routing as well as agent
count. Report it as an architecture comparison rather than proof that
agent count alone causes a result. The main system remains the agreed
5-agent implementation regardless of the experimental ranking.

### Fixed scenarios

Prepare 60 scenarios with predefined expected results:

| Category | Count | Example expectation |
|---|---:|---|
| Accounts and transactions | 10 | Correct seeded balance or transaction facts; demo KYC status |
| Cards | 8 | Correct card selected; no block before valid confirmation |
| Loans | 10 | Correct EMI, demo eligibility, confirmed application |
| Policies | 8 | Supported answer and valid citation, or explicit lack of evidence |
| Support and disputes | 8 | Correct ticket details and escalation behavior |
| Multi-turn and cross-domain | 8 | Follow-up context retained; appropriate clarification/routing |
| Security and failure handling | 8 | Reject cross-user access, stale confirmation, injection, and false success during provider errors |
| **Total** | **60** | |

Store explicit expected facts, tool behavior, final database state, and
accepted clarification/refusal outcomes. Script follow-up turns and
confirmations consistently. Do not use evaluation scenarios to tune
prompts after freezing them; version any later revisions.

### Fair execution

1. Reuse identical seeded fixtures, service/tool implementations, RAG
   corpus and retrieval settings, and conversation starting state.
2. Fix model and provider, sampling settings, per-call and per-scenario
   budgets, maximum calls, retries, and timeout rules. Record versions
   and each role's prompt/tool permissions in a run manifest.
3. Use a separate evaluation database and reset each scenario's writes
   and pending actions. Never reset the interactive demo database.
4. Pilot the harness, estimate provider usage, and establish a spending
   limit with the user before the full benchmark.
5. Run 3 repetitions of each case for each variant: **540 scenario
   runs**, potentially involving multiple model calls per run. Interleave
   variant order with a recorded seed and consistent caching/warm-up.
6. Include errors, timeouts, and budget exhaustion in outcomes. Report
   reduced sample sizes honestly if provider limits constrain execution.
7. Benchmark text to isolate architecture behavior. Validate voice
   separately on the main 5-agent system.

### Scoring and report

Measure task success, factual correctness, valid routing/tool calls,
unauthorized actions and confirmation bypasses, policy grounding,
median/p95 end-to-end latency, model/tool call counts, agents invoked,
input/output tokens, known provider costs, and failures/recovery.
Exclude scripted user waiting from latency and state how timing is
collected. Report unavailable usage or pricing as unavailable, not zero.

Use deterministic assertions for banking values, tool results, action
state, and citations. Use a written human-review rubric with variant
labels hidden for explanation quality and groundedness. Any LLM judging
is supplementary. Report category-level as well as overall results and
paired differences on the same scenarios. Treat scenario repeats as
repeated measurements; use scenario-level resampling if calculating
confidence intervals.

Show the same user prompt side by side with the actual response from
each variant, verified action outcome, tools used, timing, usage, and
pass/fail reason. Include both representative successes and failures.
Store sanitized traces and measured outputs, never private model
reasoning, tokens used for authentication, or secrets. Results remain
**not measured** until the experiment runs.

Planned evidence files:

- `backend/app/agents/variants.py`: graph factory for 2/3/5 total agents.
- `backend/tests/evals/agent_count_cases.json`: versioned scenarios.
- `backend/evals/run_comparison.py`: reproducible local runner.
- `backend/app/services/evaluation_service.py` and worker: shared job execution and scoring.
- `backend/app/api/routes/evaluations.py`: protected evaluation API.
- Evaluation models and migrations: saved jobs, attempts, events, metrics, and reviews.
- `frontend/src/features/evaluation/`: private dashboard, comparisons, charts, history, and exports.
- `evaluation/results/`: run manifest, per-run JSONL, summary JSON/CSV.
- `docs/AGENT_COMPARISON_REPORT.md`: method, measured tables/charts,
  actual output comparisons, tradeoffs, and limitations.

## 6. Validation and delivery criteria

Test service logic and workflow behavior, API authentication and
ownership, confirmation expiry and replay, loan math, RAG grounding,
agent routing, and UI interactions. Run relevant Python and frontend
checks at each phase. Exercise provider failures and database failures
without allowing the assistant to claim success.

The final demo signs in a fictional customer, retrieves a balance and
transactions, answers a cited policy question, calculates EMI, confirms
a card block, creates a ticket, and demonstrates access isolation.
Repeat a supported request by voice when configured. Present the
comparison report separately from the normal banking UI.

For the professor's demonstration, open the private evaluation dashboard,
run one identical scenario across 2/3/5 agents, inspect outputs and tool
events, reopen a saved benchmark, show aggregate metrics, and export the
report. Verify that refreshing preserves progress/history, cancellation
retains partial evidence, ordinary demo users cannot access evaluation
APIs, and no evaluation mutates the interactive demo's banking records.

Completion requires the working 5-agent application, capability-equivalent
evaluation variants, the private web evaluation dashboard with saved runs
and exports, measured reproducible comparison, tested security
and core flows, documented setup, and honest reporting of any missing
external integrations. Provider credentials must be supplied through
environment configuration; no real financial information is required.

## 7. Review checkpoint

The agent-count convention is confirmed: **Supervisor is included in
2, 3, and 5**. The proposed implementation merges Policy and Support in
the main system and uses the role groupings above for smaller variants.
The proposed benchmark is 60 scenarios with 3 repetitions per variant;
its final execution size depends on the agreed provider budget.
The private web dashboard is part of the agreed deliverable; the CLI is
an optional additional interface to the same evaluation service.

**Next action:** Implement and verify each phase in order, updating
`IMPLEMENTATION_STATUS.md` with evidence and the next stable checkpoint.
