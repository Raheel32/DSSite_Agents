"""AGENT 4 - Order Fraud Detection & Verification Pipeline (Sequential).

LangGraph concepts used here:
  * State        : a TypedDict that flows through every node.
  * Reducer      : `Annotated[int, operator.add]` means when a node returns
                   {"fraud_score": 20}, LangGraph ADDS it to the running total
                   instead of overwriting it. Same for `reasons` (lists are joined).
  * Sequential   : START -> check_ip -> check_payment -> check_speed -> decide -> END
"""
import ipaddress
import operator
from typing import Annotated, List, TypedDict

from langgraph.graph import StateGraph, START, END

FLAG_THRESHOLD = 25          # total score >= 50  -> "Flagged"
HIGH_COD_AMOUNT = 20000      # big Cash-on-Delivery orders are riskier
VERY_HIGH_AMOUNT = 50000
BLOCKED_IPS = {"203.0.113.66", "198.51.100.23"}  # sample blocklist (demo only)


class FraudState(TypedDict):
    order: dict                                   # the order sent by the website
    history: dict                                 # past data looked up from the DB
    fraud_score: Annotated[int, operator.add]     # reducer: scores add up
    reasons: Annotated[List[str], operator.add]   # reducer: reasons accumulate
    verdict: str


# ---------------------------------------------------------------- Node 1
def check_ip(state: FraudState) -> dict:
    order, history = state["order"], state["history"]
    score, reasons = 0, []

    try:
        ip = ipaddress.ip_address(order["ip_address"])
        if ip.is_private or ip.is_loopback:
            score += 20
            reasons.append("IP is private/loopback (possible proxy or spoofed header)")
    except ValueError:
        score += 40
        reasons.append("IP address is not valid")

    if order["ip_address"] in BLOCKED_IPS:
        score += 50
        reasons.append("IP is on the blocklist")

    ip_c, ship_c = order.get("ip_country"), order.get("shipping_country")
    if ip_c and ship_c and ip_c.upper() != ship_c.upper():
        score += 20
        reasons.append(f"IP country ({ip_c}) differs from shipping country ({ship_c})")

    if history.get("flagged_from_ip", 0) > 0:
        score += 30
        reasons.append("This IP was flagged on a previous order")

    return {"fraud_score": score, "reasons": reasons}


# ---------------------------------------------------------------- Node 2
def check_payment(state: FraudState) -> dict:
    order = state["order"]
    score, reasons = 0, []
    method, amount = order["payment_method"], order["amount"]

    if method == "cod" and amount > HIGH_COD_AMOUNT:
        score += 25
        reasons.append(f"High-value Cash on Delivery order ({amount:,.0f})")
    if method == "bank_transfer" and amount > VERY_HIGH_AMOUNT:
        score += 15
        reasons.append(f"Very high bank-transfer amount ({amount:,.0f}) needs manual proof check")

    return {"fraud_score": score, "reasons": reasons}


# ---------------------------------------------------------------- Node 3
def check_speed(state: FraudState) -> dict:
    order, history = state["order"], state["history"]
    score, reasons = 0, []

    secs = order.get("checkout_seconds")
    if secs is not None:
        if secs < 20:
            score += 30
            reasons.append(f"Order placed extremely fast ({secs}s) - looks like a bot")
        elif secs < 60:
            score += 15
            reasons.append(f"Order placed very quickly ({secs}s)")

    if history.get("orders_last_10min", 0) >= 3:
        score += 30
        reasons.append("3+ orders from the same customer in 10 minutes")

    return {"fraud_score": score, "reasons": reasons}


# ---------------------------------------------------------------- Node 4
def decide(state: FraudState) -> dict:
    verdict = "Flagged" if state["fraud_score"] >= FLAG_THRESHOLD else "Safe"
    return {"verdict": verdict}


def build_fraud_graph():
    g = StateGraph(FraudState)
    g.add_node("check_ip", check_ip)
    g.add_node("check_payment", check_payment)
    g.add_node("check_speed", check_speed)
    g.add_node("decide", decide)

    g.add_edge(START, "check_ip")
    g.add_edge("check_ip", "check_payment")
    g.add_edge("check_payment", "check_speed")
    g.add_edge("check_speed", "decide")
    g.add_edge("decide", END)
    return g.compile()


fraud_graph = build_fraud_graph()


def run_fraud_check(order: dict, history: dict) -> dict:
    """Run the graph and return the final state."""
    return fraud_graph.invoke(
        {"order": order, "history": history, "fraud_score": 0, "reasons": [], "verdict": ""}
    )

git add .
git commit -m "threshold changes in fraud agents 50 to 25"
git push