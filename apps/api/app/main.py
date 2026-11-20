from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.health import router as health_router
from app.routes.public import router as public_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Add managed clients/pools here in later phases and close them on shutdown.
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend API for ZUVOORA Engage",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
app.include_router(health_router)
app.include_router(public_router, prefix="/api/v1")
