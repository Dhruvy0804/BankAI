from datetime import UTC, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal, localcontext
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import APIError
from app.models import (
    Account,
    AuditLog,
    Card,
    Customer,
    KYCRecord,
    Loan,
    PendingAction,
    SupportTicket,
    Transaction,
)
from app.schemas import EligibilityOut, EMIInput, EMIOut, LoanInput, TransactionQuery


def calculate_emi(data: EMIInput) -> EMIOut:
    with localcontext() as context:
        context.prec = 40
        rate = data.annual_interest_rate / Decimal(1200)
        if rate == 0:
            payment = data.principal / data.tenure_months
        else:
            growth = (1 + rate) ** data.tenure_months
            payment = data.principal * rate * growth / (growth - 1)
        total = payment * data.tenure_months
        rounded = lambda value: value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return EMIOut(
            monthly_payment=rounded(payment),
            total_payment=rounded(total),
            total_interest=rounded(total - data.principal),
        )


class BankingService:
    def __init__(self, session: Session, customer_id: UUID, request_id: str, settings: Settings):
        self.db = session
        self.customer_id = customer_id
        self.request_id = request_id
        self.settings = settings

    def audit(self, action: str, resource_type: str, resource_id: UUID | None = None):
        self.db.add(
            AuditLog(
                customer_id=self.customer_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                outcome="success",
                request_id=self.request_id,
            )
        )

    def fail(self, status, code, message, resource_type="request", resource_id=None):
        raise APIError(
            status,
            code,
            message,
            actor=self.customer_id,
            action="operation_denied",
            resource_type=resource_type,
            resource_id=resource_id,
        )

    def owned(self, model, identifier: UUID, *, lock=False):
        query = select(model).where(model.id == identifier, model.customer_id == self.customer_id)
        if lock:
            query = query.with_for_update()
        obj = self.db.scalar(query.execution_options(populate_existing=True))
        if obj is None:
            self.fail(404, "NOT_FOUND", "Resource not found.", model.__tablename__, identifier)
        return obj

    def accounts(self):
        self.audit("list_accounts", "accounts")
        return list(
            self.db.scalars(
                select(Account)
                .where(Account.customer_id == self.customer_id)
                .order_by(Account.created_at, Account.id)
            )
        )

    def account(self, identifier):
        obj = self.owned(Account, identifier)
        self.audit("read_account", "accounts", identifier)
        return obj

    def transaction(self, identifier):
        obj = self.db.scalar(
            select(Transaction)
            .join(Account)
            .where(Transaction.id == identifier, Account.customer_id == self.customer_id)
        )
        if obj is None:
            self.fail(404, "NOT_FOUND", "Resource not found.", "transactions", identifier)
        self.audit("read_transaction", "transactions", identifier)
        return obj

    def transactions(self, filters: TransactionQuery, account_id=None):
        if account_id and filters.account_id and account_id != filters.account_id:
            self.fail(422, "INVALID_INPUT", "Conflicting account filters.")
        account_id = account_id or filters.account_id
        if account_id:
            self.owned(Account, account_id)
        query = select(Transaction).join(Account).where(Account.customer_id == self.customer_id)
        if account_id:
            query = query.where(Transaction.account_id == account_id)
        if filters.transaction_type:
            query = query.where(Transaction.transaction_type == filters.transaction_type)
        if filters.status:
            query = query.where(Transaction.status == filters.status)
        if filters.date_from:
            query = query.where(
                Transaction.occurred_at >= datetime.combine(filters.date_from, time.min, UTC)
            )
        if filters.date_to:
            query = query.where(
                Transaction.occurred_at <= datetime.combine(filters.date_to, time.max, UTC)
            )
        if filters.min_amount is not None:
            query = query.where(Transaction.amount >= filters.min_amount)
        if filters.max_amount is not None:
            query = query.where(Transaction.amount <= filters.max_amount)
        rows = list(
            self.db.scalars(
                query.order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
                .offset(filters.cursor)
                .limit(filters.limit + 1)
            )
        )
        self.audit("list_transactions", "accounts", account_id)
        return {
            "items": rows[: filters.limit],
            "next_cursor": filters.cursor + filters.limit if len(rows) > filters.limit else None,
        }

    def cards(self):
        self.audit("list_cards", "cards")
        return list(
            self.db.scalars(
                select(Card).where(Card.customer_id == self.customer_id).order_by(Card.id)
            )
        )

    def card(self, identifier):
        obj = self.owned(Card, identifier)
        self.audit("read_card", "cards", identifier)
        return obj

    def kyc(self):
        obj = self.db.scalar(select(KYCRecord).where(KYCRecord.customer_id == self.customer_id))
        if obj is None:
            self.fail(404, "NOT_FOUND", "Resource not found.", "kyc_records")
        self.audit("read_kyc", "kyc_records", obj.id)
        return obj

    def new_action(self, kind, resource_id=None, payload=None):
        now = datetime.now(UTC)
        action = PendingAction(
            customer_id=self.customer_id,
            kind=kind,
            resource_id=resource_id,
            payload=payload or {},
            status="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=self.settings.confirmation_expire_seconds),
        )
        self.db.add(action)
        self.db.flush()
        self.audit("request_" + kind, "pending_actions", action.id)
        return action

    def request_card_block(self, identifier):
        card = self.owned(Card, identifier)
        if card.status != "active":
            self.fail(
                409,
                "INVALID_STATE",
                "Only an active demo card can be blocked.",
                "cards",
                identifier,
            )
        return self.new_action(
            "block_card", identifier, {"masked_card_number": card.masked_card_number}
        )

    def confirmable(self, identifier, kind, resource_id=None):
        # Lock actor before action for a consistent order and fresh active-state check.
        actor = self.db.scalar(
            select(Customer)
            .where(Customer.id == self.customer_id, Customer.is_active.is_(True))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if actor is None:
            self.fail(401, "UNAUTHENTICATED", "A valid active customer is required.")
        action = self.owned(PendingAction, identifier, lock=True)
        if action.kind != kind or action.resource_id != resource_id:
            self.fail(409, "ACTION_MISMATCH", "Confirmation does not match this operation.")
        if action.status != "pending":
            self.fail(409, "ACTION_USED", "This action is no longer pending.")
        if action.expires_at <= datetime.now(UTC):
            self.fail(409, "ACTION_EXPIRED", "This action expired. Start a new request.")
        return action

    def execute(self, action, result_id):
        action.status = "executed"
        action.executed_at = datetime.now(UTC)
        action.result_id = result_id
        self.audit("confirm_" + action.kind, action.kind, result_id)
        self.db.flush()

    def confirm_card_block(self, identifier, action_id, confirmation=False):
        if confirmation is not True:
            self.fail(400, "CONFIRMATION_REQUIRED", "Explicit confirmation is required.")
        action = self.confirmable(action_id, "block_card", identifier)
        card = self.owned(Card, identifier, lock=True)
        if card.status != "active":
            self.fail(
                409,
                "INVALID_STATE",
                "Card status changed. Start a new request.",
                "cards",
                identifier,
            )
        card.status = "blocked"
        self.execute(action, card.id)
        return card

    def eligibility(self, data: LoanInput):
        result = calculate_emi(
            EMIInput(
                principal=data.requested_amount,
                annual_interest_rate=data.annual_interest_rate,
                tenure_months=data.tenure_months,
            )
        )
        kyc = self.db.scalar(select(KYCRecord).where(KYCRecord.customer_id == self.customer_id))
        reasons = []
        if kyc is None or kyc.status != "verified":
            reasons.append("Verified demo KYC is required.")
        disposable = data.monthly_income - data.monthly_obligations
        if disposable <= 0 or result.monthly_payment > disposable * Decimal("0.4"):
            reasons.append("EMI exceeds 40% of income after obligations.")
        if data.requested_amount > data.monthly_income * 24:
            reasons.append("Principal exceeds 24 times monthly income.")
        self.audit("check_eligibility", "loans")
        return EligibilityOut(
            eligible=not reasons, reasons=reasons, monthly_payment=result.monthly_payment
        )

    def request_loan(self, data):
        if not self.eligibility(data).eligible:
            self.fail(
                422, "DEMO_INELIGIBLE", "Application does not meet the documented demo rules."
            )
        return self.new_action("loan_application", payload=data.model_dump(mode="json"))

    def confirm_loan(self, action_id, confirmation=False):
        if confirmation is not True:
            self.fail(400, "CONFIRMATION_REQUIRED", "Explicit confirmation is required.")
        action = self.confirmable(action_id, "loan_application")
        # Payload is bound server-side; the confirmation body cannot replace it.
        data = LoanInput.model_validate(action.payload)
        self.db.scalar(
            select(KYCRecord).where(KYCRecord.customer_id == self.customer_id).with_for_update()
        )
        if not self.eligibility(data).eligible:
            self.fail(409, "ELIGIBILITY_CHANGED", "Demo eligibility changed. Start a new request.")
        loan = Loan(
            customer_id=self.customer_id,
            loan_type=data.loan_type,
            requested_amount=data.requested_amount,
            annual_interest_rate=data.annual_interest_rate,
            tenure_months=data.tenure_months,
            status="submitted",
        )
        self.db.add(loan)
        self.db.flush()
        self.execute(action, loan.id)
        return loan

    def loans(self):
        self.audit("list_loans", "loans")
        return list(
            self.db.scalars(
                select(Loan)
                .where(Loan.customer_id == self.customer_id)
                .order_by(Loan.created_at.desc(), Loan.id)
            )
        )

    def create_ticket(self, data):
        ticket = SupportTicket(customer_id=self.customer_id, **data.model_dump(), status="open")
        self.db.add(ticket)
        self.db.flush()
        self.audit("create_ticket", "support_tickets", ticket.id)
        return ticket

    def tickets(self):
        self.audit("list_tickets", "support_tickets")
        return list(
            self.db.scalars(
                select(SupportTicket)
                .where(SupportTicket.customer_id == self.customer_id)
                .order_by(SupportTicket.created_at.desc(), SupportTicket.id)
            )
        )

    def ticket(self, identifier):
        ticket = self.owned(SupportTicket, identifier)
        self.audit("read_ticket", "support_tickets", identifier)
        return ticket
