"""Self-test for Agent 1:  python test_refund.py"""
import os
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import app          # importing the app loads your .env file...
from app.agents import refund_agent

# ...so remove the keys AFTER the import: these tests must run on the keyword fallback, not real Gemini
for key in ("GOOGLE_API_KEY", "SITE_API_KEY", "ADMIN_API_KEY"):
    os.environ.pop(key, None)


def ago(**kw):
    return (datetime.now(timezone.utc) - timedelta(**kw)).isoformat()


def order(amount, status="completed", method="cod", **delivered_ago):
    when = ago(**delivered_ago) if delivered_ago else ago(hours=1)
    return {"amount": amount, "payment_method": method, "status": status,
            "order_date": when, "delivered_at": when if status == "completed" else None}


def req(ref, msg, ord_):
    return {"order_ref": ref, "customer_email": "abc@gmail.com", "message": msg, "order": ord_}


with TestClient(app) as c:
    # 1. small + fresh -> auto approved
    r = c.post("/refund/request", json=req("T1", "The oil bottle arrived damaged, I want a refund", order(3000, hours=2))).json()
    print("1", r["status"], "|", r["reason"]); assert r["status"] == "auto_approved" and r["intent"] == "refund"

    # 2. big + fresh -> pending, admin approves
    r = c.post("/refund/request", json=req("T2", "Wrong item, money back please", order(8000, hours=2))).json()
    print("2", r["status"], "|", r["reason"]); assert r["status"] == "pending_approval"
    a = c.post("/approve-refund", json={"request_id": r["request_id"], "decision": "approve", "note": "ok"}).json()
    print("  after admin:", a["status"]); assert a["status"] == "approved"

    # 3. 3 days old -> pending, admin rejects
    r = c.post("/refund/request", json=req("T3", "refund please", order(2000, days=3))).json()
    print("3", r["status"]); assert r["status"] == "pending_approval"
    a = c.post("/approve-refund", json={"request_id": r["request_id"], "decision": "reject", "note": "used"}).json()
    print("  after admin:", a["status"]); assert a["status"] == "rejected"

    # 4. 10 days old -> auto rejected
    r = c.post("/refund/request", json=req("T4", "I want a refund", order(2000, days=10))).json()
    print("4", r["status"], "|", r["reason"]); assert r["status"] == "auto_rejected"

    # 5. not delivered yet, COD cancel -> auto approved
    o = order(4000, status="processing"); 
    r = c.post("/refund/request", json=req("T5", "Please cancel my order", o)).json()
    print("5", r["status"], r["intent"]); assert r["status"] == "auto_approved" and r["intent"] == "cancel"

    # 6. message we cannot understand -> pending
    r = c.post("/refund/request", json=req("T6", "hello what is your phone number", order(1000, hours=1))).json()
    print("6", r["status"], r["intent"]); assert r["status"] == "pending_approval" and r["intent"] == "other"
    pending_id = r["request_id"]

    # 7. duplicate request for the same order -> 409
    r = c.post("/refund/request", json=req("T1", "refund again", order(3000, hours=2)))
    print("7", r.status_code); assert r.status_code == 409

    # 8. service "restarts" (memory wiped) -> admin can still decide
    refund_agent.refund_graph = refund_agent.build_refund_graph()
    a = c.post("/approve-refund", json={"request_id": pending_id, "decision": "approve", "note": "after restart"}).json()
    print("8", a["status"]); assert a["status"] == "approved"

    # 9. already decided -> 409
    r = c.post("/approve-refund", json={"request_id": pending_id, "decision": "reject"})
    print("9", r.status_code); assert r.status_code == 409

    # 10. sample database lookup (seeded order ORD-0001, COD Rs 4,200, just created)
    r = c.post("/refund/request", json={"order_ref": "ORD-0001", "customer_email": "ali@example.com",
                                        "message": "item missing from my order"}).json()
    print("10", r["status"], "|", r["reason"]); assert r["status"] == "auto_approved"

    # 11. wrong email on a sample order -> rejected
    r = c.post("/refund/request", json={"order_ref": "ORD-0002", "customer_email": "hacker@x.com",
                                        "message": "refund please"}).json()
    print("11", r["status"]); assert r["status"] == "auto_rejected"

    # 12. API keys
    os.environ["ADMIN_API_KEY"] = "secret-admin"
    os.environ["SITE_API_KEY"] = "secret-site"
    assert c.get("/refund/requests").status_code == 401
    assert c.get("/refund/requests", headers={"X-Admin-Key": "secret-admin"}).status_code == 200
    assert c.post("/refund/request", json=req("T12", "refund", order(100, hours=1))).status_code == 401
    ok = c.post("/refund/request", json=req("T12", "refund", order(100, hours=1)), headers={"X-Site-Key": "secret-site"})
    print("12 keys ok", ok.status_code); assert ok.status_code == 200

    assert c.get("/admin").status_code == 200
    print("ALL AGENT 1 TESTS PASSED")