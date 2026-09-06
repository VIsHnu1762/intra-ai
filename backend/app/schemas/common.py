"""Common schemas: pagination, messages, errors."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PaginationParams(BaseModel):
    """Query dependency for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    per_page: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page


class MessageResponse(BaseModel):
    """Generic success message."""

    model_config = ConfigDict(from_attributes=True)

    message: str


class ErrorResponse(BaseModel):
    """Structured error response."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    message: str
    details: Any = None
