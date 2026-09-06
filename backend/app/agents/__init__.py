"""Intra AI Agent Registry and Agora Agent Studio mapping package."""

from app.agents.alex import (
    ALEX_AGENT_ID,
    ALEX_DESCRIPTION,
    ALEX_DISPLAY_NAME,
    ALEX_FOCAL_COMPETENCIES,
    ALEX_INSTRUCTIONS,
    ALEX_PROFILE,
    ALEX_QUESTIONING_STYLE,
    ALEX_ROLE,
    get_alex_agora_mapping,
)
from app.agents.jordan import (
    JORDAN_AGENT_ID,
    JORDAN_DISPLAY_NAME,
    JORDAN_PROFILE,
    JORDAN_ROLE,
    get_jordan_agora_mapping,
)
from app.agents.models import (
    ActionType,
    AgentProfile,
    AgoraAgentMapping,
    NextAction,
)
from app.agents.registry import AgentRegistry, agent_registry

__all__ = [
    "ALEX_AGENT_ID",
    "ALEX_DESCRIPTION",
    "ALEX_DISPLAY_NAME",
    "ALEX_FOCAL_COMPETENCIES",
    "ALEX_INSTRUCTIONS",
    "ALEX_PROFILE",
    "ALEX_QUESTIONING_STYLE",
    "ALEX_ROLE",
    "ActionType",
    "AgentProfile",
    "AgentRegistry",
    "AgoraAgentMapping",
    "JORDAN_AGENT_ID",
    "JORDAN_DISPLAY_NAME",
    "JORDAN_PROFILE",
    "JORDAN_ROLE",
    "NextAction",
    "agent_registry",
    "get_alex_agora_mapping",
    "get_jordan_agora_mapping",
]
