"""HTTP endpoint for Agent 2."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..agents.discovery_agent import run_discovery
from ..database import get_db
from ..models import CatalogProduct
from ..schemas import ProductHit, RecommendIn, RecommendOut
from ..security import require_site

router = APIRouter(tags=["Agent 2 - Product Discovery"])


@router.post("/recommendations", response_model=RecommendOut, dependencies=[Depends(require_site)])
def recommendations(payload: RecommendIn, db: Session = Depends(get_db)):
    """Customer search ('winter jacket and shoes under 5000') -> best matching products."""
    rows = db.query(CatalogProduct).filter(CatalogProduct.in_stock.is_(True)).all()
    catalog = [
        {"id": r.external_id, "name": r.name, "price": r.price, "category": r.category,
         "description": r.description, "url": r.url, "image_url": r.image_url}
        for r in rows
    ]
    customer = {"email": payload.customer_email, "purchased_product_ids": payload.purchased_product_ids}
    state = run_discovery(payload.query, catalog, customer, payload.limit)

    parsed = state["parsed"]
    return RecommendOut(
        query=payload.query,
        interpretation={
            "items": [i["name"] for i in parsed["items"]],
            "max_price": parsed.get("max_price"),
            "min_price": parsed.get("min_price"),
            "method": parsed.get("method"),
        },
        results=[ProductHit(**r) for r in state.get("results", [])],
        steps=state.get("steps", []),
    )
