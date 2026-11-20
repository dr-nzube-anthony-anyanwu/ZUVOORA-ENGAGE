from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def readiness(request: Request):
    db = getattr(request.app.state, "db", None)
    if db is not None and not db.ping():
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}
