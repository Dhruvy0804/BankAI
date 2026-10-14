# Demo guide: current checkpoint

1. Follow README setup and start the database, API and frontend.
2. Open `http://localhost:5173`.
3. Check that Backend API and PostgreSQL show Connected.
4. Open the build roadmap to see the phased delivery sequence.
5. Open `http://127.0.0.1:8000/docs` to inspect and exercise BankSim APIs.

Phase 2 additionally demonstrates database migrations and fictional data:
run `python -m alembic upgrade head` and `python -m app.seed.demo_data` with
the backend virtual environment. Run the seed again to see zero inserts.
Use the integration suite in TESTING.md to verify constraints and migration
roundtrips safely in isolated schemas. Do not downgrade the demo database.

## Phase 3 banking API demo

1. Generate a local `.env` with `python -m app.core.setup_local` if absent.
   Preserve an existing file and configure a strong signing key there.
2. Apply migrations through `0002` and seed the fictional accounts.
3. In `/docs`, use `POST /api/v1/auth/login` with the demo credentials in README.
4. Use the returned access token in Swagger's Authorize Bearer field.
5. List your accounts, retrieve a balance, and page/filter transactions.
6. View cards and KYC; calculate an EMI with the example in API_SPEC.md.
7. Request a card block. Show that HTTP 202 returns a pending action and
   the card remains active. Explicitly confirm to show the status change.
8. Replay the confirmation to demonstrate 409 and no repeated write.
9. Request/confirm a simulated loan application and create a support ticket.
10. Sign in as a second demo customer. An account/card ID copied from the
    first customer must return 404. Do not disclose or share bearer tokens.

Confirmed demo operations persist; repeated seeding does not undo them.
Use the isolated integration tests for repeatable fresh-state scenarios.
The frontend still shows infrastructure status; browser login/dashboard
pages arrive in Phase 4. Agents, voice and evaluation remain later work.
