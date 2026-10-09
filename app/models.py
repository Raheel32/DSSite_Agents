"""Database tables.

Product / Order  -> small SAMPLE dataset used for testing (later agents use it).
FraudCheck       -> every fraud verdict is saved here (Agent 4 output + history).
"""
from datetime import datetime, timezone
from sqlalchemy import String, Float, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(50))
    price: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(50), unique=True)
    customer_email: Mapped[str] = mapped_column(String(120))
    amount: Mapped[float] = mapped_column(Float)
    payment_method: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FraudCheck(Base):
    __tablename__ = "fraud_checks"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(50), index=True)
    customer_email: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[float] = mapped_column(Float)
    payment_method: Mapped[str] = mapped_column(String(20))
    fraud_score: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(10))  # "Safe" or "Flagged"
    reasons: Mapped[str] = mapped_column(Text, default="")  # joined with " | "
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class RefundRequest(Base):
    """One row per refund/cancel request handled by Agent 1."""
    __tablename__ = "refund_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_ref: Mapped[str] = mapped_column(String(50), index=True)
    customer_email: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text, default="")
    intent: Mapped[str] = mapped_column(String(20), default="")
    refund_amount: Mapped[float] = mapped_column(Float, default=0)
    # auto_approved | auto_rejected | pending_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="processing", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    steps: Mapped[str] = mapped_column(Text, default="")          # agent trace, one step per line
    state_json: Mapped[str] = mapped_column(Text, default="")     # saved graph state (for resume)
    admin_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
