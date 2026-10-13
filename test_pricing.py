"""Self-test for Agent 3:  python test_pricing.py
(Tavily and Gemini are replaced by fakes, so no keys and no internet are needed.)"""
import json
import os

from fastapi.testclient import TestClient
from app.main import app                      # importing the app loads your .env file...
from app.agents import pricing_agent as agent

for key in ("GOOGLE_API_KEY", "SITE_API_KEY", "ADMIN_API_KEY", "TAVILY_API_KEY"):   # ...so clear the keys afterwards
    os.environ.pop(key, None)

NAHEED = {"title": "Kisan Cooking Oil 5 Liter - Naheed", "url": "https://www.naheed.pk/kisan-oil-5l",
          "content": "Kisan Cooking Oil 5 Liter pouch. Price: Rs 2,790. In stock."}
CARREFOUR = {"title": "Kisan Cooking Oil 5L | Carrefour Pakistan", "url": "https://www.carrefour.pk/kisan",
             "content": "Kisan Cooking Oil 5L price PKR 2,850 only"}
DARAZ = {"title": "Kisan Cooking Oil 5 Liter Daraz", "url": "https://www.daraz.pk/kisan-5l",
         "content": "Kisan Cooking Oil 5 Liter Rs 2,900 free delivery"}
ONE_LITER = {"title": "Kisan Cooking Oil 1 Liter", "url": "https://shop.example/kisan-1l",
             "content": "Kisan Cooking Oil 1 Liter pouch Rs 600"}
BLOG = {"title": "Best cooking oils", "url": "https://blog.example/oil", "content": "Which oil is healthy? No prices here."}
OWN = {"title": "Kisan Cooking Oil 5 Liter", "url": "https://testv3.websitedemolynk.com/oil",
       "content": "Kisan Cooking Oil 5 Liter Rs 2,875"}


def fake_search(rounds):
    """Returns the n-th list of results each time the agent searches."""
    calls = []

    def search(query, depth, exclude_domains):
        calls.append((query, depth))
        return rounds[min(len(calls) - 1, len(rounds) - 1)]
    agent.tavily_available = lambda: True
    agent.web_search = search
    return calls


def audit(c, price=3300, **extra):
    body = {"name": "Kisan Cooking Oil 5 Liter", "our_price": price, **extra}
    return c.post("/pricing/audit", json=body)


with TestClient(app) as c:
    agent.llm_available = lambda: False                       # offline price finder first

    # 1. round 1 finds only one store, the loop searches again and finds the second
    calls = fake_search([[NAHEED, BLOG], [CARREFOUR]])
    r = audit(c, 3300, product_id="p1").json()
    print("1", r["suggestion"], r["suggested_price"], r["confidence"], "rounds:", r["iterations"])
    for s in r["steps"]:
        print("   -", s[:140])
    assert r["iterations"] == 2 and len(calls) == 2
    assert r["suggestion"] == "lower" and r["suggested_price"] == 2820 and r["confidence"] == "medium"
    assert {o["store"] for o in r["offers"]} == {"naheed.pk", "carrefour.pk"}

    # 2. clicking again within 10 minutes reuses the audit (no new searches)
    before = len(calls)
    r2 = audit(c, 3300, product_id="p1").json()
    assert len(calls) == before and r2["audit_id"] == r["audit_id"] and "Reused" in r2["steps"][0]
    print("2 reused")

    # 3. 'keep' and 'raise' decisions
    fake_search([[NAHEED, CARREFOUR, DARAZ]])
    r = audit(c, 2850).json();  print("3 keep ", r["suggestion"], r["suggested_price"], r["confidence"])
    assert r["suggestion"] == "keep" and r["iterations"] == 1
    r = audit(c, 2400).json();  print("3 raise", r["suggestion"], r["suggested_price"])
    assert r["suggestion"] == "raise" and r["suggested_price"] == 2760          # capped: 2400 * 1.15
    r = audit(c, 3300, min_price=3000).json();  print("3 floor", r["suggestion"], r["suggested_price"])
    assert r["suggestion"] == "lower" and r["suggested_price"] == 3000          # never below the floor

    # 4. wrong pack size, our own site and pages without prices are not used
    fake_search([[ONE_LITER, OWN, BLOG]] * 3)
    r = audit(c, 3000, exclude_domains=["testv3.websitedemolynk.com"]).json()
    print("4", r["suggestion"], r["iterations"], "|", r["summary"])
    assert r["suggestion"] == "no_data" and r["iterations"] == 3 and r["offers"] == []

    # 5. only one trusted store after all rounds -> low confidence
    fake_search([[NAHEED]] * 3)
    r = audit(c, 3300).json();  print("5", r["suggestion"], r["confidence"], r["iterations"])
    assert r["confidence"] == "low" and r["iterations"] == 3

    # 6. Gemini mode: invented price and wrong pack are rejected by the reviewer
    agent.llm_available = lambda: True
    fake_search([[NAHEED, CARREFOUR, DARAZ, ONE_LITER]])
    agent.call_llm = lambda prompt: json.dumps({"offers": [
        {"result": 0, "store": "Naheed", "price": 2790, "pack_size": "5 liter", "same_product": True, "evidence": "Rs 2,790"},
        {"result": 1, "store": "Carrefour", "price": 2850, "pack_size": "5L", "same_product": True, "evidence": "PKR 2,850"},
        {"result": 2, "store": "Daraz", "price": 2100, "pack_size": "5 liter", "same_product": True, "evidence": "made up"},
        {"result": 3, "store": "Shop", "price": 600, "pack_size": "1 liter", "same_product": True, "evidence": "Rs 600"},
    ]})
    r = audit(c, 3300).json()
    print("6", r["method"], r["suggestion"], r["confidence"], [o["store"] for o in r["offers"]])
    assert r["method"] == "gemini" and [o["store"] for o in r["offers"]] == ["Naheed", "Carrefour"]
    reviewer = [s for s in r["steps"] if s.startswith("Reviewer")][0]
    assert "not in the page text" in reviewer and "too far" in reviewer

    # 7. Gemini breaks -> offline finder takes over
    def boom(prompt): raise RuntimeError("quota")
    agent.call_llm = boom
    fake_search([[NAHEED, CARREFOUR]])
    r = audit(c, 3300).json();  print("7", r["method"], r["suggestion"])
    assert r["method"] == "regex" and r["suggestion"] == "lower"

    # 8. no Tavily key / search failure -> no_data, no endless loop
    agent.llm_available = lambda: False
    agent.tavily_available = lambda: False
    r = audit(c, 3300).json();  print("8", r["suggestion"], r["iterations"], r["summary"])
    assert r["suggestion"] == "no_data" and r["iterations"] == 1
    agent.tavily_available = lambda: True
    def down(q, d, e): raise TimeoutError()
    agent.web_search = down
    r = audit(c, 3300).json()
    assert r["suggestion"] == "no_data" and r["iterations"] == 1

    # 9. history, status and keys
    rows = c.get("/pricing/audits").json()
    assert len(rows) >= 5 and rows[0]["status"] == "suggested"
    done = c.post(f"/pricing/audits/{rows[0]['audit_id']}/status", json={"status": "applied"}).json()
    assert done["status"] == "applied"
    assert c.post("/pricing/audits/99999/status", json={"status": "applied"}).status_code == 404
    assert audit(c, 0).status_code == 422
    os.environ["ADMIN_API_KEY"] = "admin-secret"
    assert audit(c, 3300).status_code == 401
    assert c.get("/pricing/audits", headers={"X-Admin-Key": "admin-secret"}).status_code == 200
    print("ALL AGENT 3 TESTS PASSED")
