"""Request / response shapes (Pydantic). This is the 'contract' any website follows."""
from datetime import datetime
from typing import Literal, Optional, List
from pydantic import BaseModel, Field, field_validator


class FraudRequest(BaseModel):
    order_ref: str = Field(..., examples=["ORD-1001"])
    customer_email: str = Field(..., examples=["ali@example.com"])
    amount: float = Field(..., gt=0, examples=[4500])
    payment_method: Literal["bank_transfer", "cod"]
    ip_address: str = Field(..., examples=["103.255.4.10"])
    # Optional extras the site CAN send (more data = better checks)
    shipping_country: Optional[str] = Field(None, examples=["PK"])
    ip_country: Optional[str] = Field(None, examples=["PK"])
    checkout_seconds: Optional[int] = Field(
        None, description="Seconds between opening checkout and placing the order"
    )


class FraudResult(BaseModel):
    check_id: int
    order_ref: str
    fraud_score: int
    verdict: Literal["Safe", "Flagged"]
    reasons: List[str]


# ------------------------------------------------------------ Agent 1: Refund
class OrderInfo(BaseModel):
    """Order facts the website sends (so the agent works with ANY shop)."""
    amount: float = Field(..., gt=0, examples=[3500])
    payment_method: Literal["bank_transfer", "cod"]
    status: str = Field(..., examples=["completed"], description="e.g. processing, completed, cancelled")
    order_date: Optional[str] = Field(None, examples=["2026-10-09T10:16:00+05:00"])
    delivered_at: Optional[str] = Field(None, description="When it was delivered/completed (ISO date)")


class RefundIn(BaseModel):
    order_ref: str = Field(..., examples=["8669"])
    customer_email: str = Field(..., examples=["abc@gmail.com"])
    message: str = Field(..., min_length=3, max_length=1000,
                         examples=["The ghee carton arrived damaged, I want my money back"])
    refund_amount: Optional[float] = Field(None, gt=0, description="Leave empty for a full refund")
    order: Optional[OrderInfo] = Field(
        None, description="If omitted, the agent looks the order up in its own sample database"
    )


class RefundOut(BaseModel):
    request_id: int
    order_ref: str
    intent: str
    status: str
    reason: str
    needs_admin: bool
    steps: List[str]


class ApproveIn(BaseModel):
    request_id: int
    decision: Literal["approve", "reject"]
    note: str = Field("", max_length=500)


class RefundRecord(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    order_ref: str
    customer_email: str
    message: str
    intent: str
    refund_amount: float
    status: str
    reason: str
    admin_note: str
    created_at: datetime
    decided_at: Optional[datetime] = None


# ----------------------------------------------------- Agent 2: Product discovery
class CatalogProductIn(BaseModel):
    external_id: str = Field(..., max_length=64, examples=["1234"])
    name: str = Field(..., max_length=200)
    price: float = Field(..., ge=0)
    category: str = Field("", max_length=300)
    description: str = Field("", max_length=1000)
    url: str = Field("", max_length=500)
    image_url: str = Field("", max_length=500)
    in_stock: bool = True

    @field_validator("url", "image_url")
    @classmethod
    def only_web_links(cls, v: str) -> str:
        # these get shown as links/images on the website, so only allow http(s)
        return v if v.lower().startswith(("http://", "https://")) else ""


class CatalogSyncIn(BaseModel):
    products: List[CatalogProductIn] = Field(..., max_length=200)


class RecommendIn(BaseModel):
    query: str = Field(..., min_length=2, max_length=300, examples=["winter jacket and shoes under 5000"])
    customer_email: Optional[str] = None
    purchased_product_ids: List[str] = Field(default_factory=list, max_length=100)
    limit: int = Field(10, ge=1, le=30)


class ProductHit(BaseModel):
    id: str
    name: str
    price: float
    category: str
    url: str
    image_url: str
    score: float
    matched: List[str]


class RecommendOut(BaseModel):
    query: str
    interpretation: dict
    results: List[ProductHit]
    steps: List[str]
