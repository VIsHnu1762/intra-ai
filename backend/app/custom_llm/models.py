"""OpenAI-compatible Chat Completions models and internal InterviewTurn for Custom LLM Adapter."""

from __future__ import annotations

import time
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.interview_context.models import InterviewAIContext


# ── Chat Completions Request Schemas ─────────────────────────────────────


class ChatMessage(BaseModel):
    """Standard Chat Completion message (role + content)."""

    model_config = ConfigDict(extra="ignore")

    role: str = Field(..., description="Author role (system, user, assistant, function, tool).")
    content: str | None = Field(default="", description="Textual content of the message.")
    name: str | None = Field(default=None, description="Optional author name.")
    turn_id: int | str | None = None
    timestamp: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        valid_roles = {"system", "user", "assistant", "function", "tool"}
        norm = v.strip().lower()
        if norm not in valid_roles:
            raise ValueError(f"Invalid message role '{v}'. Allowed roles: {valid_roles}")
        return norm


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible Chat Completions request payload sent by Agora or client."""

    model_config = ConfigDict(extra="allow")

    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="List of messages comprising the conversation history.",
    )
    model: str = Field(default="intra-ai", description="Requested model identifier.")
    stream: bool = Field(default=True, description="Whether to stream chunks via SSE.")
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    top_p: float | None = Field(default=None, ge=0.0, le=1.0)
    user: str | None = Field(default=None, description="Optional end-user/session identifier.")
    call_id: str | None = Field(default=None, description="Agora call/session identifier.")
    agent_uuid: str | None = Field(default=None, description="Agora agent instance UUID.")
    channel: str | None = Field(default=None, description="Agora RTC channel name.")
    frequency_penalty: float | None = None
    presence_penalty: float | None = None

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: list[ChatMessage]) -> list[ChatMessage]:
        if not v:
            raise ValueError("messages list must contain at least one message")
        return v



# ── Streaming Chunk Schemas (SSE) ────────────────────────────────────────


class ChatCompletionResponseDelta(BaseModel):
    """Delta payload inside a streaming choice chunk."""

    model_config = ConfigDict(extra="ignore")

    role: str | None = None
    content: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    """Choice chunk inside an SSE chat completion packet."""

    model_config = ConfigDict(extra="ignore")

    index: int = 0
    delta: ChatCompletionResponseDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    """Top-level OpenAI-compatible streaming packet."""

    model_config = ConfigDict(extra="ignore")

    id: str
    object: str = "chat.completion.chunk"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "intra-ai"
    choices: list[ChatCompletionChunkChoice]


# ── Non-Streaming Response Schemas ───────────────────────────────────────


class ChatCompletionResponseMessage(BaseModel):
    """Assistant message payload in a non-streaming completion."""

    model_config = ConfigDict(extra="ignore")

    role: str = "assistant"
    content: str


class ChatCompletionChoice(BaseModel):
    """Choice item in a non-streaming completion response."""

    model_config = ConfigDict(extra="ignore")

    index: int = 0
    message: ChatCompletionResponseMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    """Token usage counters (standard OpenAI telemetry)."""

    model_config = ConfigDict(extra="ignore")

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible non-streaming chat completion response."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(default_factory=lambda: f"chatcmpl-{uuid.uuid4().hex[:12]}")
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str = "intra-ai"
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)


# ── Internal Turn Representation ─────────────────────────────────────────


class InterviewTurn(BaseModel):
    """Internal representation of an interview turn passed to the adapter layer.

    Decouples the external OpenAI wire protocol from internal Intra AI systems.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    turn_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    messages: list[ChatMessage]
    latest_user_message: str = ""
    session_id: str | None = None
    channel_name: str | None = None
    model: str = "intra-ai"
    stream: bool = True
    context: InterviewAIContext | None = None
    raw_headers: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
