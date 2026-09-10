"""Local text boundary for future Agora adapters; no media credentials or SDKs."""
from typing import Protocol


class RealtimeSessionAdapter(Protocol):
    def describe(self, session_id: str) -> dict: ...


class LocalTextSessionAdapter:
    def describe(self, session_id: str) -> dict:
        return {"session_id": session_id, "mode": "local_text", "voice_available": False,
                "message": "Text session. Agora voice integration is planned separately."}
