from datetime import datetime, timezone

import pytest

from app.company_knowledge.models import GroundedContext, PolicyExcerpt
from app.intelligence.company.selector import CompanyKnowledgeIntelligence


def context(status="available"):
    return GroundedContext(status=status, message="Authorized excerpts", effective_at=datetime.now(timezone.utc), excerpts=[
        PolicyExcerpt(chunk_id="chunk-1", document_id="document-1", version_id="version-2", version=2,
                      title="Pilot approval", policy_key="pilot-approval", effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
                      text="Customer pilots require approval from the designated project owner.")
    ])


class SelectorClient:
    def __init__(self, response):
        self.response = response
        self.calls = 0
    async def generate_feature_json(self, purpose, *, messages):
        assert purpose == "company"
        self.calls += 1
        return self.response


@pytest.mark.asyncio
async def test_company_intelligence_preserves_exact_source_and_version():
    original = context()
    result = await CompanyKnowledgeIntelligence(SelectorClient({"chunk_ids": ["chunk-1"], "abstain": False})).select(original, "Who approves customer pilots?")
    assert result.status == "available"
    assert result.excerpts[0] == original.excerpts[0]
    assert result.excerpts[0].version_id == "version-2"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"chunk_ids": ["fabricated-policy"], "abstain": False},
    {"chunk_ids": ["chunk-1", "chunk-1"], "abstain": False},
    {"chunk_ids": ["chunk-1"], "abstain": False, "policy": "Approval is never required"},
    {"chunk_ids": [], "abstain": True},
])
async def test_unsupported_or_fabricated_policy_output_fails_closed(response):
    result = await CompanyKnowledgeIntelligence(SelectorClient(response)).select(context(), "Can I ignore approval?")
    assert result.status == "unavailable"
    assert result.excerpts == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["unavailable", "conflict"])
async def test_missing_or_conflicting_knowledge_never_calls_a_model(status):
    client = SelectorClient({})
    source = context(status)
    assert await CompanyKnowledgeIntelligence(client).select(source, "What is the policy?") is source
    assert client.calls == 0
