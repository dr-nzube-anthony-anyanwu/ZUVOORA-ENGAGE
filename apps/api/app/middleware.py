"""ASGI middleware that caps request body size before the application reads it.

Checks the declared Content-Length and also counts streamed bytes, so chunked or lying clients
cannot push more than the limit into multipart parsing. Applies to every route; the largest
legitimate request is a 10 MB knowledge upload plus form overhead. A reverse proxy should
enforce the same limit in production (Phase 6).
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class PayloadTooLarge(Exception):
    """Raised while streaming a body over the limit; handled as 413 (see errors.install)."""


async def _reject(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps({"error": {"code": code, "message": message, "request_id": None}}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        message = f"Request body is larger than {self.max_bytes // (1024 * 1024)} MB."
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                await _reject(send, 400, "bad_request", "Invalid Content-Length header.")
                return
            if size > self.max_bytes:
                await _reject(send, 413, "payload_too_large", message)
                return

        received = 0
        started = False

        async def limited_receive() -> Message:
            nonlocal received
            msg = await receive()
            if msg["type"] == "http.request":
                received += len(msg.get("body", b""))
                if received > self.max_bytes:
                    raise PayloadTooLarge
            return msg

        async def tracking_send(msg: Message) -> None:
            nonlocal started
            if msg["type"] == "http.response.start":
                started = True
            await send(msg)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except PayloadTooLarge:
            if not started:
                await _reject(send, 413, "payload_too_large", message)
