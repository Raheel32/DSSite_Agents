"""HTTP endpoints for Agent 4."""
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents.fraud_agent import run_fraud_check
from ..database import get_db
from ..models import FraudCheck, utcnow
from ..schemas import FraudRequest, FraudResult

router = APIRouter(prefix="/fraud", tags=["Agent 4 - Fraud Detection"])


@router.post("/check", response_model=FraudResult)
def check_order(payload: FraudRequest, db: Session = Depends(get_db)):
    """Any website calls this at checkout and gets back Safe / Flagged."""
    # 1) Look up history from OUR database (the agent itself stays DB-free)
    flagged_from_ip = (
        db.query(FraudCheck)
        .filter(FraudCheck.ip_address == payload.ip_address, FraudCheck.verdict == "Flagged")
        .count()
    )
    since = utcnow() - timedelta(minutes=10)
    orders_last_10min = (
        db.query(FraudCheck)
        .filter(FraudCheck.customer_email == payload.customer_email, FraudCheck.created_at >= since)
        .count()
    )
    history = {"flagged_from_ip": flagged_from_ip, "orders_last_10min": orders_last_10min}

    # 2) Run the LangGraph pipeline
    state = run_fraud_check(payload.model_dump(), history)

    # 3) Save the verdict
    record = FraudCheck(
        order_ref=payload.order_ref,
        customer_email=payload.customer_email,
        ip_address=payload.ip_address,
        amount=payload.amount,
        payment_method=payload.payment_method,
        fraud_score=state["fraud_score"],
        verdict=state["verdict"],
        reasons=" | ".join(state["reasons"]),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return FraudResult(
        check_id=record.id,
        order_ref=record.order_ref,
        fraud_score=record.fraud_score,
        verdict=record.verdict,
        reasons=state["reasons"],
    )


@router.get("/flagged", response_model=List[FraudResult])
def list_flagged(db: Session = Depends(get_db)):
    """Admin dashboard uses this to review flagged orders."""
    rows = (
        db.query(FraudCheck)
        .filter(FraudCheck.verdict == "Flagged")
        .order_by(FraudCheck.created_at.desc())
        .all()
    )
    return [
        FraudResult(
            check_id=r.id, order_ref=r.order_ref, fraud_score=r.fraud_score,
            verdict=r.verdict, reasons=r.reasons.split(" | ") if r.reasons else [],
        )
        for r in rows
    ]
