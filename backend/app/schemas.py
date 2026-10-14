from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    StrictBool,
    field_validator,
    model_validator,
)

Money = Annotated[Decimal, Field(gt=0, le=100000000, max_digits=12, decimal_places=2)]
NonnegativeMoney = Annotated[Decimal, Field(ge=0, le=100000000, max_digits=12, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    simulated: bool = True


class Login(Input):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class Register(Login):
    full_name: str = Field(min_length=2, max_length=120)
    password: SecretStr = Field(min_length=12, max_length=128)


class CustomerOut(Output):
    id: UUID
    full_name: str
    email: str
    is_active: bool


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class AccountOut(Output):
    id: UUID
    account_number: str
    account_type: str
    currency: str
    balance: Decimal
    status: str


class BalanceOut(Output):
    account_id: UUID
    currency: str
    balance: Decimal


class TransactionOut(Output):
    id: UUID
    account_id: UUID
    transaction_type: str
    amount: Decimal
    description: str
    merchant: str | None
    reference_code: str
    status: str
    occurred_at: datetime


class TransactionQuery(Input):
    account_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=100)
    cursor: int = Field(default=0, ge=0, le=100000)
    transaction_type: Literal["credit", "debit"] | None = None
    status: Literal["completed", "pending", "failed"] | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_amount: NonnegativeMoney | None = None
    max_amount: NonnegativeMoney | None = None

    @model_validator(mode="after")
    def ranges(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Invalid date range")
        if (
            self.min_amount is not None
            and self.max_amount is not None
            and self.min_amount > self.max_amount
        ):
            raise ValueError("Invalid amount range")
        return self


class TransactionPage(Output):
    items: list[TransactionOut]
    next_cursor: int | None


class CardOut(Output):
    id: UUID
    account_id: UUID | None
    masked_card_number: str
    card_type: str
    status: str
    expiry_month: int
    expiry_year: int


class KYCOut(Output):
    status: str
    notes: str | None
    last_updated: datetime


class EMIInput(Input):
    principal: Money
    annual_interest_rate: Decimal = Field(ge=0, le=100, decimal_places=4)
    tenure_months: int = Field(ge=1, le=600, strict=True)


class EMIOut(Output):
    monthly_payment: Decimal
    total_payment: Decimal
    total_interest: Decimal


class LoanInput(Input):
    loan_type: Literal["personal", "education", "home"]
    requested_amount: Money
    annual_interest_rate: Decimal = Field(ge=0, le=100, decimal_places=4)
    tenure_months: int = Field(ge=1, le=600, strict=True)
    monthly_income: Money
    monthly_obligations: NonnegativeMoney = Decimal(0)


class EligibilityOut(Output):
    eligible: bool
    reasons: list[str]
    monthly_payment: Decimal
    rule: str = "Demo rule: verified KYC, EMI <= 40% of income after obligations, principal <= 24x monthly income."


class LoanOut(Output):
    id: UUID
    loan_type: str
    requested_amount: Decimal
    annual_interest_rate: Decimal
    tenure_months: int
    status: str
    created_at: datetime


class PendingOut(Output):
    id: UUID
    kind: str
    resource_id: UUID | None
    payload: dict
    status: str
    expires_at: datetime
    result_id: UUID | None
    confirmation_required: bool = True


class Confirm(Input):
    confirmation: StrictBool

    @field_validator("confirmation")
    @classmethod
    def must_confirm(cls, value):
        if not value:
            raise ValueError("Explicit confirmation is required")
        return value


class CardConfirm(Confirm):
    action_id: UUID


class TicketInput(Input):
    category: Literal["account", "card", "loan", "dispute", "other"]
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=5, max_length=2000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class TicketOut(Output):
    id: UUID
    category: str
    subject: str
    description: str
    priority: str
    status: str
    created_at: datetime
    updated_at: datetime
