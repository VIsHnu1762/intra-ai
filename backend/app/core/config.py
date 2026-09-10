from typing import Literal, Optional

from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings validated at startup via Pydantic v2."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────
    APP_ENV: str = "development"
    DEBUG: bool = False

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _parse_debug_flag(cls, value: object) -> object:
        """Accept common deployment labels in addition to boolean strings.

        Some process managers export ``DEBUG=release`` when selecting a release
        profile. Treat that label as the safe production value instead of
        failing application startup during settings import.
        """
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"release", "production", "prod", "false", "0", "off", "no"}:
                return False
            if normalized in {"development", "dev", "true", "1", "on", "yes"}:
                return True
        return value

    # ── Supabase / Postgres ──────────────────────────────
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    DATABASE_URL: str
    SUPABASE_STORAGE_BUCKET: str = "resumes"

    # ── OpenAI ───────────────────────────────────────────
    OPENAI_API_KEY: str

    # Explicit AICredits slots: Nano for M1, Flash-Lite for Meta-Orchestrator.
    # Report helpers may reuse each slot; no Groq/model/key fallback is allowed.
    AICREDITS_API_KEY_GPT5_NANO: str = Field(default="", repr=False)
    AICREDITS_API_KEY_GEMINI_FLASH_LITE: str = Field(default="", repr=False)
    AICREDITS_GPT5_NANO_MODEL: str = "openai/gpt-5-nano"
    AICREDITS_GEMINI_FLASH_LITE_MODEL: str = "google/gemini-2.5-flash-lite"
    AICREDITS_M1_MODEL: str = ""
    AICREDITS_ORCHESTRATOR_MODEL: str = ""
    AICREDITS_BASE_URL: str = "https://api.aicredits.in/v1"
    AICREDITS_TIMEOUT_SECONDS: float = Field(default=60.0, ge=5, le=180)
    AICREDITS_REALTIME_TIMEOUT_SECONDS: float = Field(default=30.0, ge=5, le=60)
    AICREDITS_M1_REASONING_EFFORT: Literal["minimal", "low", "medium", "high"] = "minimal"

    # Independent feature slots, using the existing AICredits Flash-Lite key.
    AICREDITS_RESUME_MODEL: str = ""
    AICREDITS_ROLE_PLAY_MODEL: str = ""
    AICREDITS_GD_MODEL: str = ""
    AICREDITS_COMPANY_MODEL: str = ""
    CANDIDATE_ONBOARDING_ENABLED: bool = True
    COMPANY_KNOWLEDGE_ENABLED: bool = True
    ROLE_PLAY_ENABLED: bool = True
    GROUP_DISCUSSION_ENABLED: bool = True
    GD_INVITATION_SECRET: str = Field(default="", repr=False)

    @field_validator(
        "AICREDITS_GPT5_NANO_MODEL", "AICREDITS_GEMINI_FLASH_LITE_MODEL",
        "AICREDITS_BASE_URL", "AICREDITS_TIMEOUT_SECONDS", "AICREDITS_REALTIME_TIMEOUT_SECONDS",
        "AICREDITS_M1_REASONING_EFFORT", mode="before",
    )
    @classmethod
    def _aicredits_blank_defaults(cls, value: object, info: ValidationInfo) -> object:
        # The example env intentionally leaves these optional overrides empty.
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value

    # ── Redis ────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"

    # ── AWS S3 ───────────────────────────────────────────
    AWS_S3_BUCKET: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    AWS_CLOUDFRONT_DOMAIN: str = ""

    # ── Resend ───────────────────────────────────────────
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = ""

    # ── JWT ──────────────────────────────────────────────
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60

    # ── URLs ─────────────────────────────────────────────
    API_BASE_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"

    # ── Optional integrations ────────────────────────────
    DEEPGRAM_API_KEY: Optional[str] = None

    # ── Intra AI Intelligence ────────────────────────────
    M1_PROVIDER: str = "mock"
    ORCHESTRATOR_PROVIDER: Literal["groq", "aicredits"] = "groq"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODEL: str = "gpt-oss:20b"
    OLLAMA_BASE_URL: str = "https://ollama.com/v1"
    OLLAMA_TIMEOUT_SECONDS: float = 45.0
    GROQ_API_KEY: str = ""
    GROQ_M1_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-20b"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TIMEOUT_SECONDS: float = 20.0
    GROQ_ORCHESTRATOR_API_KEY: str = ""
    GROQ_ORCHESTRATOR_MODEL: str = "openai/gpt-oss-20b"
    GROQ_ORCHESTRATOR_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_ORCHESTRATOR_TIMEOUT_SECONDS: float = 20.0

    # ── Agora Agent Studio ───────────────────────────────
    AGORA_APP_ID: str = ""
    AGORA_APP_CERTIFICATE: str = ""
    AGORA_ALEX_PROJECT_ID: str = "acbcfc97ea094e3681d46fe8da21e4d1"
    # Optional common Studio base with the Custom LLM node configured.
    # Persona identity, greeting, and voice remain runtime overrides.
    AGORA_CUSTOM_LLM_PIPELINE_ID: str = ""
    AGORA_ALEX_PIPELINE_ID: str = "eb714d82ec524f14981e5b5f5108cbd1"
    AGORA_JORDAN_PROJECT_ID: str = "acbcfc97ea094e3681d46fe8da21e4d1"
    AGORA_JORDAN_PIPELINE_ID: str = "642bb4345fa244099a78a50cede2d7d3"
    AGORA_CUSTOMER_ID: str = ""
    AGORA_CUSTOMER_SECRET: str = ""
    AGORA_REST_API_KEY: str = ""
    AGORA_REST_API_SECRET: str = ""
    CUSTOM_LLM_URL: str = ""
    # Credential forwarded by Agora as `Authorization: Bearer ...` when it
    # calls the OpenAI-compatible Custom LLM endpoint. Keep this separate from
    # the Groq provider key: Agora authenticates the callback service, while
    # the adapter uses Groq internally for M1 and orchestration.
    CUSTOM_LLM_API_KEY: str = ""

    # Separate Studio project for practice and recruiter assistance. Never
    # fall back to the official interview project when these are missing.
    AGORA_TRAINING_HR_APP_ID: str = ""
    AGORA_TRAINING_HR_APP_CERTIFICATE: str = ""
    AGORA_TRAINING_HR_API_TOKEN: str = ""
    AGORA_TAYLOR_AGENT_ID: str = ""
    AGORA_TAYLOR_AGENT_RTC_UID: str = ""
    AGORA_MORGAN_AGENT_ID: str = ""
    AGORA_MORGAN_AGENT_RTC_UID: str = ""
    AGORA_MORGAN_LLM_MODE: Literal["studio", "managed"] = "studio"
    AGORA_MORGAN_MANAGED_MODEL: Literal["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-nano", "gpt-5-mini"] = "gpt-4.1-mini"
    AGORA_TAYLOR_LLM_MODE: Literal["studio", "managed"] = "managed"
    AGORA_TAYLOR_MANAGED_MODEL: Literal["gpt-4o-mini", "gpt-4.1-mini", "gpt-5-nano", "gpt-5-mini"] = "gpt-4.1-mini"
    VOICE_ASSISTANT_PUBLIC_URL: str = ""
    VOICE_ASSISTANT_SESSION_SECONDS: int = 1800
    VOICE_ASSISTANT_IDLE_SECONDS: int = 90
    # Morgan's external connectors are accessed through the controlled backend
    # bridge, never forwarded to the browser or the native agent directly.
    MORGAN_COMPOSIO_MCP_URL: str = ""
    MORGAN_COMPOSIO_API_KEY: str = ""
    MORGAN_COMPOSIO_OWNER_USER_ID: str = ""

    # ── Neo4j AuraDB (Knowledge Graph) ───────────────────
    NEO4J_URI: str = ""
    NEO4J_USERNAME: str = ""
    NEO4J_PASSWORD: str = ""
    NEO4J_DATABASE: str = "neo4j"

    # Agora NCS signature key; distinct from Custom LLM bearer credentials.
    AGORA_NOTIFICATION_SECRET: str = Field(default="", repr=False)


settings = Settings()  # type: ignore[call-arg]
