"""Serves the simple admin dashboard page at /admin."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Admin dashboard"])
PAGE = Path(__file__).resolve().parent.parent / "static" / "admin.html"


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_page():
    # The page itself contains no secrets; the API calls it makes need the admin key.
    return PAGE.read_text(encoding="utf-8")
