"""Self-test for Agent 5:  python test_onboarding.py
(The Gemini calls are replaced by a fake, so no key and no internet are needed.)"""
import base64
import json
import os

from fastapi.testclient import TestClient
from app.main import app                      # importing the app loads your .env file...
from app.agents import onboarding_agent as agent

for key in ("GOOGLE_API_KEY", "SITE_API_KEY", "ADMIN_API_KEY"):   # ...so clear the keys afterwards
    os.environ.pop(key, None)

# a real 1x1 PNG
PNG = base64.b64encode(base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)).decode()
CATS = ["Cooking Oil", "Ghee", "Flour"]
BODY = {"name": "Kisan Cooking Oil 5 Liter", "image_base64": PNG, "mime_type": "image/png", "categories": CATS}

VISION = json.dumps({"product_type": "cooking oil", "colour": "yellow", "material": "plastic pouch",
                     "pack_size": "5 liter", "brand": "Kisan", "visible_text": ["Kisan", "Cooking Oil", "5 Liter"]})

LONG = ("Kisan cooking oil in a convenient 5 liter pouch is a dependable choice for daily family cooking. "
        "The golden oil suits frying, sauteing and everyday curries, and the sturdy pouch carton makes it easy "
        "to carry and store at home. Order Kisan cooking oil online and get it delivered to your door, with the "
        "choice of cash on delivery or bank transfer at checkout. Stock up for the month and enjoy simple, "
        "reliable grocery shopping without leaving the house.")
GOOD = {"title": "Kisan Cooking Oil 5 Liter Pouch", "short_description": "Kisan cooking oil in a 5 liter pouch.",
        "description": LONG, "seo_title": "Kisan Cooking Oil 5 Liter | Buy Online",
        "meta_description": "Buy Kisan cooking oil in a 5 liter pouch online with home delivery. Pay by cash on "
                            "delivery or bank transfer and stock up easily.",
        "tags": ["kisan", "cooking oil", "5 liter", "grocery"], "category": "cooking oil",
        "focus_keyword": "kisan cooking oil"}
BAD = dict(GOOD, description="Organic oil, a miracle for your health.", meta_description="Too short.",
           focus_keyword="best oil", category="Soap")


def with_fake_llm(replies):
    """Make the agent think a Gemini key exists and answer from a list of canned replies."""
    calls = []

    def fake(prompt, image_b64=None, mime_type="image/jpeg"):
        calls.append(prompt)
        return replies[min(len(calls) - 1, len(replies) - 1)]
    agent.llm_available = lambda: True
    agent.call_llm = fake
    return calls


with TestClient(app) as c:
    # 1. first draft is bad, the loop sends the problems back, second draft is good
    calls = with_fake_llm([VISION, json.dumps(BAD), json.dumps(GOOD)])
    r = c.post("/onboarding/product", json=BODY).json()
    print("1", r["status"], "attempts:", r["attempts"], "|", r["category"])
    for s in r["steps"]:
        print("   -", s[:150])
    assert r["status"] == "approved" and r["attempts"] == 2 and r["issues"] == []
    assert r["category"] == "Cooking Oil"                       # fixed upper/lower case
    assert "PROBLEMS" in calls[2] and "organic" in calls[2]      # the 2nd attempt received the feedback

    # 2. Gemini never gets it right -> stops after 3 attempts and asks for a human review
    with_fake_llm([VISION, json.dumps(BAD)])
    r = c.post("/onboarding/product", json=BODY).json()
    print("2", r["status"], r["attempts"], len(r["issues"]), "issue(s)")
    assert r["status"] == "needs_review" and r["attempts"] == 3 and r["issues"]

    # 3. an 'organic' claim is fine when the NAME says organic
    with_fake_llm([VISION, json.dumps(dict(GOOD, title="Organic Honey 500g Jar",
                                           description=LONG.replace("cooking oil", "organic honey"),
                                           seo_title="Organic Honey 500g | Buy Online", focus_keyword="organic honey"))])
    r = c.post("/onboarding/product", json=dict(BODY, name="Organic Honey 500g Jar", categories=["Cooking Oil"])).json()
    print("3", r["status"], r["issues"])
    assert r["status"] == "approved"

    # 4. Gemini returns garbage -> template fallback, flagged for review
    with_fake_llm([VISION, "this is not json"])
    r = c.post("/onboarding/product", json=BODY).json()
    print("4", r["mode"], r["status"], r["issues"])
    assert r["mode"] == "fallback" and r["status"] == "needs_review" and r["category"] == "Cooking Oil"

    # 5. no Gemini key at all -> name-only template, valid text, needs review
    agent.llm_available = lambda: False
    r = c.post("/onboarding/product", json=BODY).json()
    print("5", r["mode"], r["status"], r["attempts"], r["issues"])
    assert r["mode"] == "fallback" and r["status"] == "needs_review" and r["attempts"] == 1 and r["issues"] == []

    # 6. bad uploads are refused
    assert c.post("/onboarding/product", json=dict(BODY, image_base64="not base64!!")).status_code == 422
    assert c.post("/onboarding/product", json=dict(BODY, mime_type="image/jpeg")).status_code == 422   # PNG data, JPEG label
    assert c.post("/onboarding/product", json=dict(BODY, name="x")).status_code == 422
    print("6 bad uploads refused")

    # 7. site key
    os.environ["SITE_API_KEY"] = "site-secret"
    assert c.post("/onboarding/product", json=BODY).status_code == 401
    assert c.post("/onboarding/product", json=BODY, headers={"X-Site-Key": "site-secret"}).status_code == 200
    print("ALL AGENT 5 TESTS PASSED")