"""Catalog sync: your website keeps the agent's copy of the product list up to date."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CatalogProduct, utcnow
from ..schemas import CatalogSyncIn
from ..security import require_admin, require_site

router = APIRouter(prefix="/catalog", tags=["Catalog (feeds Agent 2)"])


@router.post("/products", dependencies=[Depends(require_site)])
def upsert_products(payload: CatalogSyncIn, db: Session = Depends(get_db)):
    """Add new products and update existing ones (matched by external_id). Up to 200 per call."""
    created = updated = 0
    for item in payload.products:
        row = db.query(CatalogProduct).filter(CatalogProduct.external_id == item.external_id).first()
        data = item.model_dump(exclude={"external_id"})
        if row:
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = utcnow()
            updated += 1
        else:
            db.add(CatalogProduct(external_id=item.external_id, **data))
            created += 1

    # the first REAL product removes the demo/sample products
    if any(not p.external_id.startswith("sample-") for p in payload.products):
        db.query(CatalogProduct).filter(CatalogProduct.external_id.like("sample-%")).delete(
            synchronize_session=False
        )
    db.commit()
    return {"created": created, "updated": updated}


@router.delete("/products/{external_id}", dependencies=[Depends(require_site)])
def delete_product(external_id: str, db: Session = Depends(get_db)):
    """Called when a product is deleted or unpublished on the website."""
    deleted = db.query(CatalogProduct).filter(CatalogProduct.external_id == external_id).delete()
    db.commit()
    return {"deleted": deleted}


@router.get("/stats", dependencies=[Depends(require_admin)])
def stats(db: Session = Depends(get_db)):
    total = db.query(CatalogProduct).count()
    in_stock = db.query(CatalogProduct).filter(CatalogProduct.in_stock.is_(True)).count()
    sample = db.query(CatalogProduct).filter(CatalogProduct.external_id.like("sample-%")).count()
    return {"total": total, "in_stock": in_stock, "sample_products": sample}
