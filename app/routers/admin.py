"""Serves the simple admin dashboard page at /admin.

If you manage everything inside WordPress (WooCommerce > AI Agents), set the environment
variable DISABLE_ADMIN_PAGE=1 on Render and this separate page disappears (404)."""
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Admin dashboard"])
PAGE = Path(__file__).resolve().parent.parent / "static" / "admin.html"


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page():
    if os.getenv("DISABLE_ADMIN_PAGE", "").strip().lower() in ("1", "true", "yes"):
        raise HTTPException(status_code=404, detail="Not found")
    # The page itself contains no secrets; the API calls it makes need the admin key.
    return PAGE.read_text(encoding="utf-8")