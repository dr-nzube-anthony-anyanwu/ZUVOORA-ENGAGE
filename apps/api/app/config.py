import re
from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]
_MODEL_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")


class Settings(BaseSettings):
    """API configuration. Secrets are SecretStr so they never appear in reprs or logs."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "ZUVOORA Engage API"
    app_env: Environment = "development"
    log_level: str = "INFO"
    api_cors_origins: str = "http://localhost:3073"
    # Dashboard base URL, used for auth email redirects (must be in Supabase redirect allow-list).
    dashboard_url: str = "http://localhost:3073"

    # Supabase (dedicated Engage project). URL is not secret; the secret key is server-only.
    supabase_url: str | None = None
    supabase_secret_key: SecretStr | None = None
    supabase_jwt_audience: str = "authenticated"
    # Defaults to f"{supabase_url}/auth/v1" when unset.
    supabase_jwt_issuer: str | None = None
    # Legacy HS256 shared secret. Only honoured in development/test; asymmetric JWKS otherwise.
    supabase_jwt_legacy_secret: SecretStr | None = None
    jwks_cache_seconds: int = 600

    # Postgres connection as the least-privileged `engage_api` role.
    database_url: SecretStr | None = None
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    openrouter_api_key: SecretStr | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # AI answering (Phase 3d, ADR-026/029). Off unless explicitly enabled. Model lists are
    # "primary,backup" OpenRouter ids, pinned (no "~...-latest" aliases).
    ai_enabled: bool = False
    # GLM 5.3 Flash was the planned standard backup, but it cannot run with reasoning disabled
    # (HTTP 400, verified 2026-11-22); reasoning tokens would add cost/latency, so GPT-6 Luna.
    ai_standard_models: str = "deepseek/deepseek-v4-flash,openai/gpt-6-luna"
    ai_complex_models: str = "deepseek/deepseek-v4.1-flash,openai/gpt-6-luna"
    ai_timeout_seconds: float = 20.0
    ai_max_output_tokens: int = Field(default=300, ge=50, le=800)
    # Founder-approved budgets in USD (ADR-026).
    ai_budget_tenant_daily_usd: Decimal = Decimal("0.20")
    ai_budget_global_daily_usd: Decimal = Decimal("0.50")
    ai_budget_global_monthly_usd: Decimal = Decimal("2.00")
    # Worst-case provider price, USD per million tokens; also sent as OpenRouter `max_price`.
    ai_max_prompt_usd_per_mtok: Decimal = Decimal("0.50")
    ai_max_completion_usd_per_mtok: Decimal = Decimal("1.00")
    resend_api_key: SecretStr | None = None
    email_from: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    # Public widget (Phase 3b). The token secret signs frame tickets and conversation tokens.
    widget_token_secret: SecretStr | None = None
    # Allow http:// embedding pages (any port) in frame-ancestors. Development/test only.
    widget_allow_http_frames: bool = False
    # Built widget assets (apps/widget/dist); defaults to the monorepo location.
    widget_dist_dir: str | None = None

    # Domain verification (DNS TXT). Empty = the operating system's resolvers.
    dns_resolvers: str = ""
    dns_timeout_seconds: float = 4.0
    domain_verify_cooldown_seconds: int = 15

    @field_validator("supabase_url")
    @classmethod
    def strip_trailing_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @field_validator("ai_standard_models", "ai_complex_models")
    @classmethod
    def pinned_model_list(cls, value: str) -> str:
        models = [x.strip() for x in value.split(",") if x.strip()]
        if not 1 <= len(models) <= 3:
            raise ValueError("give one primary model and at most two backups")
        for model in models:
            if not _MODEL_ID.match(model):
                raise ValueError(f"not a pinned OpenRouter model id: {model!r}")
        return ",".join(models)

    @model_validator(mode="after")
    def ai_settings_are_consistent(self) -> "Settings":
        if self.ai_enabled and self.openrouter_api_key is None:
            raise ValueError("AI_ENABLED requires OPENROUTER_API_KEY")
        if self.ai_enabled and not self.openrouter_base_url.startswith("https://"):
            raise ValueError("OPENROUTER_BASE_URL must use https")
        budgets = (
            self.ai_budget_tenant_daily_usd,
            self.ai_budget_global_daily_usd,
            self.ai_budget_global_monthly_usd,
        )
        if any(b < 0 for b in budgets) or not (
            self.ai_budget_tenant_daily_usd
            <= self.ai_budget_global_daily_usd
            <= self.ai_budget_global_monthly_usd
        ):
            raise ValueError("AI budgets must satisfy 0 <= tenant daily <= global daily <= monthly")
        return self

    def ai_tiers(self) -> dict[str, tuple[str, ...]]:
        return {
            "standard": tuple(self.ai_standard_models.split(",")),
            "complex": tuple(self.ai_complex_models.split(",")),
        }

    @model_validator(mode="after")
    def enforce_production_safety(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            missing = [
                name
                for name in ("supabase_url", "supabase_secret_key", "database_url",
                         "widget_token_secret")
                if getattr(self, name) is None
            ]
            if missing:
                raise ValueError(f"Missing required settings for {self.app_env}: {missing}")
            if self.supabase_jwt_legacy_secret is not None:
                raise ValueError(
                    "SUPABASE_JWT_LEGACY_SECRET is not allowed outside development/test"
                )
            if self.supabase_url and not self.supabase_url.startswith("https://"):
                raise ValueError("SUPABASE_URL must use https outside development/test")
            if self.widget_allow_http_frames:
                raise ValueError("WIDGET_ALLOW_HTTP_FRAMES is not allowed outside development/test")
            secret = self.widget_token_secret
            if secret is not None and len(secret.get_secret_value()) < 32:
                raise ValueError("WIDGET_TOKEN_SECRET must be at least 32 characters")
            if "*" in self.cors_origins:
                raise ValueError("Wildcard CORS origins are not allowed outside development/test")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [x.strip() for x in self.api_cors_origins.split(",") if x.strip()]

    @property
    def dns_nameservers(self) -> list[str]:
        return [x.strip() for x in self.dns_resolvers.split(",") if x.strip()]

    @property
    def jwt_issuer(self) -> str | None:
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        return f"{self.supabase_url}/auth/v1" if self.supabase_url else None

    @property
    def jwks_url(self) -> str | None:
        return f"{self.supabase_url}/auth/v1/.well-known/jwks.json" if self.supabase_url else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
