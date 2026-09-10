"""Opt-in context enrichment with no dependency on Standard Interview internals."""
from typing import Protocol
from app.company_knowledge.models import GroundedContext
from app.company_knowledge.service import CompanyKnowledgeService


class PolicyContextEnricher(Protocol):
    async def enrich(self, owner_id: str, tenant_key: str, query: str) -> GroundedContext: ...


class CompanyPolicyEnricher:
    def __init__(self, sb): self.service = CompanyKnowledgeService(sb)

    async def enrich(self, owner_id: str, tenant_key: str, query: str) -> GroundedContext:
        return await self.service.retrieve(owner_id, tenant_key, query, candidate_visible=True)


def policy_answer(context: GroundedContext) -> dict:
    """Extractive output: policy wording can never come from model knowledge."""
    return {"status": context.status, "message": context.message,
            "citations": [excerpt.model_dump(mode="json") for excerpt in context.excerpts]}
