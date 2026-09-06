"""Agent Profile, Agora Mapping, and Canonical NextAction models for Intra AI."""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ActionType, DifficultyLevel


class NextAction(BaseModel):
    """Canonical NextAction contract for Intra AI interview orchestration.

    Action types are strictly:
    - ASK_QUESTION (includes standard progression and follow-up/probing questions)
    - SWITCH_AGENT (hands off to another specialized interviewer)
    - COMPLETE (concludes the interview session)

    Difficulty adjustments are represented as metadata, not separate action enums.
    """

    model_config = ConfigDict(extra="ignore")

    action: ActionType
    target_agent_id: str | None = Field(
        default=None,
        description="Logical agent ID (e.g. 'alex', 'jordan') targeted by this action.",
    )
    competency: str | None = Field(
        default=None,
        description="Focal competency evaluated in this step (e.g. 'system_design').",
    )
    difficulty: DifficultyLevel | None = Field(
        default=None,
        description="Difficulty level metadata for this question or transition.",
    )
    question_text: str | None = Field(
        default=None,
        description="Text of the question or prompt to be presented to the candidate.",
    )
    rationale: str | None = Field(
        default=None,
        description="Explainable rationale justifying why this action was selected.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional contextual parameters (e.g. handoff context, evidence references).",
    )


class AgentProfile(BaseModel):
    """Logical interviewer agent profile for Intra AI."""

    model_config = ConfigDict(extra="ignore")

    agent_id: str = Field(..., description="Unique logical identifier (e.g. 'alex', 'jordan').")
    display_name: str = Field(..., description="Human-readable persona display name.")
    role: str = Field(..., description="Persona title or organizational role.")
    description: str = Field(..., description="High-level description of persona responsibilities.")
    focal_competencies: list[str] = Field(
        default_factory=list,
        description="List of domain competencies evaluated by this agent.",
    )
    questioning_style: str = Field(
        ...,
        description="Summary of the agent's conversational style and interrogation approach.",
    )
    instructions: str = Field(
        ...,
        description="Detailed system persona instructions and behavioral constraints.",
    )
    min_difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.EASY,
        description="Minimum difficulty level handled by this agent.",
    )
    max_difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.EXPERT,
        description="Maximum difficulty level handled by this agent.",
    )
    allowed_actions: list[ActionType] = Field(
        default_factory=lambda: [
            ActionType.ASK_QUESTION,
            ActionType.SWITCH_AGENT,
            ActionType.COMPLETE,
        ],
        description="Canonical actions permitted for this agent.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extension metadata.",
    )

    @model_validator(mode="after")
    def validate_profile(self) -> "AgentProfile":
        if not self.agent_id or not self.agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        if not self.display_name or not self.display_name.strip():
            raise ValueError("display_name must be non-empty")
        return self


class AgoraAgentMapping(BaseModel):
    """Mapping between an Intra AI logical agent and its Agora Agent Studio runtime configuration."""

    model_config = ConfigDict(extra="ignore")

    project_id: str = Field(..., description="Agora Conversational AI project UUID.")
    pipeline_id: str = Field(..., description="Agora Agent Studio pipeline UUID.")
    agent_rtc_uid: int | str = Field(default=468707, description="Agent Studio default RTC UID.")
    asr_vendor: str = Field(default="deepgram", description="Automated Speech Recognition vendor.")
    asr_model: str = Field(default="nova-3", description="ASR model identifier.")
    asr_language: str = Field(default="en", description="ASR language code.")
    llm_url: str | None = Field(default=None, description="Custom LLM completions endpoint URL.")
    llm_vendor: str = Field(default="openai", description="Agent Studio default LLM vendor.")
    llm_model: str = Field(default="intra-ai", description="Agent Studio default LLM model.")
    greeting: str | None = Field(default=None, description="Default greeting message spoken when joining.")
    tts_vendor: str = Field(default="openai", description="Text-to-Speech vendor.")
    tts_model: str = Field(default="tts-1", description="TTS model identifier.")
    tts_voice: str = Field(default="echo", description="Synthesized voice persona name.")
    tts_speed: float = Field(default=1.0, description="TTS playback speech rate multiplier.")
    turn_detection: str = Field(default="default_vad", description="Turn detection / VAD mode.")
    vad_silence_duration_ms: int = Field(default=400, description="VAD silence duration threshold in ms.")
    vad_speech_threshold: float = Field(default=0.4, description="VAD speech probability threshold.")
    vad_prefix_padding_ms: int = Field(default=600, description="VAD prefix padding in ms.")
    vad_interrupt_duration_ms: int = Field(default=120, description="VAD interrupt duration in ms.")
    vad_speaking_interrupt_duration_ms: int = Field(default=120, description="VAD speaking interrupt duration in ms.")
    filler_words_enabled: bool = Field(default=True, description="Whether filler words are active.")
    filler_words_threshold_ms: int = Field(
        default=1500,
        description="Response latency wait threshold before emitting filler words (in ms).",
    )
    filler_phrases: list[str] = Field(
        default_factory=lambda: ["Please wait.", "Okay.", "Uh-huh."],
        description="Predefined filler word phrases.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional Agora runtime parameters.",
    )

    @model_validator(mode="after")
    def validate_mapping(self) -> "AgoraAgentMapping":
        if not self.project_id or not self.project_id.strip():
            raise ValueError("Agora project_id must be non-empty")
        if not self.pipeline_id or not self.pipeline_id.strip():
            raise ValueError("Agora pipeline_id must be non-empty")
        return self

    def to_agora_properties(
        self,
        system_prompt: str | None = None,
        greeting: str | None = None,
    ) -> dict[str, Any]:
        """Generate the complete Agora Agent Studio properties dictionary."""
        effective_greeting = (greeting or self.greeting or "").strip()
        llm_config: dict[str, Any] = {
            "vendor": self.llm_vendor,
            "params": {
                "model": self.llm_model,
            },
        }
        if self.llm_url:
            llm_config["url"] = self.llm_url

        if system_prompt:
            llm_config["system_messages"] = [
                {"role": "system", "content": system_prompt.strip()}
            ]
        if effective_greeting:
            llm_config["greeting_message"] = effective_greeting

        return {
            "pipeline_id": self.pipeline_id,
            "asr": {
                "vendor": self.asr_vendor,
                "params": {
                    "model": self.asr_model,
                    "language": self.asr_language,
                },
            },
            "llm": llm_config,
            "tts": {
                "vendor": self.tts_vendor,
                "params": {
                    "model": self.tts_model,
                    "voice": self.tts_voice,
                    "speed": self.tts_speed,
                },
            },
            "vad": {
                "mode": self.turn_detection,
                "silence_duration_ms": self.vad_silence_duration_ms,
                "speech_threshold": self.vad_speech_threshold,
                "prefix_padding_ms": self.vad_prefix_padding_ms,
                "interrupt_duration_ms": self.vad_interrupt_duration_ms,
                "speaking_interrupt_duration_ms": self.vad_speaking_interrupt_duration_ms,
            },
            "filler_words": {
                "enable": self.filler_words_enabled,
                "wait_time": self.filler_words_threshold_ms,
                "content": {
                    "static_config": {
                        "phrases": self.filler_phrases,
                    },
                },
            } if self.filler_words_enabled else {"enable": False},
        }

    def to_agora_join_payload(
        self,
        channel_name: str,
        user_uid: str | int = 0,
        agent_rtc_uid: str | int = 1001,
        agent_token: str | None = None,
        system_prompt: str | None = None,
        greeting: str | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate the complete Agora Conversational AI start/join REST payload."""
        import uuid

        payload: dict[str, Any] = {
            "request_id": request_id or str(uuid.uuid4()),
            "channel_name": str(channel_name),
            "user_uid": str(user_uid),
            "agent_rtc_uid": str(agent_rtc_uid),
            "properties": self.to_agora_properties(
                system_prompt=system_prompt,
                greeting=greeting,
            ),
        }
        if agent_token:
            payload["agent_token"] = agent_token
        return payload
