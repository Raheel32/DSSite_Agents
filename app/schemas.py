"""Request / response shapes (Pydantic). This is the 'contract' any website follows."""
from typing import Literal, Optional, List
from pydantic import BaseModel, Field


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
