"""Create the sole cloud demo owner from a private terminal, without public signup."""

from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import passwords
from app.db.session import build_engine
from app.models import AuditLog, Customer, KYCRecord
from app.schemas import Register


def create_owner(db: Session, data: Register) -> Customer:
    if str(data.email).endswith("@bankai.example"):
        raise ValueError("Use a private owner email outside the published demo domain.")
    if db.scalar(select(Customer.id).where(Customer.email == str(data.email))):
        raise ValueError("That owner email is already registered.")
    owner = Customer(
        full_name=data.full_name,
        email=str(data.email),
        password_hash=passwords.hash(data.password.get_secret_value()),
    )
    db.add(owner)
    db.flush()
    db.add(KYCRecord(customer_id=owner.id, status="pending", notes="Fictional cloud demo account."))
    db.add(AuditLog(
        customer_id=owner.id, action="cloud_owner_bootstrap", resource_type="customers",
        resource_id=owner.id, outcome="success", request_id="cloud-owner-bootstrap",
    ))
    return owner


def main():
    settings = Settings()
    if settings.app_env != "cloud_demo" or not settings.auth_configured:
        raise ValueError("Cloud owner setup requires cloud_demo and a valid APP_SECRET_KEY.")
    data = Register(
        full_name=input("Owner name: ").strip(),
        email=input("Owner email: ").strip(),
        password=getpass("Owner password (12+ characters): "),
    )
    engine = build_engine(settings)
    try:
        with Session(engine) as db, db.begin():
            owner = create_owner(db, data)
            print(f"Owner customer ID: {owner.id}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
