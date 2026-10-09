"""Simple API-key protection.

ADMIN_API_KEY -> protects admin endpoints (approve refunds, list requests).
SITE_API_KEY  -> protects endpoints your website calls (refund request).

If a key is NOT set in the environment, that protection is OFF (handy for local
development). Always set both on Render before going live.
"""
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException


def _check(expected: str, provided: Optional[str]) -> None:
    if not expected:          # key not configured -> dev mode, allow
        return
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_admin(x_admin_key: Optional[str] = Header(default=None)) -> None:
    _check(os.getenv("ADMIN_API_KEY", ""), x_admin_key)


def require_site(x_site_key: Optional[str] = Header(default=None)) -> None:
    _check(os.getenv("SITE_API_KEY", ""), x_site_key)
