"""Intra AI Unified Agent Turn Context Package.

Exposes models, providers, and builders for composing CV background, JD requirements,
persistent Knowledge Graph candidate memory, and live interview state.
"""

from app.agent_context.builder import AgentTurnContextBuilder
from app.agent_context.models import (
    MAX_CONTEXT_EVIDENCE,
    MAX_CONTEXT_EXPERIENCES,
    MAX_CONTEXT_PROJECTS,
    MAX_CONTEXT_SKILLS,
    MAX_PROMPT_CHARS,
    MAX_QUESTION_HISTORY,
    AgentTurnContext,
    CandidateEducationItem,
    CandidateExperienceItem,
    CandidateProfileContext,
    CandidateProjectItem,
    JobContext,
)
from app.agent_context.providers import (
    CandidateProfileProvider,
    DefaultCandidateProfileProvider,
    DefaultJobContextProvider,
    JobContextProvider,
)

__all__ = [
    # Models
    "AgentTurnContext",
    "CandidateProfileContext",
    "CandidateExperienceItem",
    "CandidateEducationItem",
    "CandidateProjectItem",
    "JobContext",
    # Constants
    "MAX_PROMPT_CHARS",
    "MAX_CONTEXT_EVIDENCE",
    "MAX_CONTEXT_SKILLS",
    "MAX_CONTEXT_PROJECTS",
    "MAX_CONTEXT_EXPERIENCES",
    "MAX_QUESTION_HISTORY",
    # Providers
    "CandidateProfileProvider",
    "DefaultCandidateProfileProvider",
    "JobContextProvider",
    "DefaultJobContextProvider",
    # Builder
    "AgentTurnContextBuilder",
]
