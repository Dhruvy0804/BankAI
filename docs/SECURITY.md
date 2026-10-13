# Security status

BankAI is local-only development with fictional records and no implemented
authentication yet. Bind development services to loopback; Compose binds
all published ports to 127.0.0.1. Do not expose this scaffold publicly.
Only explicit local origins are permitted by backend CORS.

Database connection failures are sanitized. Request IDs are generated
server-side. `.env`, virtual environments, caches and generated output
are ignored. `.env.example` contains local demo credentials/placeholders
only. Real bank credentials or identity documents must never be used.

Upcoming mandatory controls: hashed passwords, verified identity,
service-layer ownership checks, expiring action confirmations, audit
records without secrets, owner-only evaluation access, isolated fixtures,
bounded jobs, and sanitized exports. Until those are implemented and
tested, there is no login, evaluator account or private evaluation API.

Phase 2 adds fictional account records and salted Argon2 password hashes,
but still has no login or banking read/write endpoints. The database rejects
cross-customer card/account links; service-layer authorization remains a
mandatory Phase 3 task. Only masked demo card identifiers fit the schema.
Seed CLI is limited to development mode and local/container hosts, adds
missing records atomically and never resets existing passwords or balances.
Demo passwords are documented for local use only. Never deploy this seeded
development environment publicly.
