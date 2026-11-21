"""Model gateways: OpenRouter for real calls, a scripted fake for tests and local development.

Every OpenRouter request:
  * lists the tier's primary model then its backups (`models`), so OpenRouter fails over itself;
  * requires zero-data-retention providers that do not collect prompts (`zdr`,
    `data_collection: deny`) — if none is available the request fails and we fall back;
  * caps the provider price (`max_price`), so routing can never pick an expensive endpoint;
  * caps output tokens and disables reasoning tokens (cost and latency).

Errors never include the request or response body (they could contain visitor text).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

import httpx

Tier = Literal["standard", "complex"]
MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class ModelRequest:
    tier: Tier
    models: tuple[str, ...]  # primary first, then backups
    messages: tuple[ChatMessage, ...]
    max_output_tokens: int


@dataclass(frozen=True)
class ModelResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal


@dataclass(frozen=True)
class PriceCeiling:
    """Worst-case USD per million tokens; also sent to OpenRouter as `max_price`."""

    prompt: Decimal
    completion: Decimal

    def cost(self, prompt_tokens: int, completion_tokens: int) -> Decimal:
        return (prompt_tokens * self.prompt + completion_tokens * self.completion) / MILLION


def estimate_prompt_tokens(messages: tuple[ChatMessage, ...]) -> int:
    """Deliberately high (≈3 characters per token) so budget checks err on the safe side."""
    return sum(len(m.content) for m in messages) // 3 + 8 * len(messages)


class ModelError(Exception):
    """A failed model call. `billed_estimate` is set when the provider may still have charged."""

    def __init__(self, kind: str, billed_estimate: ModelResult | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.billed_estimate = billed_estimate


class ModelGateway(Protocol):
    provider: Literal["openrouter", "fake"]

    def complete(self, request: ModelRequest) -> ModelResult: ...


class OpenRouterGateway:
    provider: Literal["openrouter"] = "openrouter"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        ceiling: PriceCeiling,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._ceiling = ceiling
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds, connect=5.0),
            headers={"Authorization": f"Bearer {api_key}", "X-Title": "ZUVOORA Engage"},
            transport=transport,
            follow_redirects=False,
        )

    def body(self, request: ModelRequest) -> dict:
        return {
            "models": list(request.models),
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": 0.2,
            "reasoning": {"enabled": False},
            "usage": {"include": True},
            "provider": {
                "zdr": True,
                "data_collection": "deny",
                "allow_fallbacks": True,
                "max_price": {
                    "prompt": float(self._ceiling.prompt),
                    "completion": float(self._ceiling.completion),
                },
            },
        }

    def _worst_case(self, request: ModelRequest) -> ModelResult:
        prompt = estimate_prompt_tokens(request.messages)
        return ModelResult(
            text="",
            model=request.models[0],
            prompt_tokens=prompt,
            completion_tokens=request.max_output_tokens,
            cost_usd=self._ceiling.cost(prompt, request.max_output_tokens),
        )

    def complete(self, request: ModelRequest) -> ModelResult:
        try:
            response = self._client.post("/chat/completions", json=self.body(request))
        except httpx.TimeoutException as exc:
            # The provider may have generated (and billed) the answer: count the worst case.
            raise ModelError("timeout", self._worst_case(request)) from exc
        except httpx.HTTPError as exc:
            raise ModelError("transport") from exc
        if response.status_code != 200:
            raise ModelError(f"http_{response.status_code}")
        try:
            data = response.json()
            if data.get("error"):
                raise ModelError("provider_error")
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            usage = data.get("usage") or {}
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            cost = usage.get("cost")
        except ModelError:
            raise
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ModelError("malformed_response", self._worst_case(request)) from exc
        cost_usd = (
            Decimal(str(cost))
            if isinstance(cost, int | float) and cost >= 0
            else self._ceiling.cost(prompt_tokens, completion_tokens)
        )
        return ModelResult(
            text=str(text),
            model=str(data.get("model") or request.models[0])[:120],
            prompt_tokens=max(prompt_tokens, 0),
            completion_tokens=max(completion_tokens, 0),
            cost_usd=cost_usd,
        )

    def close(self) -> None:
        self._client.close()


class FakeGateway:
    """Deterministic stand-in: `script(request)` returns the answer text or raises ModelError."""

    provider: Literal["fake"] = "fake"
    COST = Decimal("0.000010")

    def __init__(self, script: Callable[[ModelRequest], str]) -> None:
        self._script = script
        self.requests: list[ModelRequest] = []

    def complete(self, request: ModelRequest) -> ModelResult:
        self.requests.append(request)
        text = self._script(request)
        return ModelResult(
            text=text,
            model=f"fake/{request.tier}",
            prompt_tokens=estimate_prompt_tokens(request.messages),
            completion_tokens=len(text) // 3,
            cost_usd=self.COST,
        )
