"""Quick self-test:  python test_fraud.py"""
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    safe = client.post("/fraud/check", json={
        "order_ref": "T-1", "customer_email": "good@example.com", "amount": 3500,
        "payment_method": "bank_transfer", "ip_address": "103.255.4.10",
        "shipping_country": "PK", "ip_country": "PK", "checkout_seconds": 120,
    }).json()
    print("SAFE   ->", safe)

    risky = client.post("/fraud/check", json={
        "order_ref": "T-2", "customer_email": "bot@example.com", "amount": 45000,
        "payment_method": "cod", "ip_address": "10.0.0.5",
        "shipping_country": "PK", "ip_country": "US", "checkout_seconds": 8,
    }).json()
    print("RISKY  ->", risky)

    assert safe["verdict"] == "Safe" and risky["verdict"] == "Flagged"
    print("Flagged list:", len(client.get("/fraud/flagged").json()), "order(s)")
    print("ALL TESTS PASSED")
