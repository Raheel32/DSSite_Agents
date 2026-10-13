"""HTTP endpoints for Agent 3 (competitor price audits)."""
import json
from datetime import timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents.pricing_agent import run_pricing_audit
from ..database import get_db
from ..models import PriceAudit, utcnow
from ..schemas import AuditStatusIn, PriceAuditIn, PriceAuditOut
from ..security import require_admin

router = APIRouter(tags=["Agent 3 - Competitor Pricing"])
REUSE_MINUTES = 10      # clicking Audit twice in a row does not spend search credits twice


def _out(row: PriceAudit) -> PriceAuditOut:
    return PriceAuditOut(
        audit_id=row.id, product_id=row.product_id, name=row.name, our_price=row.our_price, suggestion=row.suggestion,
        suggested_price=row.suggested_price, confidence=row.confidence, summary=row.summary,
        market=json.loads(row.market_json or "{}"), offers=json.loads(row.offers_json or "[]"),
        iterations=row.iterations, method=row.method, status=row.status,
        steps=row.steps.split("\n") if row.steps else [],
    )


@router.post("/pricing/audit", response_model=PriceAuditOut, dependencies=[Depends(require_admin)])
def audit_price(payload: PriceAuditIn, db: Session = Depends(get_db)):
    """Admin starts an audit for one product. Takes up to about a minute."""
    if payload.product_id:
        recent = (
            db.query(PriceAudit)
            .filter(PriceAudit.product_id == payload.product_id, PriceAudit.our_price == payload.our_price,
                    PriceAudit.created_at >= utcnow() - timedelta(minutes=REUSE_MINUTES))
            .order_by(PriceAudit.created_at.desc()).first()
        )
        if recent:
            out = _out(recent)
            out.steps = [f"Reused the audit from the last {REUSE_MINUTES} minutes (no new web search)"] + out.steps
            return out

    state = run_pricing_audit({
        "name": payload.name, "our_price": payload.our_price, "min_price": payload.min_price,
        "exclude_domains": payload.exclude_domains,
    })
    rec = state["recommendation"]
    row = PriceAudit(
        product_id=payload.product_id, name=payload.name, our_price=payload.our_price,
        suggestion=rec["suggestion"], suggested_price=rec["suggested_price"], confidence=rec["confidence"],
        summary=rec["summary"], offers_json=json.dumps(state.get("valid_offers") or []),
        market_json=json.dumps(rec["market"]), steps="\n".join(state["steps"]),
        iterations=state.get("iteration", 0), method=state.get("method", "regex"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/pricing/audits", response_model=List[PriceAuditOut], dependencies=[Depends(require_admin)])
def list_audits(limit: int = 20, db: Session = Depends(get_db)):
    rows = db.query(PriceAudit).order_by(PriceAudit.created_at.desc()).limit(min(limit, 100)).all()
    return [_out(r) for r in rows]


@router.post("/pricing/audits/{audit_id}/status", response_model=PriceAuditOut, dependencies=[Depends(require_admin)])
def set_status(audit_id: int, payload: AuditStatusIn, db: Session = Depends(get_db)):
    """Record that the admin applied or dismissed the suggestion."""
    row = db.get(PriceAudit, audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    return _out(row)