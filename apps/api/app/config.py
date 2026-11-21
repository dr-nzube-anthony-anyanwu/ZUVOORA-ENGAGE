from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "staging", "production"]


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
    openrouter_model: str | None = None
    resend_api_key: SecretStr | None = None
    email_from: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    # Domain verification (DNS TXT). Empty = the operating system's resolvers.
    dns_resolvers: str = ""
    dns_timeout_seconds: float = 4.0
    domain_verify_cooldown_seconds: int = 15

    @field_validator("supabase_url")
    @classmethod
    def strip_trailing_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value

    @model_validator(mode="after")
    def enforce_production_safety(self) -> "Settings":
        if self.app_env in {"staging", "production"}:
            missing = [
                name
                for name in ("supabase_url", "supabase_secret_key", "database_url")
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
