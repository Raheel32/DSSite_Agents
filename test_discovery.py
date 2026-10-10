"""Self-test for Agent 2:  python test_discovery.py"""
import os
os.environ.pop("GOOGLE_API_KEY", None)
os.environ.pop("SITE_API_KEY", None)
os.environ.pop("ADMIN_API_KEY", None)

from fastapi.testclient import TestClient
from app.main import app


def names(resp):
    return [r["name"] for r in resp["results"]]


with TestClient(app) as c:
    # 1. the BRD example: two items + budget
    r = c.post("/recommendations", json={"query": "sardi ke liye jacket aur shoes under 5000"}).json()
    print("1", r["interpretation"], "\n ", names(r))
    assert r["interpretation"]["max_price"] == 5000
    assert "Winter Puffer Jacket" in names(r) and "Running Shoes Pro" in names(r)
    assert "Leather Biker Jacket" not in names(r) and "Leather Formal Shoes" not in names(r)   # over budget
    assert any("jacket" in n.lower() or "hoodie" in n.lower() for n in names(r)[:2])           # both items shown early
    assert any("shoes" in n.lower() or "sneakers" in n.lower() for n in names(r)[:2])

    # 2. shorthand price
    r = c.post("/recommendations", json={"query": "shoes below 3k"}).json()
    print("2", names(r)); assert names(r) == ["Canvas Sneakers"]

    # 3. minimum price
    r = c.post("/recommendations", json={"query": "jacket above 5000"}).json()
    print("3", names(r)); assert names(r) == ["Leather Biker Jacket"]

    # 4. purchase history boosts and labels what the customer bought before
    base = c.post("/recommendations", json={"query": "shoes"}).json()
    hist = c.post("/recommendations", json={"query": "shoes", "purchased_product_ids": ["sample-5"]}).json()
    def find(resp, name):
        return next(x for x in resp["results"] if x["name"] == name)
    bought = find(hist, "Canvas Sneakers")
    print("4", [(x["name"], x["score"]) for x in base["results"]], "->", [(x["name"], x["score"]) for x in hist["results"]])
    assert "bought a similar item before" in bought["matched"]
    assert bought["score"] > find(base, "Canvas Sneakers")["score"]          # bought before -> boosted
    assert all("bought a similar item before" in x["matched"] for x in hist["results"])   # same category -> familiar
    assert not any("bought a similar item before" in x["matched"] for x in base["results"])

    # 5. daily sync: new real products arrive, samples disappear
    sync = c.post("/catalog/products", json={"products": [
        {"external_id": "101", "name": "KISAN COOKING OIL 5 Liter", "price": 2875, "category": "Oil, Grocery",
         "description": "pure cooking oil pouch", "url": "https://shop.example/oil", "in_stock": True},
        {"external_id": "102", "name": "DALDA BANASPATI GHEE 5 kg", "price": 3125, "category": "Ghee, Grocery",
         "description": "banaspati ghee", "url": "javascript:alert(1)", "in_stock": True},
        {"external_id": "103", "name": "Sold Out Oil 1 Liter", "price": 600, "category": "Oil", "in_stock": False},
    ]}).json()
    print("5", sync); assert sync == {"created": 3, "updated": 0}
    stats = c.get("/catalog/stats").json(); print("  stats", stats)
    assert stats["sample_products"] == 0 and stats["total"] == 3

    r = c.post("/recommendations", json={"query": "cooking oil and ghee under 3000"}).json()
    print("  ", names(r), r["interpretation"]["items"])
    assert names(r) == ["KISAN COOKING OIL 5 Liter"]              # ghee is Rs 3,125 (over), sold-out oil hidden
    r = c.post("/recommendations", json={"query": "ghee"}).json()
    assert r["results"][0]["url"] == ""                            # unsafe link was blanked

    # 6. update an existing product (price drop) + delete one
    up = c.post("/catalog/products", json={"products": [
        {"external_id": "102", "name": "DALDA BANASPATI GHEE 5 kg", "price": 2900, "category": "Ghee", "in_stock": True}]}).json()
    print("6", up); assert up == {"created": 0, "updated": 1}
    r = c.post("/recommendations", json={"query": "cooking oil and ghee under 3000"}).json()
    assert len(r["results"]) == 2
    assert c.delete("/catalog/products/101").json() == {"deleted": 1}

    # 7. gibberish does not crash
    r = c.post("/recommendations", json={"query": "zzzzqqq"}).json()
    print("7", r["results"]); assert r["results"] == []

    # 8. keys
    os.environ["SITE_API_KEY"] = "site-secret"; os.environ["ADMIN_API_KEY"] = "admin-secret"
    assert c.post("/recommendations", json={"query": "ghee"}).status_code == 401
    assert c.post("/recommendations", json={"query": "ghee"}, headers={"X-Site-Key": "site-secret"}).status_code == 200
    assert c.get("/catalog/stats").status_code == 401
    print("ALL AGENT 2 TESTS PASSED")
