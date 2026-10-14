"""Quick self-test:  python test_fraud.py"""
import os

# Tests always use their OWN throw-away database (never your real one, wherever .env points)
os.environ["DATABASE_URL"] = "sqlite:///./test_agents.db"
if os.path.exists("test_agents.db"):
    try:
        os.remove("test_agents.db")
    except OSError:
        pass

from fastapi.testclient import TestClient
from app.main import app          # importing the app loads your .env file...

for key in ("SITE_API_KEY", "ADMIN_API_KEY"):   # ...so clear the keys afterwards: these tests start without keys
    os.environ.pop(key, None)

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

    # keys: the website needs the site key, the admin lists need the admin key
    os.environ["SITE_API_KEY"] = "site-secret"
    os.environ["ADMIN_API_KEY"] = "admin-secret"
    body = {"order_ref": "T-3", "customer_email": "k@example.com", "amount": 100,
            "payment_method": "cod", "ip_address": "103.255.4.10"}
    assert client.post("/fraud/check", json=body).status_code == 401
    assert client.post("/fraud/check", json=body, headers={"X-Site-Key": "wrong"}).status_code == 401
    assert client.post("/fraud/check", json=body, headers={"X-Site-Key": "site-secret"}).status_code == 200
    assert client.get("/fraud/flagged").status_code == 401
    assert client.get("/fraud/history").status_code == 401
    assert client.get("/fraud/flagged", headers={"X-Admin-Key": "admin-secret"}).status_code == 200
    assert client.get("/fraud/history", headers={"X-Admin-Key": "admin-secret"}).status_code == 200
    print("keys enforced on all fraud endpoints")
    print("ALL TESTS PASSED")
