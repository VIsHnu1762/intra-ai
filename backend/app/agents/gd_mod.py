"""GD Moderator agent profile and Agora Agent Studio mapping."""

from __future__ import annotations

from app.agents.models import AgentProfile, AgoraAgentMapping
from app.core.config import settings
from app.models.enums import ActionType, DifficultyLevel

GD_MOD_AGENT_ID = "gd_mod"
GD_MOD_DISPLAY_NAME = "GD Moderator"
GD_MOD_ROLE = "AI Group Discussion Moderator"

GD_MOD_PROFILE = AgentProfile(
    agent_id=GD_MOD_AGENT_ID,
    display_name=GD_MOD_DISPLAY_NAME,
    role=GD_MOD_ROLE,
    description=(
        "AI moderator that facilitates group discussions, ensures balanced participation, "
        "redirects off-topic content, and evaluates candidates' communication and reasoning skills."
    ),
    focal_competencies=[
        "communication",
        "critical_thinking",
        "teamwork",
        "leadership",
        "problem_solving",
    ],
    questioning_style="neutral and facilitative moderator",
    instructions="""You are an AI Group Discussion Moderator.
Your role is to facilitate a structured group discussion, ensuring all participants get a fair chance to speak.

Guidelines:
- Remain neutral and professional at all times.
- Encourage quieter participants to contribute.
- Gently redirect off-topic or hostile exchanges back to the topic.
- Introduce new angles when the discussion stalls.
- Warn participants when time is running low.
- Do not take sides or express personal opinions on the discussion topic.
""",
    min_difficulty=DifficultyLevel.EASY,
    max_difficulty=DifficultyLevel.HARD,
    allowed_actions=[ActionType.ASK_QUESTION, ActionType.COMPLETE],
)


def get_gd_mod_agora_mapping() -> AgoraAgentMapping:
    """Build the Agora Agent Studio runtime mapping for GD Moderator."""
    project_id = (
        getattr(settings, "AGORA_APP_ID", "")
        or "a71666df598e499992a0ee5499dc7dcf"
    )
    pipeline_id = (
        getattr(settings, "AGORA_GD_MOD_PIPELINE_ID", "")
        or "4c8d370abbb640d09a1a4d8a5c64322f"
    )
    return AgoraAgentMapping(
        project_id=project_id,
        pipeline_id=pipeline_id,
        agent_rtc_uid=998877,
        asr_vendor="deepgram",
        asr_model="nova-3",
        asr_language="en",
        llm_url=None,   # Uses Studio-managed LLM
        llm_vendor="openai",
        llm_model="intra-ai",
        tts_vendor="openai",
        tts_model="tts-1",
        tts_voice="alloy",
        tts_speed=1.0,
        turn_detection="default_vad",
        filler_words_enabled=True,
        filler_words_threshold_ms=1500,
    )
