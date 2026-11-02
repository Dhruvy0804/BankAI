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
## Phase 4 web walkthrough

1. Start the database/backend and frontend using README instructions.
2. Open http://localhost:5173 and use the Local demo credentials disclosure.
3. Sign in as Demo Asha. View backend-fetched balances, activity and KYC.
4. Open Accounts and refresh the selected account's balance.
5. Open Transactions; filter by debit, date, amount or account and page results.
   Search applies only to the visible page and is labelled accordingly.
6. Open Cards, request a block, and cancel first to show no status change.
   Request again and confirm to update the demo card.
7. Open Loans, calculate EMI with fictional inputs, check demo eligibility,
   request an application and explicitly confirm the server-returned details.
8. Create a fictional support ticket and open its details in Support history.
9. Refresh to demonstrate session restoration; sign out and sign in as Demo
   Ravi to show customer-specific data. Do not share bearer tokens.

Confirmed operations persist in the demo database. For a repeatable walkthrough
without changing demo records, use the disposable browser smoke test described
in TESTING.md.

## Show the five-agent workflow to an evaluator

1. Sign in to a fictional customer account and open **Text assistant**.
   Open **View my demo banking records** to show that customer's current
   accounts, transaction history, masked cards and loans side by side. Use
   **Refresh demo records** after any confirmed action.
2. Start a new conversation and click **Fill five-agent demo question**. Review
   the account, card, loan and support request, then send it. This is read-only.
3. Under the saved answer, open **Agent activity and shared context**. The five
   role cards identify the ADK supervisor and four CrewAI specialists. Each
   specialist card shows its verified output, MCP tools and any earlier agent
   result it used. An agent not selected by the supervisor is labelled **Not
   called for this question**.
4. Scroll through the ordered event timeline to show A2A delegation, MCP tool
   requests/results, Blackboard consumption and output validation. Open
   **Verified shared artifacts** for the structured Pydantic records.

The supervisor chooses relevant agents; a broad question invites all four
specialists but does not guarantee every role will run. Show the actual trace
and explain any unused role instead of claiming all five participated.
