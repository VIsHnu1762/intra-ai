"""Short-lived, session-bound credentials for Agora's server-to-server MCP calls."""
from __future__ import annotations

from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.voice.models import VoiceSession


def issue_mcp_token(session: VoiceSession) -> str:
    return jwt.encode({
        "sub": session.user_id, "aud": "intra-voice-mcp", "iss": "intra-ai",
        "sid": session.session_id, "persona": session.persona,
        "exp": int(session.expires_at.timestamp()),
    }, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def verify_mcp_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM],
                            audience="intra-voice-mcp", issuer="intra-ai",
                            options={"require_exp": True, "require_sub": True, "require_aud": True})
        if (not isinstance(claims.get("sid"), str) or not isinstance(claims.get("persona"), str)
                or claims["persona"] not in {"taylor", "morgan"}):
            raise UnauthorizedError("Invalid assistant authorization")
        return claims
    except JWTError:
        raise UnauthorizedError("Invalid or expired assistant authorization") from None
