"""Small async bridge to the existing synchronous Supabase client."""

import asyncio
from typing import Any

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError, ValidationError


class DependencyUnavailable(AppError):
    status_code = 503
    code = "DEPENDENCY_UNAVAILABLE"
    message = "A required service is temporarily unavailable. Your saved data is preserved."


async def execute(query: Any) -> Any:
    try:
        result = await asyncio.to_thread(query.execute)
        return result.data
    except AppError:
        raise
    except Exception as exc:
        code = str(getattr(exc, "code", ""))
        message = str(exc)
        if code == "23505" or "VERSION_CONFLICT" in message or "REPLAY_MISMATCH" in message:
            raise ConflictError("State changed or request ID was reused. Refresh before retrying") from None
        if "FEATURE_FORBIDDEN" in message:
            raise ForbiddenError() from None
        if "FEATURE_NOT_FOUND" in message:
            raise NotFoundError() from None
        if code in {"23514", "23503", "22023"} or "FEATURE_INVALID" in message:
            raise ValidationError("The requested transition or data is invalid") from None
        raise DependencyUnavailable() from None


async def rpc(sb: Any, name: str, **params: Any) -> Any:
    return await execute(sb.rpc(name, params))


def tenant_key(actor: Any) -> str:
    return str(actor.tenant_id) if actor.tenant_id else "user:" + actor.user_id
