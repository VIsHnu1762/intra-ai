"""Intra AI Agent Registry — Central registry for logical interviewer agents and Agora mappings."""

from __future__ import annotations

from typing import Callable
import structlog

from app.agents.alex import ALEX_PROFILE, get_alex_agora_mapping
from app.agents.jordan import JORDAN_PROFILE, get_jordan_agora_mapping
from app.agents.models import AgentProfile, AgoraAgentMapping
from app.core.exceptions import AgentNotFoundError, AgoraConfigurationError

logger = structlog.stdlib.get_logger("intra_ai.agents.registry")

MappingType = AgoraAgentMapping | Callable[[], AgoraAgentMapping] | None


class AgentRegistry:
    """N-agent capable registry resolving logical agent IDs to profiles and Agora mappings."""

    def __init__(self, register_defaults: bool = True) -> None:
        self._agents: dict[str, AgentProfile] = {}
        self._agora_mappings: dict[str, MappingType] = {}
        if register_defaults:
            self._register_default_agents()

    def _register_default_agents(self) -> None:
        """Register default built-in agents (e.g. Alex, Jordan)."""
        self.register(
            profile=ALEX_PROFILE,
            agora_mapping=get_alex_agora_mapping,
        )
        self.register(
            profile=JORDAN_PROFILE,
            agora_mapping=get_jordan_agora_mapping,
        )

    def register(
        self,
        profile: AgentProfile,
        agora_mapping: MappingType = None,
    ) -> None:
        """Register a new logical agent profile and its optional Agora Agent Studio mapping.

        Allows adding N specialized agents (Alex, Jordan, Morgan, custom) without modifying
        orchestration or routing code.
        """
        agent_id = profile.agent_id.strip().lower()
        if not agent_id:
            raise ValueError("AgentProfile must have a non-empty agent_id")

        self._agents[agent_id] = profile
        self._agora_mappings[agent_id] = agora_mapping
        logger.info(
            "agent_registered",
            agent_id=agent_id,
            display_name=profile.display_name,
            has_agora_mapping=agora_mapping is not None,
        )

    def get_profile(self, agent_id: str) -> AgentProfile:
        """Retrieve the logical AgentProfile for the given agent_id.

        Raises:
            AgentNotFoundError: If the agent_id is not registered.
        """
        norm_id = agent_id.strip().lower()
        if norm_id not in self._agents:
            raise AgentNotFoundError(
                f"Interviewer agent '{agent_id}' not found in registry. "
                f"Available agents: {list(self._agents.keys())}"
            )
        return self._agents[norm_id]

    def get_agora_mapping(self, agent_id: str) -> AgoraAgentMapping:
        """Resolve the Agora Agent Studio runtime mapping for the given agent_id.

        Raises:
            AgentNotFoundError: If the agent_id is not registered.
            AgoraConfigurationError: If the agent has no Agora configuration or if required
                identifiers (project_id, pipeline_id) are missing/empty.
        """
        norm_id = agent_id.strip().lower()
        if norm_id not in self._agents:
            raise AgentNotFoundError(
                f"Interviewer agent '{agent_id}' not found in registry. "
                f"Available agents: {list(self._agents.keys())}"
            )

        raw_mapping = self._agora_mappings.get(norm_id)
        if raw_mapping is None:
            raise AgoraConfigurationError(
                f"Agent '{agent_id}' does not have a configured Agora Agent Studio mapping"
            )

        try:
            if callable(raw_mapping):
                mapping = raw_mapping()
            else:
                mapping = raw_mapping

            if not mapping.project_id or not mapping.project_id.strip():
                raise AgoraConfigurationError(
                    f"Agora project_id for agent '{agent_id}' is empty or invalid"
                )
            if not mapping.pipeline_id or not mapping.pipeline_id.strip():
                raise AgoraConfigurationError(
                    f"Agora pipeline_id for agent '{agent_id}' is empty or invalid"
                )

            return mapping
        except AgoraConfigurationError:
            raise
        except Exception as exc:
            raise AgoraConfigurationError(
                f"Failed to resolve Agora configuration for agent '{agent_id}': {exc}"
            ) from exc

    def get_agent(self, agent_id: str) -> tuple[AgentProfile, AgoraAgentMapping]:
        """Convenience method returning both profile and Agora runtime mapping."""
        return self.get_profile(agent_id), self.get_agora_mapping(agent_id)

    def has_agent(self, agent_id: str) -> bool:
        """Check if an agent is registered."""
        return agent_id.strip().lower() in self._agents

    def list_agents(self) -> list[AgentProfile]:
        """Return all registered agent profiles."""
        return list(self._agents.values())

    def list_agent_ids(self) -> list[str]:
        """Return all registered logical agent IDs."""
        return list(self._agents.keys())

    def reset(self) -> None:
        """Reset the registry to its default built-in state."""
        self._agents.clear()
        self._agora_mappings.clear()
        self._register_default_agents()


# Global default singleton instance
agent_registry = AgentRegistry()
