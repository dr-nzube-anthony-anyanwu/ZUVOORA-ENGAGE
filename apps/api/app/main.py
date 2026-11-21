import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import get_settings
from app.db import Database
from app.middleware import BodySizeLimitMiddleware
from app.routes.content import router as content_router
from app.routes.domains import router as domains_router
from app.routes.health import router as health_router
from app.routes.knowledge import router as knowledge_router
from app.routes.me import router as me_router
from app.routes.platform import router as platform_router
from app.routes.public import router as public_router
from app.routes.tenants import router as tenants_router
from app.security.jwt import TokenVerifier
from app.services.domain_verification import DnsTxtVerifier
from app.services.extraction import MAX_UPLOAD_BYTES
from app.services.storage import SupabaseObjectStore
from app.services.supabase_admin import SupabaseAuthAdmin

settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Services are only created when configured; unconfigured features fail explicitly (503).
    app.state.verifier = TokenVerifier(settings) if settings.jwt_issuer else None
    app.state.auth_admin = (
        SupabaseAuthAdmin(settings)
        if settings.supabase_url and settings.supabase_secret_key is not None
        else None
    )
    app.state.domain_verifier = DnsTxtVerifier(settings)
    app.state.object_store = (
        SupabaseObjectStore(settings)
        if settings.supabase_url and settings.supabase_secret_key is not None
        else None
    )
    app.state.db = None
    if settings.database_url is not None:
        db = Database(settings)
        db.open()
        app.state.db = db
    try:
        yield
    finally:
        if app.state.db is not None:
            app.state.db.close()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Backend API for ZUVOORA Engage",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
    openapi_url="/openapi.json" if settings.app_env != "production" else None,
    lifespan=lifespan,
)
errors.install(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)
# Outermost: cap request bodies (10 MB upload + multipart overhead) before anything parses them.
app.add_middleware(BodySizeLimitMiddleware, max_bytes=MAX_UPLOAD_BYTES + 256 * 1024)
app.include_router(health_router)
app.include_router(public_router, prefix="/api/v1")
app.include_router(me_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(content_router, prefix="/api/v1")
app.include_router(domains_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(platform_router, prefix="/api/v1")
