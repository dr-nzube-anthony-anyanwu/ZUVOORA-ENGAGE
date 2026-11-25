import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import errors
from app.config import get_settings
from app.db import Database
from app.middleware import BodySizeLimitMiddleware, install_proxy_headers
from app.routes.analytics import platform_router as analytics_platform_router
from app.routes.analytics import router as analytics_router
from app.routes.appointments import router as appointments_router
from app.routes.content import router as content_router
from app.routes.demo_requests import platform_router as demo_platform_router
from app.routes.demo_requests import public_router as demo_public_router
from app.routes.domains import router as domains_router
from app.routes.health import router as health_router
from app.routes.inbox import router as inbox_router
from app.routes.knowledge import router as knowledge_router
from app.routes.me import router as me_router
from app.routes.plans import clinic_router as plans_clinic_router
from app.routes.plans import platform_router as plans_platform_router
from app.routes.plans import usage_router
from app.routes.platform import router as platform_router
from app.routes.scheduling import router as scheduling_router
from app.routes.tenants import router as tenants_router
from app.routes.webhooks import router as webhooks_router
from app.routes.widget_admin import router as widget_admin_router
from app.routes.widget_booking import router as widget_booking_router
from app.routes.widget_public import router as widget_public_router
from app.security.jwt import TokenVerifier
from app.services.ai.factory import build_budget, build_responder, build_vision_reader
from app.services.domain_verification import DnsTxtVerifier
from app.services.extraction import MAX_UPLOAD_BYTES
from app.services.malware_scan import build_scanner
from app.services.scheduling.calcom import DefaultProviderFactory
from app.services.secrets_box import SecretsBox
from app.services.storage import SupabaseObjectStore
from app.services.supabase_admin import SupabaseAuthAdmin
from app.services.widget_tokens import WidgetTokens

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
    app.state.widget_tokens = (
        WidgetTokens(settings.widget_token_secret.get_secret_value())
        if settings.widget_token_secret is not None
        else None
    )
    app.state.object_store = (
        SupabaseObjectStore(settings)
        if settings.supabase_url and settings.supabase_secret_key is not None
        else None
    )
    app.state.responder = build_responder(settings)
    app.state.vision_reader = build_vision_reader(settings)  # None unless AI is enabled
    app.state.ai_budget = build_budget(settings)
    app.state.malware_scanner = build_scanner(settings)  # None unless CLAMAV_HOST is set
    app.state.secrets_box = (
        SecretsBox(
            settings.integrations_encryption_key.get_secret_value(),
            settings.integrations_encryption_key_previous.get_secret_value()
            if settings.integrations_encryption_key_previous
            else None,
        )
        if settings.integrations_encryption_key is not None
        else None
    )
    app.state.scheduling_providers = DefaultProviderFactory(settings.calcom_api_url)
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
    docs_url="/docs" if settings.api_docs_enabled else None,
    redoc_url="/redoc" if settings.api_docs_enabled else None,
    openapi_url="/openapi.json" if settings.api_docs_enabled else None,
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
# Outermost of all: the visitor's address from X-Forwarded-For, trusted only when the request
# comes from the reverse proxy or the dashboard server (FORWARDED_ALLOW_IPS; Phase 6, R2). The
# container runs uvicorn with --no-proxy-headers so this is the only place that decides.
install_proxy_headers(app, settings)
app.include_router(health_router)
app.include_router(me_router, prefix="/api/v1")
app.include_router(tenants_router, prefix="/api/v1")
app.include_router(content_router, prefix="/api/v1")
app.include_router(domains_router, prefix="/api/v1")
app.include_router(knowledge_router, prefix="/api/v1")
app.include_router(widget_admin_router, prefix="/api/v1")
app.include_router(inbox_router, prefix="/api/v1")
app.include_router(scheduling_router, prefix="/api/v1")
app.include_router(appointments_router, prefix="/api/v1")
app.include_router(webhooks_router)
app.include_router(widget_booking_router)
app.include_router(widget_public_router)
app.include_router(demo_public_router)
app.include_router(demo_platform_router, prefix="/api/v1")
app.include_router(platform_router, prefix="/api/v1")
app.include_router(plans_clinic_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(analytics_platform_router, prefix="/api/v1")
app.include_router(plans_platform_router, prefix="/api/v1")
