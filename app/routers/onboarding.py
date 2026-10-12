"""HTTP endpoint for Agent 5."""
from fastapi import APIRouter, Depends

from ..agents.onboarding_agent import run_onboarding
from ..schemas import OnboardIn, OnboardOut
from ..security import require_site

router = APIRouter(tags=["Agent 5 - Product Onboarding & SEO"])


@router.post("/onboarding/product", response_model=OnboardOut, dependencies=[Depends(require_site)])
def onboard_product(payload: OnboardIn):
    """Vendor gives a photo + name; the agent returns the full product page content."""
    state = run_onboarding(payload.name, payload.image_base64, payload.mime_type, payload.categories)
    d = state["draft"]
    return OnboardOut(
        status=state["status"], mode=state.get("mode", "fallback"), attempts=state["attempts"],
        title=d["title"], short_description=d["short_description"], description=d["description"],
        seo_title=d["seo_title"], meta_description=d["meta_description"], tags=d["tags"],
        category=d["category"], focus_keyword=d["focus_keyword"], issues=state["issues"],
        details=state.get("details") or {}, steps=state["steps"],
    )