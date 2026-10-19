"""Persistent BankSim records. All application data is synthetic."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedMixin, IdentityMixin


class PendingAction(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "pending_actions"
    __table_args__ = (
        CheckConstraint("kind IN ('block_card', 'loan_application')", name="kind"),
        CheckConstraint("status IN ('pending', 'executed', 'cancelled')", name="status"),
        CheckConstraint("expires_at > created_at", name="expiry"),
        Index("ix_pending_actions_owner_state", "customer_id", "status"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"))
    kind: Mapped[str] = mapped_column(String(30))
    resource_id: Mapped[UUID | None] = mapped_column(ForeignKey("cards.id"))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(12), server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_id: Mapped[UUID | None]


class Customer(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    accounts: Mapped[list["Account"]] = relationship(back_populates="customer")
    cards: Mapped[list["Card"]] = relationship(back_populates="customer")
    kyc: Mapped["KYCRecord | None"] = relationship(back_populates="customer")
    loans: Mapped[list["Loan"]] = relationship(back_populates="customer")
    tickets: Mapped[list["SupportTicket"]] = relationship(back_populates="customer")


class Account(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("id", "customer_id", name="uq_accounts_id_customer"),
        CheckConstraint("account_type IN ('savings', 'current')", name="type"),
        CheckConstraint("status IN ('active', 'frozen', 'closed')", name="status"),
        CheckConstraint("balance >= 0 AND balance <> 'NaN'::numeric", name="balance"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    account_number: Mapped[str] = mapped_column(String(40), unique=True)
    account_type: Mapped[str] = mapped_column(String(12))
    currency: Mapped[str] = mapped_column(String(3), server_default="INR")
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), server_default="0")
    status: Mapped[str] = mapped_column(String(12), server_default="active")
    customer: Mapped[Customer] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class Transaction(IdentityMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("transaction_type IN ('credit', 'debit')", name="type"),
        CheckConstraint("amount > 0 AND amount <> 'NaN'::numeric", name="amount"),
        CheckConstraint("status IN ('completed', 'pending', 'failed')", name="status"),
        Index("ix_transactions_account_occurred", "account_id", "occurred_at", "id"),
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"))
    transaction_type: Mapped[str] = mapped_column(String(10))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    description: Mapped[str] = mapped_column(String(255))
    merchant: Mapped[str | None] = mapped_column(String(120))
    reference_code: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(12), server_default="completed")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    account: Mapped[Account] = relationship(back_populates="transactions")


class Card(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "cards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "customer_id"],
            ["accounts.id", "accounts.customer_id"],
            name="fk_cards_account_owner",
        ),
        CheckConstraint("card_type IN ('debit', 'credit')", name="type"),
        CheckConstraint("status IN ('active', 'blocked', 'expired')", name="status"),
        CheckConstraint("expiry_month BETWEEN 1 AND 12", name="expiry_month"),
        CheckConstraint("expiry_year BETWEEN 2000 AND 2200", name="expiry_year"),
        CheckConstraint("masked_card_number ~ '^DEMO-XXXX-[0-9]{4}$'", name="masked_number"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    account_id: Mapped[UUID | None] = mapped_column(index=True)
    masked_card_number: Mapped[str] = mapped_column(String(32), unique=True)
    card_type: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), server_default="active")
    expiry_month: Mapped[int] = mapped_column(Integer)
    expiry_year: Mapped[int] = mapped_column(Integer)
    customer: Mapped[Customer] = relationship(back_populates="cards")
    account: Mapped[Account | None] = relationship(viewonly=True)


class KYCRecord(IdentityMixin, Base):
    __tablename__ = "kyc_records"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'verified', 'rejected')", name="status"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), unique=True)
    status: Mapped[str] = mapped_column(String(12))
    notes: Mapped[str | None] = mapped_column(Text)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    customer: Mapped[Customer] = relationship(back_populates="kyc")


class Loan(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "loans"
    __table_args__ = (
        CheckConstraint("loan_type IN ('personal', 'education', 'home')", name="type"),
        CheckConstraint(
            "requested_amount > 0 AND requested_amount <> 'NaN'::numeric", name="amount"
        ),
        CheckConstraint("annual_interest_rate BETWEEN 0 AND 100", name="rate"),
        CheckConstraint("tenure_months BETWEEN 1 AND 600", name="tenure"),
        CheckConstraint(
            "status IN ('draft', 'submitted', 'approved_demo', 'rejected_demo')",
            name="status",
        ),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    loan_type: Mapped[str] = mapped_column(String(12))
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    annual_interest_rate: Mapped[Decimal] = mapped_column(Numeric(7, 4))
    tenure_months: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), server_default="draft")
    customer: Mapped[Customer] = relationship(back_populates="loans")


class SupportTicket(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "support_tickets"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'in_progress', 'resolved')", name="status"),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="priority"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    category: Mapped[str] = mapped_column(String(40))
    subject: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="open")
    priority: Mapped[str] = mapped_column(String(10), server_default="normal")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    customer: Mapped[Customer] = relationship(back_populates="tickets")


class AuditLog(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "audit_logs"
    customer_id: Mapped[UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[UUID | None]
    outcome: Mapped[str] = mapped_column(String(30))
    request_id: Mapped[str] = mapped_column(String(64), index=True)


class PolicyDocument(IdentityMixin, Base):
    __tablename__ = "policy_documents"
    __table_args__ = (UniqueConstraint("source", "checksum", name="uq_policy_source_checksum"),)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    chunks: Mapped[list["PolicyChunk"]] = relationship(back_populates="document")


class PolicyChunk(IdentityMixin, Base):
    __tablename__ = "policy_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_policy_chunk_position"),
        CheckConstraint("chunk_index >= 0", name="position"),
        CheckConstraint("page IS NULL OR page > 0", name="page"),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL)",
            name="embedding_model",
        ),
    )
    document_id: Mapped[UUID] = mapped_column(ForeignKey("policy_documents.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(200))
    page: Mapped[int | None] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector())
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    document: Mapped[PolicyDocument] = relationship(back_populates="chunks")


class Conversation(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "conversations"
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    title: Mapped[str] = mapped_column(String(80))


class ChatTurn(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("conversation_id", "message_id", name="uq_chat_turn_message"),
        UniqueConstraint("conversation_id", "position", name="uq_chat_turn_position"),
        CheckConstraint("position BETWEEN 1 AND 100", name="position"),
    )
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[UUID]
    position: Mapped[int] = mapped_column(Integer)
    user_text: Mapped[str] = mapped_column(Text)
    response: Mapped[dict] = mapped_column(JSONB)


class AgentRun(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'completed', 'failed', 'cancelled')", name="status"),
        CheckConstraint("revision >= 0 AND model_calls >= 0 AND tool_calls >= 0", name="counters"),
    )
    customer_id: Mapped[UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(12), default="running")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    model_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    usage_complete: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentArtifact(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "agent_artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "revision", name="uq_agent_artifact_revision"),
        UniqueConstraint("run_id", "role", name="uq_agent_artifact_role"),
    )
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB)


class AgentEvent(IdentityMixin, CreatedMixin, Base):
    __tablename__ = "agent_events"
    sequence: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
