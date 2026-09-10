from datetime import datetime
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class IntelligenceFinding(StrictModel):
    competency: str = Field(min_length=1, max_length=80)
    observation: str = Field(min_length=5, max_length=600)
    quote: str = Field(min_length=3, max_length=1000)
    score: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)


class EvidenceSignal(IntelligenceFinding):
    id: str
    event_id: str
    candidate_id: str
    session_id: str
    source_type: Literal["role_play", "group_discussion"]
    observed_at: datetime
    participant_id: str | None = None
    phase_id: str | None = None


class FeatureJSONClient(Protocol):
    async def generate_feature_json(self, purpose: str, *, messages: list[dict]) -> dict: ...
