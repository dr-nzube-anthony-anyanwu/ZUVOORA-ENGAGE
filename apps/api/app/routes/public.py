from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=["public-widget"])


class WidgetSessionRequest(BaseModel):
    widget_id: str = Field(min_length=8, max_length=128)


@router.post("/public/widget/session")
async def create_widget_session(payload: WidgetSessionRequest, request: Request):
    # Intentionally disabled until Phase 1-3 tenant/domain security is implemented.
    if not request.headers.get("origin"):
        raise HTTPException(status_code=400, detail="A valid website origin is required.")
    raise HTTPException(
        status_code=501,
        detail="Widget session is not enabled. Complete tenant and domain verification first.",
    )
