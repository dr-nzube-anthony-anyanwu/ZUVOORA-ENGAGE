"""Uniform, non-leaky error responses and security-event logging."""

from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

security_log = logging.getLogger("engage.security")
app_log = logging.getLogger("engage.app")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,100}$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found() -> ApiError:
    # Used for both "does not exist" and "not yours" so tenant existence is never revealed.
    return ApiError(404, "not_found", "Resource not found.")


def forbidden(message: str = "You do not have permission to perform this action.") -> ApiError:
    return ApiError(403, "forbidden", message)


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def log_security_event(request: Request, event: str, **fields: object) -> None:
    """Structured security log line. Never pass tokens, secrets or message content."""
    safe = {k: v for k, v in fields.items() if k not in {"token", "password", "secret"}}
    security_log.warning(
        "security_event=%s request_id=%s path=%s %s",
        event,
        request_id_of(request),
        request.url.path,
        " ".join(f"{k}={v}" for k, v in safe.items()),
    )


def _body(code: str, message: str, request: Request) -> dict[str, object]:
    return {"error": {"code": code, "message": message, "request_id": request_id_of(request)}}


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        request.state.request_id = (
            incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
        return JSONResponse(_body(exc.code, exc.message, request), exc.status, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body("http_error", message, request), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Report field locations and messages only; never echo submitted values back.
        details = [
            {"loc": [str(p) for p in err.get("loc", [])], "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        body = _body("validation_error", "Request validation failed.", request)
        body["error"]["details"] = details  # type: ignore[index]
        return JSONResponse(body, 422)

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        app_log.exception("unhandled_error request_id=%s", request_id_of(request))
        return JSONResponse(_body("internal_error", "Internal server error.", request), 500)
