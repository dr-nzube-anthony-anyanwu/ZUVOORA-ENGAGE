"""Builds the widget responder from settings. AI is attached only when explicitly enabled."""

from __future__ import annotations

from app.config import Settings
from app.services.ai.answerer import AiAnswerer, Budget
from app.services.ai.gateway import OpenRouterGateway, PriceCeiling
from app.services.answering.pipeline import FactsFirstResponder


def build_responder(settings: Settings) -> FactsFirstResponder:
    if not settings.ai_enabled or settings.openrouter_api_key is None:
        return FactsFirstResponder()
    ceiling = PriceCeiling(
        prompt=settings.ai_max_prompt_usd_per_mtok,
        completion=settings.ai_max_completion_usd_per_mtok,
    )
    gateway = OpenRouterGateway(
        api_key=settings.openrouter_api_key.get_secret_value(),
        base_url=settings.openrouter_base_url,
        timeout_seconds=settings.ai_timeout_seconds,
        ceiling=ceiling,
    )
    answerer = AiAnswerer(
        gateway=gateway,
        tiers=settings.ai_tiers(),  # type: ignore[arg-type]
        budget=Budget(
            tenant_daily=settings.ai_budget_tenant_daily_usd,
            global_daily=settings.ai_budget_global_daily_usd,
            global_monthly=settings.ai_budget_global_monthly_usd,
        ),
        ceiling=ceiling,
        max_output_tokens=settings.ai_max_output_tokens,
    )
    return FactsFirstResponder(ai=answerer)
