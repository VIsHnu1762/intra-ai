"""In-memory session store for InterviewAIContext orchestration state."""

from __future__ import annotations

import asyncio
from typing import Optional
import structlog

from app.interview_context.models import InterviewAIContext
from app.models.enums import DifficultyLevel

logger = structlog.stdlib.get_logger("intra_ai.interview_context.store")


class InterviewSessionStore:
    """Isolated in-memory session store for InterviewAIContext instances.

    Guarantees:
    - Isolation per interview_id (zero candidate data leakage across sessions).
    - Preserves short-term orchestration state across multiple turns in a running backend.
    - Resolves Agora call_id, agent_uuid, and channel aliases to the canonical interview_id.
    - Provides per-interview async locks for serialized state mutation.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, InterviewAIContext] = {}
        self._aliases: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._global_lock = asyncio.Lock()

    def get_lock(self, interview_id: str) -> asyncio.Lock:
        """Return dedicated asyncio.Lock for the resolved interview_id."""
        clean_id = self.resolve_interview_id(interview_id)
        if clean_id not in self._locks:
            self._locks[clean_id] = asyncio.Lock()
        return self._locks[clean_id]

    def register_alias(self, alias: str, interview_id: str) -> None:
        """Map an external identifier (e.g. Agora call_id, agent_uuid, agora_agent_id) to the canonical interview_id."""
        if alias and alias.strip() and interview_id and interview_id.strip():
            clean_alias = alias.strip()
            clean_id = interview_id.strip()
            self._aliases[clean_alias] = clean_id
            logger.info("session_alias_registered", alias=clean_alias, canonical_interview_id=clean_id)

    def resolve_interview_id(self, identifier: Optional[str] = None, default: Optional[str] = None) -> str:
        """Resolve any given identifier/alias to the canonical interview_id."""
        if identifier and identifier.strip():
            clean = identifier.strip()
            if clean in self._sessions:
                return clean
            if clean in self._aliases:
                return self._aliases[clean]

        if default and default.strip():
            clean_def = default.strip()
            if clean_def in self._sessions:
                return clean_def
            if clean_def in self._aliases:
                return self._aliases[clean_def]

        if identifier and identifier.strip():
            return identifier.strip()

        # If no identifier was given and exactly one active session exists, map to it
        if len(self._sessions) == 1:
            return next(iter(self._sessions.keys()))

        # Return None / empty string if we cannot resolve — the caller is responsible for
        # creating an isolated ephemeral session. Never fall back to test-room-101 implicitly.
        return default.strip() if default and default.strip() else ""

    def get(self, interview_id: str) -> Optional[InterviewAIContext]:
        """Retrieve context for a specific interview_id or alias, or None if not found."""
        clean_id = self.resolve_interview_id(interview_id)
        return self._sessions.get(clean_id)

    def set(self, interview_id: str, context: InterviewAIContext) -> None:
        """Store or update context for an interview_id."""
        clean_id = self.resolve_interview_id(interview_id)
        self._sessions[clean_id] = context

    def get_or_create(
        self,
        interview_id: str,
        candidate_id: Optional[str] = None,
        round_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        difficulty: DifficultyLevel = DifficultyLevel.MEDIUM,
        missing_competencies: Optional[list[str]] = None,
        metadata: Optional[dict[str, object]] = None,
    ) -> InterviewAIContext:
        """Retrieve existing context or initialize a fresh one for the canonical interview_id."""
        clean_id = self.resolve_interview_id(interview_id)
        if clean_id in self._sessions:
            return self._sessions[clean_id]

        context = InterviewAIContext(
            interview_id=clean_id,
            candidate_id=candidate_id or f"cand-{clean_id}",
            current_round_id=round_id or "technical",
            current_agent_id=(agent_id or "alex").strip().lower(),
            difficulty=difficulty,
            missing_competencies=list(missing_competencies) if missing_competencies is not None else [],
            metadata=dict(metadata or {}),
        )
        self._sessions[clean_id] = context
        logger.info(
            "interview_session_created",
            interview_id=clean_id,
            candidate_id=context.candidate_id,
            agent_id=context.current_agent_id,
        )
        return context

    def has(self, interview_id: str) -> bool:
        """Check if an interview session exists."""
        clean_id = self.resolve_interview_id(interview_id)
        return clean_id in self._sessions

    def clear(self, interview_id: Optional[str] = None) -> None:
        """Clear a single session or all sessions."""
        if interview_id:
            clean_id = self.resolve_interview_id(interview_id)
            self._sessions.pop(clean_id, None)
            self._locks.pop(clean_id, None)
            # Remove aliases pointing to this session
            self._aliases = {k: v for k, v in self._aliases.items() if v != clean_id}
        else:
            self._sessions.clear()
            self._aliases.clear()
            self._locks.clear()

    def list_session_ids(self) -> list[str]:
        """Return all active canonical session IDs."""
        return list(self._sessions.keys())


# Global default session store instance
interview_session_store = InterviewSessionStore()
