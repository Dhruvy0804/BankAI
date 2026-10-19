# BankAI — Implementation Plan 2

**Purpose:** Revised implementation plan for the professor's project-review requirements.
**Prepared:** 2026-10-20.
**Main system:** Five agents in total, including the supervisor.
**Evaluation configurations:** Two, three, and five agents in total.
**Frameworks:** Google ADK and CrewAI only.
**Status:** Phases 0–6 implemented locally; later phases remain planned. See [implementation status](docs/IMPLEMENTATION_STATUS.md) for verification evidence and limitations.

## 1. Relationship to the original plan

This is a separate alternative to [BankAI_Implementation_Plan.md](BankAI_Implementation_Plan.md). The original plan and [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) remain unchanged and available for reference.

When Plan 2 is selected for implementation, its framework choices, remaining phases, evaluation design, and cloud-deployment requirements take precedence over conflicting instructions in the original documents. Existing banking functionality, API contracts, authorization, confirmation rules, and synthetic-data requirements continue to apply.

Creating this document does not start the next implementation phase. Implement future work in phases when instructed, keeping the application runnable, testing each phase, and recording actual results in the implementation status document. Do not report planned features as completed.

Preserving an old Markdown plan does not automatically restore old application code. Before implementing this alternative, retain the working Phase 4 Git checkpoint and use a separate branch. Use reviewed, additive database migrations where possible, and document dependency or schema changes needed to return to that checkpoint.

## 2. Project objective and retained scope

Build a web application where users can ask fictional banking questions through text, browser voice, and actual telephone conversations. Agents retrieve account information, explain policies, calculate demo loan information, and prepare supported simulated actions. The project owner also gets a private evaluation dashboard for comparing agent configurations and showing evidence to the professor.

The production demonstration uses five agents. Two-agent and three-agent versions exist for evaluation; they must answer the same tasks using the same underlying banking services and permissions.

Retain:

- The React/Vite/TypeScript frontend and FastAPI/Pydantic backend.
- PostgreSQL, SQLAlchemy/Alembic, and pgvector for banking data and policy retrieval.
- Existing login, ownership checks, banking dashboard, accounts, transactions, cards, loans, support, pending confirmations, and audit logs.
- RAG for banking policies and FAQs, with source attribution.
- LiveKit-based browser voice and an actual outbound phone-call demonstration using telephony/SIP, STT, and TTS.
- A private web evaluation dashboard, saved experiment history, and downloadable reports.
- Fictional customers and transactions only. No real banking integration or real financial operations.

Repository status at preparation: Phases 0–4 are recorded as complete; Phases 5 onward are not started. Recheck the repository and test results before implementation.

Current checkpoint: Phase 5 and Phase 6A–6C have since been implemented and locally verified, including a live five-role ADK/CrewAI workflow over A2A and MCP. Phase 7 (RAG) is next; evaluation comparisons and cloud deployment remain later work.

## 3. Professor's requirements and acceptance evidence

| ID | Requirement | Planned implementation | Required evidence |
|---|---|---|---|
| R1 | Shared context/state; compare messaging architectures; mandatory Blackboard | Versioned shared Blackboard with typed artifacts; direct-message comparison | Trace showing one agent writes an artifact and another consumes it; architecture comparison report |
| R2 | At least two external tools through MCP | Authenticated BankSim lookup and loan EMI calculator exposed through MCP | Successful real MCP requests/responses for both tools, plus invalid-input and unauthorized-access checks |
| R3 | Pydantic structured output | Validated intermediate artifacts and final response JSON; Markdown/table views derived from JSON | Schema validation tests and exported examples |
| R4 | Suitable agentic patterns and comparison | Supervisor delegation with Blackboard; controlled direct-message/sequential-delegation baseline | Same-task results comparing patterns at fixed agent count and prompt variant |
| R5 | Callback monitoring of flow, intermediate output, errors | Framework callbacks and protocol hooks emitting correlated events | Successful and failed traces with ordered agent/tool events |
| R6 | A2A interoperability between frameworks | Google ADK supervisor delegates to CrewAI specialists using actual A2A protocol | Agent Cards, protocol task/artifact exchange, and cross-framework integration tests |
| R7 | Both CrewAI and ADK; no other agentic framework | ADK supervisor, CrewAI specialists in every configuration | Dependency review and executed traces identifying both frameworks |
| R8 | Guardrails, callback validation, prompt variations | Input/tool/output validation, injection and abusive-input handling, protected actions; two prompt strategies | Adversarial tests and controlled prompt comparison |
| R9 | Observability, auditability, provenance | Correlated traces across API, agent runtimes, A2A, MCP, state, retrieval, and final output | Inspectable traces and source/artifact provenance |
| R10 | Repeated end-to-end performance, cost, runtime evaluation | Agent-count, architecture, and prompt experiments with repeated runs | Saved outputs, accuracy/safety metrics, latency, tokens, cost estimates, and uncertainty |
| R11 | Cloud deployment | HTTPS web app, backend, agent services, worker, and database on cloud infrastructure | Working authenticated cloud demonstration and deployed end-to-end verification |

**Terminology requiring confirmation:** The supplied rubric says “Hover Blackboard architecture.” This plan interprets the mandatory component as a shared Blackboard architecture. The meaning of “Hover” is unverified; confirm the exact term with the professor before finalizing the architecture acceptance criteria. Do not claim that a separately defined “Hover” architecture has been implemented.

## 4. Framework allocation and exact agent counts

| Configuration | Google ADK agent | CrewAI agents | Total |
|---|---|---|---|
| Main system / five-agent evaluation | Supervisor | Account; Card; Loan; Policy/Support | 5 |
| Three-agent evaluation | Supervisor | Account/Card; Loan/Policy/Support | 3 |
| Two-agent evaluation | Supervisor | Banking Generalist | 2 |

The supervisor handles routing, clarification, coordination, and the final response. Specialists perform their assigned banking work using approved tools and return typed artifacts.

Merged roles inherit the relevant capabilities of the five-agent system. Every configuration must genuinely execute both frameworks on appropriate benchmark tasks. Record which roles actually ran for each task; a configured agent does not need to run when its capabilities are irrelevant.

Do not create hidden manager, planner, reviewer, or critic agents through automatic framework features. Disable automatic agent creation and count every independently configured LLM agent role. Retries and repeated calls by one role are additional invocations, not additional agent roles. Record both role counts and model-call counts.

MCP servers, A2A adapters, state storage, callback handlers, retrieval services, and voice components do not count as agents unless they introduce another autonomous LLM role.

Remove LangGraph from the proposed AI architecture. Do not introduce LangChain, PydanticAI, or another agentic framework. Direct model-provider SDKs, Pydantic, MCP/A2A SDKs, database libraries, and tracing libraries may support the two permitted frameworks.

## 5. Communication, shared state, and execution

### 5.1 Main Blackboard architecture

Use the existing PostgreSQL infrastructure for a shared Blackboard, scoped by authenticated owner, conversation/session, and execution run. It must be accessible through controlled service interfaces by both frameworks; their separate in-memory session objects are not automatically shared state.

Store:

- The user request, immutable server-established identity references, and authorized configuration.
- Task status, assigned role, dependencies, and bounded retry/error information.
- Validated intermediate artifacts with schema version, author role/framework, timestamps, source references, and state revision.
- Final response, pending-action reference when applicable, and execution/provenance identifiers.

Use transactional/version-checked writes to prevent silent overwrites. Enforce ownership on reads and writes. Agents cannot change the trusted user identity, grant themselves permissions, or treat Blackboard content as authorization. Record which artifact revisions each consumer used.

Example: Account produces an account/KYC artifact; Loan consumes that artifact and uses the approved calculator and eligibility service; Policy/Support consumes the loan result and relevant policy sources; Supervisor consumes these validated results and creates the final response. The banking service still rechecks ownership and action eligibility at execution time.

### 5.2 A2A interoperability

Run an ADK supervisor and CrewAI specialist endpoints using supported A2A integration or the official protocol SDK. Exchange Agent Cards, task requests/status, and typed result artifacts over the actual protocol. A direct Python function call is not sufficient evidence of A2A interoperability.

Propagate run/task/correlation IDs and authorized artifact references across the boundary. Bind identity through authenticated, short-lived service credentials and server-side checks; never place raw user tokens or secrets in model prompts or shared artifacts. Restrict reachable endpoints and agent capabilities.

Handle protocol errors, cancellation, timeouts, retries, and idempotency explicitly. Ensure sensitive actions cannot execute twice after a retry. Verify supported ADK/CrewAI/A2A versions together in a small interoperability test, then pin the working versions. Do not assume similarly named framework features are protocol-compatible without testing.

### 5.3 Architecture and pattern comparison

Implement two controlled execution modes:

1. **Blackboard with supervisor delegation:** Agents publish typed intermediate results to shared state; downstream agents consume authorized artifact references and revisions.
2. **Direct-message/sequential delegation:** The same roles exchange the needed intermediate artifacts through A2A task messages. Shared experiment logs remain available, but task knowledge is passed in messages rather than read from the Blackboard.

Both modes use real A2A, the same business tools, permissions, bounded clarification/retry rules, and final schema. Record actual task graphs because a single-agent task may not exercise inter-agent context sharing. Include explicitly dependent, multi-step scenarios in the architecture comparison.

## 6. MCP tools and structured contracts

Expose at least these two custom tools through a real MCP client/server boundary:

| Tool | Existing functionality to reuse | Validation |
|---|---|---|
| BankSim account lookup | Ownership-scoped banking service for balances/account facts | Server-bound identity, allowed account IDs, typed output, redaction |
| Loan EMI calculator | Existing calculation service | Valid principal/rate/tenure, financial rounding, typed result |

Custom tools qualify under the supplied rubric, but existing REST endpoints alone do not demonstrate MCP. Capture protocol evidence that agents invoke both tools through MCP. Keep existing REST endpoints usable by the web dashboard.

Additional card, loan, or retrieval tools may use the same controlled integration when needed. Reuse the banking service; do not expose arbitrary SQL, unrestricted filesystem access, or bypass confirmation rules. MCP access must not weaken existing authentication and ownership checks.

Define Pydantic contracts for agent requests, intermediate artifacts, tool results, execution events, and final responses. A final response should contain the request/run ID, status, answer, typed data, source references, allowed next steps or pending confirmation, safe errors, and provenance references. Use a discriminated structure where different statuses require different fields.

Validate tool returns and A2A artifacts before another agent consumes them. Bound invalid-output repair attempts; return a clear failure when validation still fails. Canonical output is JSON; the UI renders Markdown/tables and voice derives a spoken response from the validated content.

## 7. Guardrails, callbacks, and observability

### 7.1 Validation and action protection

- Validate request types, lengths, supported intents, configuration values, and ownership at API/service boundaries.
- Detect and safely handle prompt injection, abusive/toxic requests, and instructions embedded in retrieved documents or tool text. Do not block legitimate banking complaints merely because their wording is negative.
- Treat user input, retrieved content, model output, and tool returns as untrusted. Deterministic authorization and confirmation remain authoritative even when model-based checks fail.
- Validate callback inputs, tool argument/return types, cross-agent artifacts, retrieved-source ownership, and final Pydantic output.
- Preserve explicit confirmation for card blocking and demo loan submission. Bind confirmation to the exact user, action parameters, and expiry; prevent replay.
- Use bounded tool/model calls, timeouts, cancellation, and safe user-facing failures. Do not leak stack traces, credentials, or another customer's information.

Use CrewAI/ADK callbacks and validation hooks plus Pydantic and application checks. Do not introduce a third agentic framework to implement guardrails.

### 7.2 Monitoring and provenance

Instrument before/after agent, model, and tool execution, plus state writes, A2A exchanges, MCP calls, retrieval, validation failures, retries, cancellation, and final response. Use supported framework callbacks and protocol hooks; add application events only where needed to connect the trace.

Correlate API requests, agent runs, A2A tasks, MCP tool calls, Blackboard artifact revisions, database audit records, and voice sessions. Use an OpenTelemetry-compatible trace mechanism where practical and retain a queryable execution/event history for the evaluation dashboard.

Record role/framework, model/version, prompt version/hash, configuration, source IDs, artifact producers/consumers, outcome/error class, duration, token usage, and cost-estimation inputs. Redact secrets and sensitive identifiers; apply access control and retention limits. Persist observable actions, results, and concise task summaries, not private model chain-of-thought.

Trace and audit storage serve different purposes: trace the workflow and preserve existing banking audit records for actions. A trace link must explain where an answer's facts came from.

## 8. Prompt variation and experiment design

### 8.1 Prompt strategies

Version two prompt strategies:

- **A: Tool-oriented/ReAct-style instructions:** Bounded action/observation cycles using approved tools; log actions and results without requesting private reasoning.
- **B: Few-shot instructions:** Fixed examples of routing, safe tool use, refusal, and structured answers.

Keep tool permissions, schema, model settings, safety requirements, and factual sources constant. Store the actual prompt versions used. Optional persona/content variations are separate experiments; do not silently combine them with the primary prompt comparison.

### 8.2 Required experiments and run counts

Use the original 60-scenario benchmark across its seven task categories, including multi-step context-sharing, follow-up, failure, ownership, and confirmation cases. Retain the scenario definitions and expected outcomes independently of agent configuration.

| Study | Fixed settings | Compared variable | Runs |
|---|---|---|---|
| Agent count | Blackboard, prompt A | 2 vs 3 vs 5 total agents | 60 scenarios × 3 repeats × 3 counts = 540 |
| Architecture/pattern | 5 agents, prompt A | Blackboard vs direct-message delegation | 360 total; 180 additional after reusing the matching baseline cell |
| Prompt strategy | 5 agents, Blackboard | Prompt A vs prompt B | 360 total; 180 additional after reusing the matching baseline cell |

The minimum combined design is **900 unique scenario-runs**, including the reused baseline results only once. This design supports each stated comparison but does not measure all interactions. An optional full factorial study is 60 × 3 repeats × 3 counts × 2 architectures × 2 prompts = **2,160 runs**, subject to budget.

Pilot a small subset first to validate execution, scoring, trace completeness, and per-run cost. Estimate and document the total budget before the full provider-backed benchmark. A pilot or mock-provider run is not the completed final evaluation. Obtain missing provider credentials through normal secret configuration, never by committing them.

### 8.3 Fairness and measurements

- Hold model/provider, model settings, knowledge snapshot, tool schemas, scenario inputs, fixtures, maximum call/token budget, retry limits, and timeouts constant across compared cells.
- Restore fictional data and conversation state between independent scenarios; preserve intentional context within a multi-turn scenario. Prevent earlier runs, caches, and state changes from benefiting only one configuration.
- Randomize/interleave execution order and retain all repeats, errors, cancellations, and timeouts. Label exploratory settings separately from controlled comparisons.
- Report task success, factual accuracy against fixtures, source correctness, structured-output validity, safety/ownership/confirmation compliance, and successful dependent-artifact consumption.
- Report total end-to-end latency, p50/p95 where supported by sample size, model/tool/A2A counts, token totals, errors, and retry overhead. Define timing boundaries consistently and report cold-start/setup overhead separately.
- Record actual provider token usage and a dated price snapshot; calculate estimated model cost plus separately reported cloud, speech, and telephony cost. Distinguish estimates from invoiced charges and report unavailable usage rather than inventing it.
- Use deterministic checks for banking facts and protected actions, and a fixed human-review rubric for answer quality. Blind human reviewers to configuration when practical. If an LLM judge is added, validate it against human samples and report its separate cost.
- Summarize paired scenario-level differences and uncertainty across repeats. Avoid declaring five agents better in advance. Note that merged role boundaries and framework composition are part of the configuration change, so this is a system comparison rather than a perfectly isolated effect of count alone.

Text is the primary controlled benchmark. Evaluate browser voice and telephone calls separately, reporting transcription quality, response delay, interruptions, and failures. Do not mix speech/telephony latency with text results without a separate breakdown.

## 9. Private evaluation web dashboard

Only the authorized project owner can create experiments, inspect traces, or export results. Reuse application authentication and add explicit evaluation-owner authorization.

Provide:

- Scenario selection, 2/3/5-agent selection, architecture/pattern, prompt version, repeats, and visible execution budget.
- Background experiment execution with persisted job status, progress, cancellation, and bounded concurrency. Jobs must survive browser closure; define recovery after worker restart.
- Side-by-side actual responses, structured outputs, expected outcomes, and scoring explanations.
- Agent/task timeline showing intermediate artifacts, Blackboard writers/readers, A2A exchanges, MCP calls, retries, validation failures, and provenance links.
- Accuracy/safety, latency, tokens, estimated cost, and configuration comparisons, with repeat counts and failure totals.
- Saved experiment history and JSON/CSV plus a readable Markdown report export containing configuration and version information.

Use real persisted execution events. Clearly label mock/provider-free development runs and incomplete experiments. Do not fabricate traces, timings, or evaluation scores for presentation.

## 10. Browser voice and actual phone calls

Keep browser voice as Phase 8A and actual outbound telephone calling as Phase 8B. In the phone demonstration, the project owner starts an approved test call, the professor answers on a normal phone, asks questions, and hears BankAI responses. This requires a configured telephony provider/SIP trunk and working speech services; browser microphone support alone does not satisfy it.

Use the same five-agent backend, validated final response, ownership rules, and synthetic banking session for both channels. Browser and phone components do not add agent roles. Correlate speech, call, and agent events with the same run/session identifiers.

Restrict outbound testing to explicitly approved numbers and bind each call to an authorized synthetic session. Obtain the recipient's agreement, identify the demo, and define how confirmation works in a telephone session without bypassing backend checks. Mask phone numbers in logs and exports; recording is off by default. Bound duration, concurrency, and spend; do not redial automatically. Authenticate webhooks, handle duplicates idempotently, and clean up disconnected sessions.

Acceptance: a real consented test call supports a multi-turn banking conversation and a safe failure case, with trace evidence and measured speech/telephony costs. Missing provider access must be reported as a blocker; a simulated call is not completion.

## 11. Cloud deployment

Cloud deployment is required in this plan. Local Docker execution is development evidence only.

Use a small, understandable topology: HTTPS frontend/API, private agent/A2A/MCP services, a persistent experiment worker, and managed PostgreSQL with pgvector support. A cloud VM/container host plus managed database is a suitable initial topology; choose the provider and instance sizes after checking current compatibility and cost. Keep agent services and the database off the public network.

Deploy the frontend and API under an approved HTTPS origin. Store secrets outside the repository, restrict CORS, disable debug/demo bootstrap behavior, and provide only approved synthetic demo accounts. Review the existing development authentication/session handling for public hosting; use secure HttpOnly cookie sessions with CSRF protection where applicable, or another documented secure production design. Restrict evaluation and outbound-calling controls to the owner.

Configure database migrations, backups, health checks, worker restarts/job recovery, trace retention, spending limits, and a teardown procedure. Ensure the chosen host supports voice/WebSocket durations and persistent background work; do not assume request-only serverless hosting runs an experiment worker indefinitely. Place LiveKit/telephony workers on compatible infrastructure and verify webhook connectivity.

Acceptance evidence must include an authenticated cloud URL, deployed commit/configuration references without secrets, functioning cross-framework A2A and both MCP tools, an exported evaluation run, and a cloud end-to-end smoke test. Verify browser voice and the approved phone test in the deployed environment. Report actual hosting/provider charges separately from estimated benchmark cost.

## 12. Phased implementation and exit gates

| Phase | Work | Exit gate |
|---|---|---|
| 0–4: Preserve existing application | Recheck the completed scaffold, database, authentication, BankSim APIs, and dashboard; retain Git checkpoint | Existing relevant tests/builds pass; baseline recorded; no unnecessary rewrite |
| 5: Typed text-chat foundation | Provider adapter using a direct SDK, authenticated chat API/UI, conversation persistence, Pydantic final response, safe errors | Real configured-provider text response and schema/error tests; mock runs clearly labeled |
| 6A: Framework and protocol foundation | Pin compatible CrewAI/ADK/A2A versions; implement supervisor/specialist interoperability, shared-state contracts, callback correlation | Real ADK-to-CrewAI A2A task/result exchange, artifact ownership/version tests, no extra agent framework |
| 6B: MCP banking tools | Expose account lookup and EMI calculator through authenticated MCP; validate arguments/results | Both tools successfully invoked over MCP; bad type/ownership cases rejected |
| 6C: Main five-agent system | Four CrewAI specialists plus ADK supervisor, Blackboard dependencies, protected operations, bounded retries, guardrails, tracing | Multi-agent dependent workflow and five-role count verified; injection/confirmation/error tests pass |
| 7: RAG | Ingest approved fictional policies, chunk/embed/retrieve, attach provenance and injection-resistant handling | Grounded answer with valid citations; irrelevant/missing/conflicting-source cases handled |
| 8A: Browser voice | LiveKit/STT/TTS integration, multi-turn sessions, interruption/disconnect handling | Live browser voice task uses the same verified agent backend |
| 8B: Actual phone calling | Authorized outbound calling, SIP/provider configuration, secure callbacks, consent and spending controls | Real approved phone conversation and safe failure verified; costs recorded |
| 9A: Evaluation runtime | 2/3/5 variants, direct-message mode, prompt A/B, scenario fixtures, repeatable jobs and scoring | Small real-provider pilot verifies all experiment dimensions and both frameworks |
| 9B: Evaluation web dashboard | Owner access, job control/history, output comparisons, artifacts/traces, metrics, exports | Owner can launch, cancel, reopen, and export real runs; unauthorized access rejected |
| 9C: Local benchmark readiness | Freeze scenarios/prompts/configuration; validate scoring and budget with pilot runs | Reproducible benchmark manifest and cost estimate; final cloud run ready |
| 10: Cloud and final evaluation | Deploy, run deployed acceptance checks and the budgeted final benchmark, prepare professor demonstration | R1–R11 evidence complete; cloud results/report exported; limitations and actual costs documented |

Phases may contain small testable checkpoints, but do not skip exit gates. Implement only the requested next phase. Update status after each implemented phase with files changed, verification, unresolved blockers, and the next step. Do not push, deploy, spend on a full benchmark, or make phone calls merely because this planning document was created; those are future execution steps under the user's instructions and configured budget.

## 13. Final professor-review package

Deliver the cloud application and setup instructions; the exact five-agent role diagram and 2/3 variants; Blackboard and direct-message flow examples; cross-framework A2A and two-tool MCP evidence; Pydantic response examples; guardrail and callback tests; inspectable traces/provenance; and repeated evaluation reports with actual outputs, cost/runtime estimates, failures, and limitations.

Include the tested dependency lockfiles, deployed commit, schema/prompt/model versions, scenario manifest, reproduction commands, and an R1–R11 checklist linking each claim to its evidence. Keep secrets, credentials, and raw personal identifiers out of exports.

Completion means the system has been exercised end to end, not merely that its interfaces or dashboard screens exist. Clearly separate completed, locally verified, cloud verified, and blocked capabilities.

## 14. Official implementation references

Check the current documentation and pin tested versions when each integration is implemented:

- [Google ADK shared session state](https://github.com/google/adk-docs/blob/main/docs/sessions/state.md)
- [Google ADK consuming A2A agents](https://github.com/google/adk-docs/blob/main/docs/a2a/quickstart-consuming.md)
- [Google ADK callbacks](https://github.com/google/adk-docs/blob/main/docs/callbacks/types-of-callbacks.md)
- [CrewAI A2A delegation](https://docs.crewai.com/en/learn/a2a-agent-delegation)
- [CrewAI MCP integration](https://docs.crewai.com/en/mcp/overview)
- [LiveKit outbound calling](https://docs.livekit.io/telephony/making-calls/outbound-calls/)

These references guide implementation; they are not evidence that the planned integrations have already passed project tests.
