# Phase 9 benchmark readiness (2026-11-20)

This is a provider-free checkpoint, not a measured comparison. No evaluation
worker or paid benchmark has run.

## Frozen comparison design

- The versioned dataset has 60 fictional banking cases across seven categories:
  9 account/transaction, 9 card, 9 loan, 9 policy, 8 support/dispute,
  8 multi-turn/cross-domain, and 8 authorization/confirmation/injection.
- Eight cases contain a prior question, nine require policy citations when
  answered, and eight prohibit banking tool calls.
- Five cells compare 2, 3 and 5 total agents using Blackboard/ReAct, plus
  5-agent direct messaging/ReAct and 5-agent Blackboard/few-shot prompts.
- Three repeats per case and cell produce 900 attempts and 1,020 conversation
  turns. A seeded shuffle fixes attempt order. Saved plans record dataset hash,
  selected cells, repeats, seed, model, framework versions, and agent code hash.
  A model or code change requires a new plan before execution.
- Automated scoring checks status, retrieved tool receipts, required facts in
  both receipts and the visible answer, source IDs, cross-agent consumption,
  and actual tool-call count for no-tool cases. Human review is still required
  for answer quality and nuanced banking correctness.

The 60 cases passed schema/uniqueness/category checks. All nine loan case
values were recomputed with BankAI's EMI calculator. The isolated runner has
ten embedded chunks from three approved fictional policy documents. Cases
are scenario variations, so the 60 rows are not 60 independent topics.

## Provisional token and cost forecast

The local database contained 21 earlier completed `gemini-3.5-flash-lite`
agent runs with complete usage at this checkpoint. Their rounded average was
11,952 input and 592 output tokens per run. Multiplying by 1,020 planned
turns gives **12,191,040 input** and **603,840 output** tokens. This sample
mainly reflects existing app use, not balanced 2/3/5 evaluation traffic;
prompt style, case complexity, and retries can change actual usage materially.

[Google's Gemini API pricing page](https://ai.google.dev/gemini-api/docs/pricing)
listed standard paid-tier `gemini-3.5-flash-lite` text rates of **$0.30 per
million input tokens** and **$2.50 per million output tokens** when checked
on 2026-11-20. At those rates the token-only illustration is **about $5.17**
for 900 attempts, before retries, other services, taxes, or price changes.
This is neither a spending cap nor an observed benchmark cost. Free-tier
availability and quotas are account-specific. The evaluation dashboard
requires an owner-entered dated price snapshot and explicit acknowledgement
before live execution; a rate must be checked again at that time.

## Still required for Phase 9 exit gates

1. With an approved provider budget, run a small real-provider pilot that
   covers all five cells, multi-turn and policy cases, and both ADK/CrewAI
   paths. Confirm complete usage, latency, output, A2A/MCP traces, and errors.
2. Review pilot answers and scoring manually. Correct scenario expectations
   or scoring rules where evidence warrants it, then freeze a new dataset hash.
3. Recalculate the forecast from pilot results by cell, record variance and
   failed attempts, and verify the owner can launch, cancel, reopen, compare,
   review, and export real runs. Keep unauthorized access tests passing.

The 900-attempt study and cloud verification belong to Phase 10 after a
reviewed budget and pilot. No comparative quality or runtime winner is claimed.
