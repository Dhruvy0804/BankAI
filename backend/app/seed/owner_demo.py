"""Seed the configured project owner's fictional banking profile locally."""

import json
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import build_engine
from app.seed.demo_data import require_demo_seed, seed_owner_demo


def main():
    settings = Settings()
    require_demo_seed(settings)
    if not settings.phone_owner_customer_id:
        raise ValueError("PHONE_OWNER_CUSTOMER_ID is required.")
    engine = build_engine(settings)
    try:
        with Session(engine) as session, session.begin():
            counts = seed_owner_demo(session, UUID(settings.phone_owner_customer_id))
        print(json.dumps({"inserted": counts}, indent=2))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
