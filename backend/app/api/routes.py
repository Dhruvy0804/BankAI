from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.api.deps import DB, Actor, Banking
from app.core.errors import APIError
from app.core.security import DUMMY_HASH, issue_token, passwords, signing_key
from app.models import AuditLog, Customer, KYCRecord
from app.schemas import (
    AccountOut,
    BalanceOut,
    CardConfirm,
    CardOut,
    Confirm,
    CustomerOut,
    EligibilityOut,
    EMIInput,
    EMIOut,
    Input,
    KYCOut,
    LoanInput,
    LoanOut,
    Login,
    PendingOut,
    Register,
    TicketInput,
    TicketOut,
    TokenOut,
    TransactionOut,
    TransactionPage,
    TransactionQuery,
)
from app.services.banking import calculate_emi

router = APIRouter(prefix="/api/v1")


def throttle(request):
    request.app.state.login_limiter.check(request.client.host if request.client else "unknown")
    signing_key(request.app.state.settings)


@router.post("/auth/register", response_model=CustomerOut, status_code=201, tags=["Authentication"])
def register(data: Register, request: Request, db: DB):
    throttle(request)
    if db.scalar(select(Customer.id).where(Customer.email == str(data.email))):
        raise APIError(409, "REGISTRATION_UNAVAILABLE", "Registration cannot be completed.")
    customer = Customer(
        full_name=data.full_name,
        email=str(data.email),
        password_hash=passwords.hash(data.password.get_secret_value()),
    )
    db.add(customer)
    db.flush()
    db.add(
        KYCRecord(
            customer_id=customer.id,
            status="pending",
            notes="Demo registration; no documents collected.",
        )
    )
    db.add(
        AuditLog(
            customer_id=customer.id,
            action="register",
            resource_type="customers",
            resource_id=customer.id,
            outcome="success",
            request_id=request.state.request_id,
        )
    )
    return customer


@router.post("/auth/login", response_model=TokenOut, tags=["Authentication"])
def login(data: Login, request: Request, db: DB):
    throttle(request)
    customer = db.scalar(select(Customer).where(Customer.email == str(data.email)))
    valid = passwords.verify(
        data.password.get_secret_value(), customer.password_hash if customer else DUMMY_HASH
    )
    if not valid or customer is None or not customer.is_active:
        raise APIError(
            401, "INVALID_CREDENTIALS", "Invalid email or password.", action="login_failed"
        )
    db.add(
        AuditLog(
            customer_id=customer.id,
            action="login",
            resource_type="customers",
            resource_id=customer.id,
            outcome="success",
            request_id=request.state.request_id,
        )
    )
    return TokenOut(
        access_token=issue_token(customer.id, request.app.state.settings),
        expires_in=request.app.state.settings.access_token_expire_minutes * 60,
    )


@router.get("/auth/me", response_model=CustomerOut, tags=["Authentication"])
@router.get("/customers/me", response_model=CustomerOut, tags=["BankSim"])
def me(customer: Actor, service: Banking):
    service.audit("read_customer", "customers", customer.id)
    return customer


@router.get("/accounts", response_model=list[AccountOut], tags=["BankSim"])
def accounts(service: Banking):
    return service.accounts()


@router.get("/accounts/{account_id}", response_model=AccountOut, tags=["BankSim"])
def account(account_id: UUID, service: Banking):
    return service.account(account_id)


@router.get("/accounts/{account_id}/balance", response_model=BalanceOut, tags=["BankSim"])
def balance(account_id: UUID, service: Banking):
    obj = service.account(account_id)
    return BalanceOut(account_id=obj.id, balance=obj.balance, currency=obj.currency)


@router.get("/accounts/{account_id}/transactions", response_model=TransactionPage, tags=["BankSim"])
def account_transactions(
    account_id: UUID, service: Banking, filters: Annotated[TransactionQuery, Query()]
):
    return service.transactions(filters, account_id)


@router.get("/transactions", response_model=TransactionPage, tags=["BankSim"])
def transactions(service: Banking, filters: Annotated[TransactionQuery, Query()]):
    return service.transactions(filters)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut, tags=["BankSim"])
def transaction(transaction_id: UUID, service: Banking):
    return service.transaction(transaction_id)


@router.get("/cards", response_model=list[CardOut], tags=["BankSim"])
def cards(service: Banking):
    return service.cards()


@router.get("/cards/{card_id}", response_model=CardOut, tags=["BankSim"])
def card(card_id: UUID, service: Banking):
    return service.card(card_id)


@router.post(
    "/cards/{card_id}/block", response_model=PendingOut, status_code=202, tags=["Confirmations"]
)
def block_card(card_id: UUID, service: Banking, data: Input | None = None):
    return service.request_card_block(card_id)


@router.post("/cards/{card_id}/block/confirm", response_model=CardOut, tags=["Confirmations"])
def confirm_block(card_id: UUID, data: CardConfirm, service: Banking):
    return service.confirm_card_block(card_id, data.action_id, data.confirmation)


@router.get("/kyc/status", response_model=KYCOut, tags=["BankSim"])
def kyc(service: Banking):
    return service.kyc()


@router.post("/loans/emi", response_model=EMIOut, tags=["Loans"])
def emi(data: EMIInput, service: Banking):
    service.audit("calculate_emi", "loans")
    return calculate_emi(data)


@router.post("/loans/eligibility", response_model=EligibilityOut, tags=["Loans"])
def eligibility(data: LoanInput, service: Banking):
    return service.eligibility(data)


@router.post("/loans/applications", response_model=PendingOut, status_code=202, tags=["Loans"])
def apply_loan(data: LoanInput, service: Banking):
    return service.request_loan(data)


@router.post(
    "/loans/applications/{action_id}/confirm",
    response_model=LoanOut,
    status_code=201,
    tags=["Confirmations"],
)
def confirm_loan(action_id: UUID, data: Confirm, service: Banking):
    return service.confirm_loan(action_id, data.confirmation)


@router.get("/loans", response_model=list[LoanOut], tags=["Loans"])
def loans(service: Banking):
    return service.loans()


@router.post("/support/tickets", response_model=TicketOut, status_code=201, tags=["Support"])
def create_ticket(data: TicketInput, service: Banking):
    return service.create_ticket(data)


@router.get("/support/tickets", response_model=list[TicketOut], tags=["Support"])
def tickets(service: Banking):
    return service.tickets()


@router.get("/support/tickets/{ticket_id}", response_model=TicketOut, tags=["Support"])
def ticket(ticket_id: UUID, service: Banking):
    return service.ticket(ticket_id)
