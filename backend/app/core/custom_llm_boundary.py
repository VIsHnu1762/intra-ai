"""Authenticate Agora turn callbacks without changing the interview adapter."""
import hmac

from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class CustomLLMCredentialBoundary:
    paths = frozenset({"/api/v1/chat/completions", "/v1/chat/completions"})

    def __init__(self, app, key):
        self.app = app
        self.key = str(key or "")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST" or scope.get("path", "").rstrip("/") not in self.paths:
            return await self.app(scope, receive, send)
        if not self.key:
            response = JSONResponse({"error": {"message": "Interview callback authentication is not configured", "type": "server_error", "code": "callback_unavailable"}}, status_code=503)
            return await response(scope, receive, send)
        authorization = Headers(scope=scope).get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        valid = bool(separator and scheme.lower() == "bearer" and credential and
                     hmac.compare_digest(credential.encode("utf-8"), self.key.encode("utf-8")))
        if not valid:
            response = JSONResponse({"error": {"message": "Invalid interview callback credential", "type": "authentication_error", "code": "unauthorized"}}, status_code=401, headers={"WWW-Authenticate": "Bearer"})
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
