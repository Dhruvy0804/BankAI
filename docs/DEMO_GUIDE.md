# Demo guide: current checkpoint

1. Follow README setup and start the database, API and frontend.
2. Open `http://localhost:5173`.
3. Check that Backend API and PostgreSQL show Connected.
4. Open the build roadmap to see the phased delivery sequence.
5. Open `http://127.0.0.1:8000/docs` to inspect health/readiness contracts.

Phase 2 additionally demonstrates database migrations and fictional data:
run `python -m alembic upgrade head` and `python -m app.seed.demo_data` with
the backend virtual environment. Run the seed again to see zero inserts.
Use the integration suite in TESTING.md to verify constraints and migration
roundtrips safely in isolated schemas. Do not downgrade the demo database.

Local demo credentials are listed in README, but login and banking pages
are not implemented yet. The UI shows infrastructure status, not customer
balances. Agents, voice sessions and evaluation results are still planned.
