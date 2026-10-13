"""Request / response shapes (Pydantic). This is the 'contract' any website follows."""
from datetime import datetime
from typing import Literal, Optional, List
import base64

from pydantic import BaseModel, Field, field_validator, model_validator


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


# ------------------------------------------------- Agent 5: Product onboarding & SEO
MAX_IMAGE_BYTES = 4 * 1024 * 1024


class OnboardIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, examples=["Kisan Cooking Oil 5 Liter"])
    image_base64: str = Field(..., description="The product photo, base64 encoded (max 4 MB)")
    mime_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    categories: List[str] = Field(default_factory=list, max_length=200,
                                  description="Your existing category names; the agent picks one")

    @field_validator("categories")
    @classmethod
    def clean_categories(cls, v: List[str]) -> List[str]:
        return [c.strip()[:100] for c in v if c.strip()]

    @model_validator(mode="after")
    def check_image(self):
        try:
            raw = base64.b64decode(self.image_base64, validate=True)
        except Exception:
            raise ValueError("image_base64 is not valid base64")
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image must be between 1 byte and 4 MB")
        looks_like = {
            "image/jpeg": raw.startswith(b"\xff\xd8"),
            "image/png": raw.startswith(b"\x89PNG"),
            "image/webp": raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
        }
        if not looks_like[self.mime_type]:
            raise ValueError("the file content does not match mime_type")
        return self


class OnboardOut(BaseModel):
    status: Literal["approved", "needs_review"]
    mode: str
    attempts: int
    title: str
    short_description: str
    description: str
    seo_title: str
    meta_description: str
    tags: List[str]
    category: str
    focus_keyword: str
    issues: List[str]
    details: dict
    steps: List[str]


# ---------------------------------------------- Agent 3: Competitor pricing auditor
class PriceAuditIn(BaseModel):
    product_id: str = Field("", max_length=64, description="Your product/variation id (optional)")
    name: str = Field(..., min_length=2, max_length=200, examples=["Kisan Cooking Oil 5 Liter"])
    our_price: float = Field(..., gt=0, examples=[2875])
    min_price: Optional[float] = Field(None, ge=0, description="Never suggest a price below this")
    exclude_domains: List[str] = Field(default_factory=list, max_length=10,
                                       description="Your own website, so it is not counted as a competitor")

    @field_validator("exclude_domains")
    @classmethod
    def clean_domains(cls, v: List[str]) -> List[str]:
        return [d.strip().lower().replace("https://", "").replace("http://", "").strip("/")[:100] for d in v if d.strip()]


class Offer(BaseModel):
    store: str
    price: float
    url: str
    pack_size: str = ""
    evidence: str = ""


class PriceAuditOut(BaseModel):
    audit_id: int
    product_id: str = ""
    name: str
    our_price: float
    suggestion: Literal["lower", "raise", "keep", "no_data"]
    suggested_price: Optional[float]
    confidence: Literal["high", "medium", "low"]
    summary: str
    market: dict
    offers: List[Offer]
    iterations: int
    method: str
    status: str
    steps: List[str]


class AuditStatusIn(BaseModel):
    status: Literal["applied", "dismissed"]