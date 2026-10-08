"""Small SAMPLE dataset so you can test without a real shop.
Runs automatically on startup, but only if the tables are empty."""
from sqlalchemy.orm import Session
from .models import Product, Order

PRODUCTS = [
    ("Winter Puffer Jacket", "jackets", 4200, "Warm padded jacket for cold weather"),
    ("Leather Biker Jacket", "jackets", 9500, "Classic black leather jacket"),
    ("Fleece Zip Hoodie", "jackets", 2800, "Soft fleece hoodie, great for winters"),
    ("Running Shoes Pro", "shoes", 3900, "Lightweight breathable running shoes"),
    ("Canvas Sneakers", "shoes", 2200, "Everyday casual sneakers"),
    ("Leather Formal Shoes", "shoes", 6500, "Office-ready leather shoes"),
    ("Woolen Cap", "accessories", 650, "Warm woolen cap"),
    ("Cotton Socks (3 pack)", "accessories", 450, "Soft cotton socks"),
]

ORDERS = [
    ("ORD-0001", "ali@example.com", 4200, "cod"),
    ("ORD-0002", "sara@example.com", 6100, "bank_transfer"),
    ("ORD-0003", "ahmed@example.com", 2200, "cod"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Product).count() == 0:
        db.add_all(Product(name=n, category=c, price=p, description=d) for n, c, p, d in PRODUCTS)
    if db.query(Order).count() == 0:
        db.add_all(
            Order(order_ref=r, customer_email=e, amount=a, payment_method=m) for r, e, a, m in ORDERS
        )
    db.commit()
