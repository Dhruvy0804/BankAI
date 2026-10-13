import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

from pwdlib import PasswordHash
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import ROOT, Settings
from app.db.session import build_engine
from app.models import (
    Account,
    AuditLog,
    Card,
    Customer,
    KYCRecord,
    Loan,
    PolicyChunk,
    PolicyDocument,
    SupportTicket,
    Transaction,
)

DEMO_PASSWORD = "BankAI-demo-only-2026!"
SEED_DATE = datetime(2026, 10, 1, 9, tzinfo=UTC)


def demo_id(key: str):
    return uuid5(NAMESPACE_URL, f"bankai-demo-v1/{key}")


def seed_demo(session: Session) -> dict[str, int]:
    """Insert stable demo IDs in the caller's transaction; never overwrite rows."""
    session.execute(text("SELECT pg_advisory_xact_lock(2026101302)"))
    counts: dict[str, int] = {}

    def add(model, key, **values):
        result = session.execute(
            insert(model)
            .values(id=demo_id(key), **values)
            .on_conflict_do_nothing(index_elements=["id"])
            .returning(model.id)
        )
        inserted = int(result.scalar_one_or_none() is not None)
        counts[model.__tablename__] = counts.get(model.__tablename__, 0) + inserted

    for index, name in enumerate(("Asha", "Ravi", "Mira"), 1):
        key = f"customer-{index}"
        customer_id = demo_id(key)
        existing = session.scalar(select(Customer.id).where(Customer.id == customer_id))
        if existing is None:
            add(
                Customer,
                key,
                full_name=f"Demo {name}",
                email=f"demo.{name.lower()}@bankai.example",
                password_hash=PasswordHash.recommended().hash(DEMO_PASSWORD),
                phone=f"DEMO-PHONE-{index:03d}",
                created_at=SEED_DATE,
            )
        else:
            counts.setdefault("customers", 0)
        add(
            KYCRecord,
            f"kyc-{index}",
            customer_id=customer_id,
            status=("verified", "pending", "rejected")[index - 1],
            notes="Synthetic KYC scenario; no identity documents collected.",
            last_updated=SEED_DATE,
        )
        add(
            Loan,
            f"loan-{index}",
            customer_id=customer_id,
            loan_type="personal",
            requested_amount=Decimal("100000.00") * index,
            annual_interest_rate=Decimal("10.5000"),
            tenure_months=12 * index,
            status=("draft", "submitted", "approved_demo")[index - 1],
            created_at=SEED_DATE,
        )
        add(
            SupportTicket,
            f"ticket-{index}",
            customer_id=customer_id,
            category="demo_support",
            subject=f"Demo support scenario {index}",
            description="Fictional banking inquiry.",
            status=("open", "in_progress", "resolved")[index - 1],
            priority=("normal", "high", "low")[index - 1],
            created_at=SEED_DATE,
            updated_at=SEED_DATE,
        )

    for index, owner in enumerate((1, 1, 2, 3), 1):
        account_id = demo_id(f"account-{index}")
        customer_id = demo_id(f"customer-{owner}")
        entries = (
            ("credit", Decimal("10000.00") * index, "Demo opening deposit"),
            ("debit", Decimal("125.50"), "Demo grocery purchase"),
            ("credit", Decimal("2500.00"), "Demo salary credit"),
            ("debit", Decimal("499.25"), "Demo utility payment"),
            ("debit", Decimal("50.00"), "Demo transport fare"),
        )
        balance = sum(
            (amount if kind == "credit" else -amount for kind, amount, _ in entries),
            Decimal("0.00"),
        )
        add(
            Account,
            f"account-{index}",
            customer_id=customer_id,
            account_number=f"DEMO-ACCT-{index:04d}",
            account_type="current" if index == 2 else "savings",
            currency="INR",
            balance=balance,
            status="active",
            created_at=SEED_DATE,
        )
        for position, (kind, amount, description) in enumerate(entries):
            add(
                Transaction,
                f"transaction-{index}-{position}",
                account_id=account_id,
                transaction_type=kind,
                amount=amount,
                description=description,
                merchant="Demo Merchant" if kind == "debit" else None,
                reference_code=f"DEMO-TXN-{index:04d}-{position:02d}",
                status="completed",
                occurred_at=SEED_DATE + timedelta(days=position),
            )
        add(
            Card,
            f"card-{index}",
            customer_id=customer_id,
            account_id=account_id,
            masked_card_number=f"DEMO-XXXX-{index:04d}",
            card_type="debit",
            status="blocked" if index == 2 else "active",
            expiry_month=12,
            expiry_year=2030,
            created_at=SEED_DATE,
        )

    policy = (ROOT / "data/banking_policies/demo_overview.md").read_text(encoding="utf-8")
    checksum = sha256(policy.encode()).hexdigest()
    # Content-derived keys permit versioned seed policies, while stable content is idempotent.
    policy_key = f"policy-{checksum}"
    add(
        PolicyDocument,
        policy_key,
        title="Synthetic demo banking overview",
        source="demo_overview.md",
        checksum=checksum,
        ingested_at=SEED_DATE,
    )
    add(
        PolicyChunk,
        f"{policy_key}-0",
        document_id=demo_id(policy_key),
        chunk_index=0,
        text=policy,
        section="Demo scope",
        ingested_at=SEED_DATE,
    )
    add(
        AuditLog,
        "audit-seed",
        customer_id=None,
        action="demo_seed",
        resource_type="dataset",
        resource_id=None,
        outcome="created",
        request_id="demo-seed-v1",
        created_at=SEED_DATE,
    )
    return counts


def require_local_demo(settings: Settings):
    url = make_url(settings.database_url)
    if settings.app_env != "development" or url.host not in {"localhost", "127.0.0.1", "::1", "db"}:
        raise ValueError("Demo seeding is allowed only in a local development environment.")


def main():
    settings = Settings()
    require_local_demo(settings)
    engine = build_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            counts = seed_demo(session)
        print(json.dumps({"inserted": counts}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
