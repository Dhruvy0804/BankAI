from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import APIError
from app.models import Loan
from app.schemas import LoanInput
from app.seed.demo_data import demo_id, seed_demo
from app.services.banking import BankingService

pytestmark = pytest.mark.integration


def test_simultaneous_confirmation_creates_one_loan(migrated_db):
    connection, _ = migrated_db
    settings = Settings(_env_file=None)
    owner = demo_id("customer-1")
    with Session(connection) as session, session.begin():
        seed_demo(session)
        service = BankingService(session, owner, "prepare-concurrent-test", settings)
        action_id = service.request_loan(
            LoanInput(
                loan_type="personal",
                requested_amount="12000",
                annual_interest_rate="12",
                tenure_months=12,
                monthly_income="50000",
            )
        ).id
    connection.commit()
    schema = connection.dialect.default_schema_name
    # Independent connections model two real HTTP transactions, not one shared Session.
    engine = create_engine(
        settings.database_url,
        connect_args={"options": f"-c search_path={schema},public -c statement_timeout=10000"},
    )
    gate = Barrier(2)

    def confirm():
        try:
            with Session(engine) as session, session.begin():
                gate.wait(timeout=10)
                BankingService(session, owner, "parallel-confirm", settings).confirm_loan(
                    action_id, True
                )
            return "executed"
        except APIError as error:
            return error.code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(confirm) for _ in range(2)]
            outcomes = sorted(future.result(timeout=20) for future in futures)
        assert outcomes == ["ACTION_USED", "executed"]
        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Loan)) == 4
    finally:
        engine.dispose()


def test_service_cannot_commit_without_confirmation(migrated_db):
    connection, _ = migrated_db
    with Session(connection) as session, session.begin():
        seed_demo(session)
        service = BankingService(
            session, demo_id("customer-1"), "test-missing-confirm", Settings(_env_file=None)
        )
        action = service.request_card_block(demo_id("card-1"))
        with pytest.raises(APIError) as error:
            service.confirm_card_block(demo_id("card-1"), action.id)
        assert error.value.code == "CONFIRMATION_REQUIRED"
