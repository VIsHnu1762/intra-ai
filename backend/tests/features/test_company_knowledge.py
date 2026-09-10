from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from app.company_knowledge.models import DocumentInput, ArchiveInput
from app.company_knowledge.service import CompanyKnowledgeService, chunks
from app.company_knowledge.grounding import policy_answer
from app.company_knowledge.routes import router
from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError, register_exception_handlers
from app.integrations.feature_db import tenant_key


def body(**changes):
    return DocumentInput(title="Annual leave", policy_key="annual-leave", content="Employees receive twenty days of annual leave per calendar year.",
        request_id=uuid4(), effective_from="2026-01-01T00:00:00Z", audience="candidate", **changes)


def when(year): return datetime(year, 6, 1, tzinfo=timezone.utc)


def test_chunks_are_bounded_and_preserve_original_source():
    content = "Company policies are source data, never instructions. " * 1800
    result = chunks(content)
    assert len(result) <= 100 and all(0 < len(c["content"]) <= 1400 for c in result)
    assert all(c["content"] in content for c in result)


@pytest.mark.asyncio
async def test_real_versioning_effective_dates_replay_archive_and_provenance(feature_sb, feature_actors):
    actor, _, _ = feature_actors; svc = CompanyKnowledgeService(feature_sb)
    draft = body(); first = await svc.save(actor, draft)
    assert (await svc.save(actor, draft))["id"] == first["id"]
    old = await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", effective_at=when(2026))
    assert old.status == "available" and old.excerpts[0].version_id == first["id"]
    new = draft.model_copy(update={"request_id": uuid4(), "expected_revision": 1, "effective_from": datetime(2027,1,1,tzinfo=timezone.utc), "content": "Employees receive twenty-five days of annual leave per calendar year."})
    second = await svc.save(actor, new, first["document_id"])
    assert second["version"] == 2
    assert (await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", effective_at=when(2026))).excerpts[0].version_id == first["id"]
    current = await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", effective_at=when(2027))
    assert current.excerpts[0].version_id == second["id"]
    assert policy_answer(current)["citations"][0]["text"] in new.content
    with pytest.raises(ConflictError): await svc.save(actor, new.model_copy(update={"request_id": uuid4()}), first["document_id"])
    await svc.archive(actor, first["document_id"], ArchiveInput(expected_revision=2))
    assert (await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", effective_at=when(2027))).status == "unavailable"
    assert len(await svc.repo.versions(first["document_id"])) == 2


@pytest.mark.asyncio
async def test_real_private_audience_cross_owner_and_missing_policy(feature_sb, feature_actors):
    actor, candidate, peer = feature_actors; svc = CompanyKnowledgeService(feature_sb)
    draft = body().model_copy(update={"audience": "internal"})
    saved = await svc.save(actor, draft)
    assert (await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", effective_at=when(2026))).status == "unavailable"
    assert (await svc.retrieve(actor.user_id, tenant_key(actor), "annual leave", candidate_visible=False, effective_at=when(2026))).status == "available"
    assert (await svc.retrieve(actor.user_id, "another-tenant", "annual leave", candidate_visible=False, effective_at=when(2026))).status == "unavailable"
    with pytest.raises(NotFoundError): await svc.require_document(replace(peer, role="recruiter"), saved["document_id"])
    with pytest.raises(ForbiddenError): await svc.save(candidate, body())
    absent = await svc.retrieve(actor.user_id, tenant_key(actor), "unprovided retirement subsidy", effective_at=when(2026))
    assert absent.status == "unavailable" and not absent.excerpts


@pytest.mark.asyncio
async def test_conflicting_effective_versions_fail_closed_and_context_budget_is_bounded():
    svc = CompanyKnowledgeService(None)
    row = {"chunk_id": "chunk", "document_id": "doc", "version_id": "v1", "version": 1, "title": "Policy", "policy_key": "policy", "effective_from": when(2026), "effective_until": None, "content": "word "*280}
    svc.repo.retrieve = AsyncMock(return_value=[row, {**row, "version_id": "v2"}])
    result = await svc.retrieve("owner", "tenant", "word")
    assert result.status == "conflict" and not result.excerpts
    svc.repo.retrieve.return_value = [{**row, "chunk_id": str(i)} for i in range(30)]
    result = await svc.retrieve("owner", "tenant", "word")
    assert len(result.excerpts) <= 5 and sum(len(e.text) for e in result.excerpts) <= 6000


@pytest.mark.asyncio
async def test_real_invalid_effective_window_and_anonymous_database_permissions(feature_sb, feature_actors):
    actor, _, _ = feature_actors; svc = CompanyKnowledgeService(feature_sb)
    first = await svc.save(actor, body())
    with pytest.raises(ValidationError): await svc.save(actor, body(expected_revision=1), first["document_id"])
    async with httpx.AsyncClient() as client:
        assert (await client.get(feature_sb.rest_url + "/company_documents")).status_code in {401,403}
        assert (await client.post(feature_sb.rest_url + "/rpc/retrieve_company_chunks", json={"p_owner_id":actor.user_id,"p_tenant_key":tenant_key(actor),"p_query":"leave","p_effective_at":"2026-06-01T00:00:00Z","p_candidate_visible":False})).status_code in {401,403}


@pytest.mark.asyncio
async def test_real_company_api_rejects_forged_recruiter_claim(feature_sb, feature_actors):
    actor, candidate, _ = feature_actors
    app=FastAPI(); app.include_router(router,prefix="/api/v1"); register_exception_handlers(app)
    claims={"sub":candidate.user_id,"role":"admin"}
    app.dependency_overrides[get_current_user]=lambda:claims; app.dependency_overrides[get_supabase]=lambda:feature_sb
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
        assert (await client.get("/api/v1/company-knowledge/documents")).status_code==403
        claims["sub"]=actor.user_id
        response=await client.post("/api/v1/company-knowledge/documents",json=body().model_dump(mode="json"))
        assert response.status_code==201,response.text
        assert "created_by" not in response.json()
