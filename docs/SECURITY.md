# Security status

Phase 1 is a local-only infrastructure shell with no account records or
authentication. Bind development services to loopback; Compose binds
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
