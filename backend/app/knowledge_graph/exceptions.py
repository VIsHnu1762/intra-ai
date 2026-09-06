"""Exceptions for Intra AI Knowledge Graph operations and domain validation."""

from __future__ import annotations

from typing import Any, Optional

from app.core.exceptions import AppError


class KnowledgeGraphError(AppError):
    """Base exception for Knowledge Graph operations."""

    code = "KNOWLEDGE_GRAPH_ERROR"
    status_code = 500
    message = "An error occurred in the Knowledge Graph"

    def __init__(
        self,
        message: Optional[str] = None,
        code: Optional[str] = None,
        details: Optional[Any] = None,
    ) -> None:
        if code:
            self.code = code
        super().__init__(
            message=message or self.message,
            details=details,
        )


class EntityValidationError(KnowledgeGraphError):
    """Raised when entity data fails domain validation rules."""

    code = "KG_ENTITY_VALIDATION_ERROR"
    status_code = 422
    message = "Knowledge Graph entity validation failed"


class RelationshipValidationError(KnowledgeGraphError):
    """Raised when relationship type or endpoints are invalid."""

    code = "KG_RELATIONSHIP_VALIDATION_ERROR"
    status_code = 422
    message = "Knowledge Graph relationship validation failed"


class EntityNotFoundError(KnowledgeGraphError):
    """Raised when a requested entity does not exist in the graph."""

    code = "KG_ENTITY_NOT_FOUND"
    status_code = 404
    message = "Knowledge Graph entity not found"


class Neo4jConfigurationError(KnowledgeGraphError):
    """Raised when Neo4j credentials or configuration are missing or invalid."""

    code = "NEO4J_CONFIGURATION_ERROR"
    status_code = 500
    message = "Neo4j configuration is missing or incomplete"


class Neo4jConnectionError(KnowledgeGraphError):
    """Raised when connecting or querying Neo4j fails."""

    code = "NEO4J_CONNECTION_ERROR"
    status_code = 503
    message = "Failed to connect to Neo4j AuraDB"
