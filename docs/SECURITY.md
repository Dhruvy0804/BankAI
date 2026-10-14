# Security status

BankAI is local-only development with fictional records and JWT authentication.
Bind development services to loopback; Compose binds
all published ports to 127.0.0.1. Do not expose this scaffold publicly.
Only explicit local origins are permitted by backend CORS.

Database connection failures are sanitized. Request IDs are generated
server-side. `.env`, virtual environments, caches and generated output
are ignored. `.env.example` contains local demo credentials/placeholders
only. Real bank credentials or identity documents must never be used.

Phase 3 implements Argon2 password hashing, signed expiring access tokens,
active-customer checks, server-side ownership checks and minimal audit logs.
JWT algorithms, issuer and audience are pinned, and required claims are
validated. The verified subject is the only source of customer identity.
Registration cannot set customer IDs or roles. Unknown and wrong-password
logins use the same response; unknown users still perform password-hash work.

Confirmation requests have server-stored operation details, owner, expiry
and state. Only explicit true plus the exact action ID can execute. User,
action and relevant banking records are locked/revalidated before commit.
Concurrent/replayed confirmation cannot duplicate a write. Any storage or
audit failure rolls back sensitive changes; denial audits use a fresh
transaction after the failed operation is rolled back. Inputs and outputs
use Pydantic schemas; errors do not echo rejected values or SQL details.

Login/registration throttling is bounded and process-local (10 attempts
per IP per minute), not a distributed production limiter. No refresh-token
rotation, password reset, MFA, or per-token revocation is implemented.
Default access lifetime is 30 minutes. Customer deactivation is checked
on each request; signing-key rotation invalidates existing tokens.

`app.core.setup_local` creates `.env` with a random secret and never prints
it or overwrites an existing file. Missing/placeholder signing keys fail
closed for auth; health checks can still run. Never share `.env` or bearer
tokens. Only local known origins are permitted; CORS is not authorization.

The database also rejects cross-customer card/account links. Only masked
demo card identifiers fit the schema.
Seed CLI is limited to development mode and local/container hosts, adds
missing records atomically and never resets existing passwords or balances.
Demo passwords are documented for local use only. Never deploy this seeded
development environment publicly.

Evaluation roles/access, agent tool controls, prompt-injection defenses,
voice tokens and export sanitization are later phases, not current claims.

Implementation references: [FastAPI security](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
and [PyJWT claim validation](https://pyjwt.readthedocs.io/en/latest/usage.html).

Phase 4 stores only the access token and expiry in `sessionStorage`, not
passwords or customer banking records. On sign-out, expiry or a protected
401, the session and displayed data are cleared; in-flight read requests are
aborted and stale completions are ignored. No token is placed in a URL.
Sessions remain tab-local and are still validated by the backend. Storage is
JavaScript-readable and is suitable only for this local prototype; use
HttpOnly-cookie sessions and CSRF protection before public deployment.
Client sign-out does not revoke an already copied token server-side.

Confirmation dialogs use the native modal dialog for focus containment,
explicit buttons, exact server-returned action details and expiry. The UI
prevents duplicate submissions, but server checks remain authoritative.
No frontend-only role/visibility control is treated as authorization.
