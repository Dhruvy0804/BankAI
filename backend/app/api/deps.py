from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import APIError
from app.core.security import decode_token
from app.models import AuditLog, Customer
from app.services.banking import BankingService

bearer = HTTPBearer(auto_error=False)


def get_db(request: Request):
    with request.app.state.session_factory() as session:
        try:
            yield session
            session.commit()
        except APIError as error:
            session.rollback()
            if error.action:
                session.add(
                    AuditLog(
                        customer_id=error.actor,
                        action=error.action,
                        resource_type=error.resource_type,
                        resource_id=error.resource_id,
                        outcome=error.code,
                        request_id=request.state.request_id,
                    )
                )
                session.commit()
            raise
        except Exception:
            session.rollback()
            raise


DB = Annotated[Session, Depends(get_db, scope="function")]


def current_customer(
    request: Request,
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
):
    if credentials is None:
        raise APIError(
            401,
            "UNAUTHENTICATED",
            "A valid access token is required.",
            action="authentication_failed",
        )
    identity = decode_token(credentials.credentials, request.app.state.settings)
    customer = db.get(Customer, identity)
    if customer is None or not customer.is_active:
        raise APIError(
            401,
            "UNAUTHENTICATED",
            "A valid access token is required.",
            action="authentication_failed",
        )
    return customer


Actor = Annotated[Customer, Depends(current_customer)]


def banking_service(request: Request, db: DB, customer: Actor):
    return BankingService(db, customer.id, request.state.request_id, request.app.state.settings)


Banking = Annotated[BankingService, Depends(banking_service)]
