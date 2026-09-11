"""Role Play agent profile and Agora Agent Studio mapping."""

from __future__ import annotations

from app.agents.models import AgentProfile, AgoraAgentMapping
from app.core.config import settings
from app.models.enums import ActionType, DifficultyLevel

ROLE_PLAY_AGENT_ID = "role_play"
ROLE_PLAY_DISPLAY_NAME = "Role Play AI"
ROLE_PLAY_ROLE = "AI Role Play Evaluator"

ROLE_PLAY_PROFILE = AgentProfile(
    agent_id=ROLE_PLAY_AGENT_ID,
    display_name=ROLE_PLAY_DISPLAY_NAME,
    role=ROLE_PLAY_ROLE,
    description=(
        "AI persona that participates in structured role-play scenarios to evaluate candidates' "
        "soft skills including negotiation, conflict resolution, customer handling, and situational judgment."
    ),
    focal_competencies=[
        "communication",
        "negotiation",
        "conflict_resolution",
        "empathy",
        "situational_judgment",
        "customer_handling",
    ],
    questioning_style="immersive role-play persona",
    instructions="""You are an AI participating in a structured role-play scenario.
Embody the persona defined in the scenario. React naturally to what the candidate says.

Guidelines:
- Stay in character at all times during the role-play.
- Respond realistically to the candidate's approach and tone.
- Escalate or de-escalate based on how the candidate handles the situation.
- Do not break character unless explicitly asked to end the session.
- Evaluate the candidate's communication, empathy, and problem-solving through the interaction.
""",
    min_difficulty=DifficultyLevel.EASY,
    max_difficulty=DifficultyLevel.EXPERT,
    allowed_actions=[ActionType.ASK_QUESTION, ActionType.COMPLETE],
)


def get_role_play_agora_mapping() -> AgoraAgentMapping:
    """Build the Agora Agent Studio runtime mapping for Role Play."""
    project_id = (
        getattr(settings, "AGORA_APP_ID", "")
        or "a71666df598e499992a0ee5499dc7dcf"
    )
    pipeline_id = (
        getattr(settings, "AGORA_ROLE_PLAY_PIPELINE_ID", "")
        or "e31086fedf71452e807948c0a59e4142"
    )
    return AgoraAgentMapping(
        project_id=project_id,
        pipeline_id=pipeline_id,
        agent_rtc_uid=888989,
        asr_vendor="deepgram",
        asr_model="nova-3",
        asr_language="en",
        llm_url=None,   # Uses Studio-managed LLM
        llm_vendor="openai",
        llm_model="intra-ai",
        tts_vendor="openai",
        tts_model="tts-1",
        tts_voice="shimmer",
        tts_speed=1.0,
        turn_detection="default_vad",
        filler_words_enabled=True,
        filler_words_threshold_ms=1500,
    )
