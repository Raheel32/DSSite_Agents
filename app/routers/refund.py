"""HTTP endpoints for Agent 1 (Refund & Escalation)."""
import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..agents import refund_agent
from ..database import get_db
from ..models import Order, RefundRequest, utcnow
from ..schemas import ApproveIn, RefundIn, RefundOut, RefundRecord
from ..security import require_admin, require_site

router = APIRouter(tags=["Agent 1 - Refund & Escalation"])

OPEN_STATUSES = ("pending_approval", "approved", "auto_approved")


def _order_from_request(payload: RefundIn, db: Session) -> Optional[dict]:
    """Use the order facts the website sent; otherwise look in our sample database."""
    if payload.order:
        data = payload.order.model_dump()
        data["customer_email"] = payload.customer_email
        return data
    row = db.query(Order).filter(Order.order_ref == payload.order_ref).first()
    if not row:
        return None
    stamp = row.created_at.isoformat()
    return {
        "amount": row.amount,
        "payment_method": row.payment_method,
        "status": row.status,
        "order_date": stamp,
        "delivered_at": stamp if row.status in refund_agent.DELIVERED_STATUSES else None,
        "customer_email": row.customer_email,
    }


def _out(row: RefundRequest) -> RefundOut:
    return RefundOut(
        request_id=row.id, order_ref=row.order_ref, intent=row.intent, status=row.status,
        reason=row.reason, needs_admin=row.status == "pending_approval",
        steps=row.steps.split("\n") if row.steps else [],
    )


@router.post("/refund/request", response_model=RefundOut, dependencies=[Depends(require_site)])
def request_refund(payload: RefundIn, db: Session = Depends(get_db)):
    """Your website calls this when a customer asks for a refund or cancellation."""
    existing = (
        db.query(RefundRequest)
        .filter(RefundRequest.order_ref == payload.order_ref, RefundRequest.status.in_(OPEN_STATUSES))
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A request for this order already exists (id {existing.id}, status {existing.status}).",
        )

    order = _order_from_request(payload, db)
    row = RefundRequest(
        order_ref=payload.order_ref, customer_email=payload.customer_email,
        message=payload.message, refund_amount=payload.refund_amount or (order or {}).get("amount", 0),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    request_dict = {
        "order_ref": payload.order_ref, "customer_email": payload.customer_email,
        "message": payload.message, "refund_amount": payload.refund_amount,
    }
    values, paused = refund_agent.start_refund(request_dict, order, thread_id=f"refund-{row.id}")

    row.intent = values.get("intent", "")
    row.steps = "\n".join(values.get("steps", []))
    if paused:
        row.status = "pending_approval"
        row.reason = values.get("route_reason", "")
        row.state_json = json.dumps(values)
    else:
        row.status = values["status"]
        row.reason = values["reason"]
        row.decided_at = utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)


@router.get("/refund/{request_id}/status", dependencies=[Depends(require_site)])
def refund_status(request_id: int, db: Session = Depends(get_db)):
    """Lets the website show the customer where their request stands (no personal data)."""
    row = db.get(RefundRequest, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"request_id": row.id, "status": row.status, "reason": row.reason}


@router.get("/refund/requests", response_model=List[RefundRecord], dependencies=[Depends(require_admin)])
def list_requests(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    """Admin dashboard: list requests (e.g. ?status=pending_approval)."""
    query = db.query(RefundRequest)
    if status:
        query = query.filter(RefundRequest.status == status)
    return query.order_by(RefundRequest.created_at.desc()).limit(limit).all()


@router.post("/approve-refund", response_model=RefundOut, dependencies=[Depends(require_admin)])
def approve_refund(payload: ApproveIn, db: Session = Depends(get_db)):
    """Admin clicks Approve / Reject -> the paused graph resumes and finishes."""
    row = db.get(RefundRequest, payload.request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Request not found")
    if row.status != "pending_approval":
        raise HTTPException(status_code=409, detail=f"Request is already {row.status}.")

    saved = json.loads(row.state_json)
    values = refund_agent.resume_refund(f"refund-{row.id}", saved, payload.decision, payload.note)

    row.status = values["status"]
    row.reason = values["reason"]
    row.steps = "\n".join(values.get("steps", []))
    row.admin_note = payload.note
    row.decided_at = utcnow()
    db.commit()
    db.refresh(row)
    return _out(row)
