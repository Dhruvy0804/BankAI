# API status

Implemented OpenAPI contract: `http://127.0.0.1:8000/docs`.

| Route | Success | Failure |
|---|---|---|
| GET `/health` | 200: status=ok, service=bankai-api, version=0.1.0 | Independent of database |
| GET `/ready` | 200: status=ready, database=connected | 503: DATABASE_UNAVAILABLE |

Responses carry a generated `X-Request-ID`. Readiness errors include the
same ID in `{error: {code, message, request_id}}`. Raw exceptions and
connection credentials are never returned. These infrastructure endpoints
contain no user data and are intentionally unauthenticated for local use.

Authentication, BankSim, chat, RAG, voice and owner evaluation endpoints
remain planned in the project specification. No placeholder endpoint
claims to perform those operations.

Phase 2 adds persistence and local migration/seed commands only; this HTTP
contract is unchanged. Database records are not publicly exposed through
new API endpoints. `/ready` still checks connectivity, not migration version.
