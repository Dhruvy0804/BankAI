from decimal import Decimal
from uuid import uuid4

import pytest
from pwdlib import PasswordHash
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.db.base import Base
from app.models import Account, Card, Customer, KYCRecord, Loan, PolicyChunk, Transaction
from app.seed.demo_data import DEMO_PASSWORD, demo_id, seed_demo, seed_owner_demo

pytestmark = pytest.mark.integration


def test_migration_roundtrip_and_model_consistency(migrated_db):
    connection, config = migrated_db
    schema = connection.dialect.default_schema_name
    assert set(Base.metadata.tables) <= set(inspect(connection).get_table_names(schema=schema))
    command.check(config)
    command.downgrade(config, "base")
    assert not (set(Base.metadata.tables) & set(inspect(connection).get_table_names(schema=schema)))
    command.upgrade(config, "head")
    assert len(inspect(connection).get_table_names(schema=schema)) == len(Base.metadata.tables) + 1


def test_repeat_seed_preserves_changes_and_passwords(migrated_db):
    connection, _ = migrated_db
    with Session(connection) as session, session.begin():
        first = seed_demo(session)
        assert first == {
            "customers": 3,
            "kyc_records": 3,
            "loans": 3,
            "support_tickets": 3,
            "accounts": 4,
            "transactions": 20,
            "cards": 4,
            "policy_documents": 1,
            "policy_chunks": 1,
            "audit_logs": 1,
        }
        customer = session.get(Customer, demo_id("customer-1"))
        old_hash = customer.password_hash
        assert old_hash != DEMO_PASSWORD
        assert PasswordHash.recommended().verify(DEMO_PASSWORD, old_hash)
        assert len(customer.accounts) == 2
        assert customer.kyc.status == "verified"
        account = customer.accounts[0]
        account.balance = Decimal("999.99")
        card = session.get(Card, demo_id("card-1"))
        card.status = "blocked"
        session.flush()
        assert all(count == 0 for count in seed_demo(session).values())
        session.expire_all()
        assert account.balance == Decimal("999.99")
        assert card.status == "blocked"
        assert customer.password_hash == old_hash
        assert session.scalar(select(func.count()).select_from(Customer)) == 3


def test_owner_demo_profile_is_independent_and_idempotent(migrated_db):
    connection, _ = migrated_db
    owner_id = uuid4()
    with Session(connection) as session, session.begin():
        seed_demo(session)
        session.add(Customer(id=owner_id, full_name="Project Owner", email="owner@example.org", password_hash="test-only"))
        session.add(KYCRecord(customer_id=owner_id, status="pending", notes="Existing owner status"))
        session.flush()
        first = seed_owner_demo(session, owner_id)
        assert first == {"kyc_records": 0, "loans": 1, "support_tickets": 1,
                         "accounts": 2, "transactions": 6, "cards": 2}
        assert session.scalar(select(KYCRecord).where(KYCRecord.customer_id == owner_id)).status == "pending"
        accounts = session.scalars(select(Account).where(Account.customer_id == owner_id)).all()
        assert {account.balance for account in accounts} == {Decimal("25000.00"), Decimal("4500.00")}
        for account in accounts:
            total = sum((t.amount if t.transaction_type == "credit" else -t.amount for t in account.transactions), Decimal("0.00"))
            assert account.balance == total
        card = session.scalar(select(Card).where(Card.customer_id == owner_id, Card.status == "active"))
        card.status = "blocked"
        assert all(count == 0 for count in seed_owner_demo(session, owner_id).values())
        session.flush()
        assert card.status == "blocked"
        assert session.scalar(select(func.count()).select_from(Account).where(Account.customer_id == demo_id("customer-1"))) == 2


def test_money_and_seed_relationships(migrated_db):
    connection, _ = migrated_db
    with Session(connection) as session, session.begin():
        seed_demo(session)
        for account in session.scalars(select(Account)):
            assert isinstance(account.balance, Decimal)
            total = sum(
                (
                    t.amount if t.transaction_type == "credit" else -t.amount
                    for t in account.transactions
                ),
                Decimal("0.00"),
            )
            assert account.balance == total
            assert all(t.occurred_at.tzinfo is not None for t in account.transactions)
        for card in session.scalars(select(Card)):
            assert card.account.customer_id == card.customer_id
        chunk = session.scalar(select(PolicyChunk))
        assert chunk.embedding is None
        assert chunk.document.source == "demo_overview.md"


@pytest.mark.parametrize(
    "model,key,field,value",
    [
        (Account, "account-1", "balance", Decimal("-0.01")),
        (Account, "account-1", "balance", Decimal("NaN")),
        (Account, "account-1", "customer_id", uuid4()),
        (Transaction, "transaction-1-0", "amount", Decimal(0)),
        (Card, "card-1", "expiry_month", 13),
        (Card, "card-1", "account_id", demo_id("account-3")),
        (Card, "card-1", "masked_card_number", "1234567890123456"),
        (Loan, "loan-1", "tenure_months", 0),
        (Loan, "loan-1", "annual_interest_rate", Decimal(101)),
        (Customer, "customer-2", "email", "demo.asha@bankai.example"),
    ],
)
def test_invalid_records_rejected(migrated_db, model, key, field, value):
    connection, _ = migrated_db
    with Session(connection) as session, session.begin():
        seed_demo(session)
        with pytest.raises(IntegrityError), session.begin_nested():
            setattr(session.get(model, demo_id(key)), field, value)
            session.flush()


def test_vector_storage_and_unique_chunk_position(migrated_db):
    connection, _ = migrated_db
    with Session(connection) as session, session.begin():
        seed_demo(session)
        chunk = session.scalar(select(PolicyChunk))
        chunk.embedding = [0.1, 0.2, 0.3]
        chunk.embedding_model = "synthetic-test-vector"
        session.flush()
        assert session.scalar(text("SELECT vector_dims(embedding) FROM policy_chunks")) == 3
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(PolicyChunk(document_id=chunk.document_id, chunk_index=0, text="duplicate"))
            session.flush()
