"""In-memory store for live InterviewSession objects.

Separate from InterviewSessionStore (which stores InterviewAIContext for M1/orchestrator).
This store owns meeting-level state: channel, agents, status.
"""

from __future__ import annotations

import asyncio
from typing import Optional
import structlog

from app.sessions.models import InterviewSession, InterviewConfiguration

logger = structlog.stdlib.get_logger("intra_ai.sessions.store")


class SessionStore:
    """In-memory meeting store with one async lifecycle lock per interview."""

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewSession] = {}
        self._channels: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def create(self, config: InterviewConfiguration) -> InterviewSession:
        """Create and store a new InterviewSession from an InterviewConfiguration.

        If a session with the same interview_id already exists, it is returned as-is
        (idempotent create).
        """
        if config.interview_id in self._sessions:
            logger.info(
                "[SESSION_EXISTS]",
                interview_id=config.interview_id,
                channel=self._sessions[config.interview_id].channel_name,
            )
            return self._sessions[config.interview_id]

        session = InterviewSession.from_config(config)
        self.set(session)

        logger.info(
            "[SESSION_CREATED]",
            interview_id=session.interview_id,
            channel=session.channel_name,
            selected_agents=session.agent_ids,
            current_agent=session.current_agent_id,
        )
        return session

    def get(self, interview_id: str) -> Optional[InterviewSession]:
        """Resolve the platform ID or its exact registered Agora channel.

        Custom LLM callbacks use channel identity while platform routes use the
        interview ID. Both must reach the same meeting for physical handoffs.
        """
        identifier = interview_id.strip()
        return self._sessions.get(self._channels.get(identifier, identifier))

    def get_lock(self, interview_id: str) -> asyncio.Lock:
        """Serialize starts, handoffs and stops, including channel aliases."""
        session = self.get(interview_id)
        key = session.interview_id if session else interview_id.strip()
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def set(self, session: InterviewSession) -> None:
        """Store or update a session."""
        self._sessions[session.interview_id] = session
        self._channels[session.channel_name] = session.interview_id

    def delete(self, interview_id: str) -> None:
        """Remove a session."""
        session = self.get(interview_id)
        if session:
            self._sessions.pop(session.interview_id, None)
            self._channels.pop(session.channel_name, None)

    def list_ids(self) -> list[str]:
        """Return all active session IDs."""
        return list(self._sessions.keys())

    def has(self, interview_id: str) -> bool:
        """Check whether a session exists."""
        return self.get(interview_id) is not None


# Global singleton
session_store = SessionStore()
