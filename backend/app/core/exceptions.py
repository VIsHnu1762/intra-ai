from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = structlog.stdlib.get_logger("intra_ai.exceptions")


# ── Base exception ───────────────────────────────────────


class AppError(Exception):
    """Base application error with HTTP status and machine-readable code."""

    status_code: int = 500
    code: str = "INTERNAL_ERROR"
    message: str = "An unexpected error occurred"

    def __init__(
        self,
        message: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details
        super().__init__(self.message)


# ── Concrete errors ──────────────────────────────────────


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"
    message = "Resource not found"


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Authentication required"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"
    message = "Insufficient permissions"


class ValidationError(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"
    message = "Request validation failed"


class ConflictError(AppError):
    status_code = 409
    code = "CONFLICT"
    message = "Resource already exists"


class AgentNotFoundError(NotFoundError):
    code = "AGENT_NOT_FOUND"
    message = "Interviewer agent not found"


class AgoraConfigurationError(AppError):
    status_code = 500
    code = "AGORA_CONFIG_ERROR"
    message = "Agora Agent Studio configuration error"


# ── Handler registration ─────────────────────────────────


def _build_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        body["details"] = details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    """Attach structured error handlers to the FastAPI *app*."""

    @app.exception_handler(AppError)
    async def _app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "app_error",
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_build_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        # Provider/database exceptions can include connection URLs or raw payloads.
        logger.error("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=_build_body("INTERNAL_ERROR", "An unexpected error occurred"),
        )
