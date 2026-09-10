from datetime import datetime, timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=160)
    policy_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    content: str = Field(min_length=30, max_length=100_000)
    effective_from: AwareDatetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_until: AwareDatetime | None = None
    audience: Literal["candidate", "internal"] = "internal"
    expected_revision: int = Field(default=0, ge=0)
    request_id: UUID

    @model_validator(mode="after")
    def window(self):
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValueError("Effective end must be later than the start")
        return self


class ArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    archived: bool = True


class RetrievalInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=2, max_length=300)
    effective_at: AwareDatetime | None = None


class PolicyExcerpt(BaseModel):
    chunk_id: str
    document_id: str
    version_id: str
    version: int
    title: str
    policy_key: str
    effective_from: datetime
    effective_until: datetime | None = None
    text: str


class GroundedContext(BaseModel):
    source: Literal["company_policy"] = "company_policy"
    status: Literal["available", "unavailable", "conflict"]
    message: str
    effective_at: datetime
    excerpts: list[PolicyExcerpt] = Field(default_factory=list)


class DocumentView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    policy_key: str
    revision: int
    archived_at: datetime | None = None
    created_at: datetime


class VersionView(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    document_id: str
    version: int
    title: str
    content: str
    audience: str
    effective_from: datetime
    effective_until: datetime | None = None
    created_at: datetime
