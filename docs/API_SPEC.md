# Phase 3 API contract

Interactive OpenAPI: `http://127.0.0.1:8000/docs`. Base path `/api/v1`.
All banking routes require `Authorization: Bearer <access_token>`.
Only registration/login and `/health`, `/ready` are unauthenticated.
Banking responses include `simulated: true`. Decimal amounts serialize as
strings. Request bodies reject extra fields, including customer IDs and roles.

## Authentication

| Method | Path | Result |
|---|---|---|
| POST | `/auth/register` | 201 profile and pending demo KYC; no funded account |
| POST | `/auth/login` | Access token, bearer type, expiry in seconds |
| GET | `/auth/me`, `/customers/me` | Own profile without password hash |

Login JSON: `{"email":"demo.asha@bankai.example","password":"BankAI-demo-only-2026!"}`.
Registration adds `full_name` (2–120 characters), requires a password of
12–128 characters, and accepts no role. Emails are normalized to lowercase.
Login and registration share a 10-attempt/client-IP/60-second limit per process.

JWTs use HS256, pinned issuer/audience, and required subject/expiry/issued-at
claims. Customers are reloaded and must be active on protected requests.
TTL is `ACCESS_TOKEN_EXPIRE_MINUTES`, default 30, allowed 1–120. No refresh
or logout/revocation endpoint exists; deactivate a customer or rotate the
signing key to invalidate access as appropriate for this local demo.

## Banking reads

| Method | Path | Result |
|---|---|---|
| GET | `/accounts` | Own account list |
| GET | `/accounts/{account_id}` | One owned account |
| GET | `/accounts/{account_id}/balance` | Account ID, currency and balance |
| GET | `/accounts/{account_id}/transactions` | Owned, filtered transaction page |
| GET | `/transactions` | Transactions across own accounts, with filters |
| GET | `/transactions/{transaction_id}` | One owned transaction |
| GET | `/cards`, `/cards/{card_id}` | Own masked demo cards |
| GET | `/kyc/status` | Own synthetic KYC status |
| GET | `/loans` | Own simulated loan records |
| GET | `/support/tickets`, `/support/tickets/{ticket_id}` | Own tickets |

Transaction filters: `account_id`, `transaction_type` (credit/debit), `status`
(completed/pending/failed), `date_from`/`date_to` (inclusive UTC dates), and
`min_amount`/`max_amount`. `limit` is 1–100, default 20. `cursor` is an integer
offset, default 0, maximum 100000. Response has `items` and `next_cursor`
(null at the end). Sort is occurred-at descending, then UUID descending.
Offset pagination is not a snapshot: concurrent inserts can shift pages.
Keep filters unchanged while paging. Foreign account filters return 404.

## Confirmed simulated operations

| Method | Path | Result |
|---|---|---|
| POST | `/cards/{card_id}/block` | 202 pending action; empty body or `{}` |
| POST | `/cards/{card_id}/block/confirm` | 200 blocked card after confirmation |
| POST | `/loans/emi` | Monthly payment, total payment and interest |
| POST | `/loans/eligibility` | Demo eligibility, reasons and documented rule |
| POST | `/loans/applications` | 202 pending action; does not create a loan |
| POST | `/loans/applications/{action_id}/confirm` | 201 submitted demo loan |
| POST | `/support/tickets` | 201 open ticket |

EMI body:

```json
{"principal":"12000.00","annual_interest_rate":"12","tenure_months":12}
```

Decimal calculation uses round-half-up to two places and handles zero
interest. Totals use unrounded payment, so multiplying displayed monthly
payment may differ by a few paise.

Loan eligibility/application body:

```json
{
  "loan_type":"personal",
  "requested_amount":"12000.00",
  "annual_interest_rate":"12",
  "tenure_months":12,
  "monthly_income":"50000.00",
  "monthly_obligations":"5000.00"
}
```

Types: personal/education/home. Principal/income positive; obligations
nonnegative. Money <= 100000000 with at most two decimal places. Annual
rate 0–100, at most four decimal places; tenure 1–600 whole months.
Demo eligibility requires verified KYC, EMI <= 40% of income after
obligations, and principal <= 24 times monthly income. Ineligible
applications return 422. This is not a credit assessment or approval.

Pending responses contain `id`, `kind`, `resource_id`, bound `payload`,
`expires_at`, `status`, `result_id`, and `confirmation_required: true`.
Card confirmation: `{"action_id":"pending-uuid","confirmation":true}`.
Loan confirmation: `{"confirmation":true}`; changed inputs are rejected.
Only JSON boolean true is accepted, not `"yes"`, 1, or false.

Actions bind the user and exact operation, expire after
`CONFIRMATION_EXPIRE_SECONDS` (default 300), and execute once. Confirmation
rechecks active user, ownership/status or loan eligibility. Row locks and
one transaction cover action consumption, banking changes and success audit.
Repeat/concurrent confirmations return 409 after one execution. No action
cancellation endpoint is implemented yet.

Support body:

```json
{"category":"dispute","subject":"Demo charge question","description":"Please review this fictional charge.","priority":"normal"}
```

Categories: account/card/loan/dispute/other. Priorities: low/normal/high/urgent.
Subject: 3–200 characters; description: 5–2000. Explicit creation expresses
user intent; a ticket does not establish that fraud occurred.

## Errors and audits

Errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`
and matching `X-Request-ID`. Passwords, tokens, rejected input values and
raw SQL errors are not echoed.

- 401 invalid credentials, missing/invalid/expired token or inactive customer.
- 404 absent or other-customer resource, with the same non-disclosing message.
- 409 used/expired/mismatched action or conflicting current state.
- 422 invalid inputs/ranges, extra body fields or demo ineligibility.
- 429 authentication throttle, with Retry-After.
- 503 missing signing configuration or database failure.

Sensitive reads/writes and failed authentication/ownership checks create
minimal audit metadata. Failures roll back writes before recording a denial.
There is no public audit-log endpoint. `/health` checks process liveness;
`/ready` checks database connectivity, not schema version or signing key.
AI, RAG, voice and evaluation endpoints remain later work.
