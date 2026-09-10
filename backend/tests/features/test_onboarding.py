import io
import zipfile
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, UploadFile
from starlette.datastructures import Headers
from app.candidate_onboarding.service import OnboardingService
from app.candidate_onboarding.routes import router, service
from app.core.deps import get_current_user, get_supabase
from app.core.exceptions import ConflictError, NotFoundError, ValidationError, register_exception_handlers
from app.integrations.document_text import extract_document
from app.integrations.aicredits_client import AICreditsClient, AICreditsError
from app.services.resume_service import ResumeService

MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT = "Candidate has five years of Python, PostgreSQL and FastAPI experience."


def docx(text=TEXT):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' + text + '</w:t></w:r></w:p></w:body></w:document>')
    return stream.getvalue()


def upload(content=None):
    return UploadFile(io.BytesIO(content or docx()), filename="resume.docx", headers=Headers({"content-type": MIME}))


def llm():
    return SimpleNamespace(generate_feature_json=AsyncMock(return_value={"skills": ["Python", "PostgreSQL"], "experience": [], "education": [], "projects": [], "certifications": []}))


def test_docx_extraction_and_binary_rejection():
    assert extract_document(docx(), "resume.docx", MIME) == (TEXT, "docx")
    for content, name, mime in [(b"not pdf", "x.pdf", "application/pdf"), (docx(), "x.exe", MIME),
                                (b"x" * (8*1024*1024+1), "x.pdf", "application/pdf"), (docx("tiny"), "x.docx", MIME)]:
        with pytest.raises(ValidationError): extract_document(content, name, mime)


def test_pdf_is_extracted_without_treating_binary_as_resume():
    # Minimal one-page PDF, built locally without a rendering dependency.
    stream = b"BT /F1 12 Tf 40 700 Td (Candidate Python PostgreSQL FastAPI experience for five years.) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    data = b"%PDF-1.4\n"; offsets = [0]
    for i, obj in enumerate(objects, 1): offsets.append(len(data)); data += str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n"
    xref = len(data); data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    assert "Python" in extract_document(data, "resume.pdf", "application/pdf")[0]


@pytest.mark.asyncio
async def test_profile_parser_uses_named_aicredits_slot_and_local_fallback():
    provider = llm()
    result, source = await ResumeService.parse_profile_text(TEXT, client=provider)
    assert source == "aicredits" and result.skills == ["Python", "PostgreSQL"]
    assert provider.generate_feature_json.call_args.args == ("resume",)
    provider.generate_feature_json.side_effect = AICreditsError("rate_limited")
    result, source = await ResumeService.parse_profile_text(TEXT, client=provider)
    assert source == "local_fallback" and "python" in result.skills


@pytest.mark.asyncio
async def test_real_upload_restart_replace_replay_and_candidate_isolation(feature_sb, feature_actors):
    _, candidate, peer = feature_actors
    provider = llm(); svc = OnboardingService(feature_sb, llm=provider)
    assert (await svc.status(candidate)).needs_onboarding
    request = str(uuid4())
    first = await svc.upload(candidate, upload(), 0, request)
    assert first.version == 1
    recovered = OnboardingService(feature_sb, llm=provider)
    assert (await recovered.status(candidate)).current.id == first.id
    replay = await recovered.upload(candidate, upload(), 0, request)
    assert replay.id == first.id and provider.generate_feature_json.await_count == 1
    with pytest.raises(ConflictError): await svc.upload(candidate, upload(docx(TEXT + " More skills.")), 0, request)
    second = await svc.upload(candidate, upload(), 1, str(uuid4()))
    assert second.version == 2 and (await svc.status(candidate)).current.id == second.id
    assert (await svc.download(candidate, first.id))[0] == docx()
    with pytest.raises(NotFoundError): await svc.download(peer, first.id)


@pytest.mark.asyncio
async def test_real_api_uses_persisted_identity_and_hides_storage(feature_sb, feature_actors):
    recruiter, candidate, peer = feature_actors
    app = FastAPI(); app.include_router(router, prefix="/api/v1"); register_exception_handlers(app)
    claims = {"sub": candidate.user_id, "role": "admin"}
    app.dependency_overrides[get_current_user] = lambda: claims
    app.dependency_overrides[get_supabase] = lambda: feature_sb
    app.dependency_overrides[service] = lambda: OnboardingService(feature_sb, llm=llm())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/candidate/onboarding/resumes", files={"file": ("resume.docx", docx(), MIME)}, data={"expected_revision": "0", "request_id": str(uuid4())})
        assert response.status_code == 201, response.text
        assert not {"storage_key", "raw_text", "user_id", "content_sha256"} & response.json().keys()
        claims["sub"] = peer.user_id
        assert (await client.get(f'/api/v1/candidate/onboarding/resumes/{response.json()["id"]}/download')).status_code == 404
        claims["sub"] = recruiter.user_id
        assert (await client.get("/api/v1/candidate/onboarding/status")).status_code == 403


@pytest.mark.asyncio
async def test_real_concurrent_upload_has_one_current_version(feature_sb, feature_actors):
    import asyncio
    _, candidate, _ = feature_actors
    svc = OnboardingService(feature_sb, llm=llm())
    results = await asyncio.gather(*(svc.upload(candidate, upload(), 0, str(uuid4())) for _ in range(2)), return_exceptions=True)
    assert sum(not isinstance(result, Exception) for result in results) == 1
    assert any(isinstance(result, ConflictError) for result in results)
    assert len(await svc.repo.versions(candidate.user_id)) == 1


@pytest.mark.asyncio
async def test_unknown_commit_result_must_not_delete_possibly_committed_object(monkeypatch):
    from app.integrations.feature_db import DependencyUnavailable
    from tests.features.conftest import MemoryStorage
    sb = SimpleNamespace(storage=MemoryStorage())
    svc = OnboardingService(sb, llm=llm())
    svc.repo.versions = AsyncMock(return_value=[])
    svc.repo.save = AsyncMock(side_effect=DependencyUnavailable())
    actor = SimpleNamespace(role="candidate", user_id="candidate")
    with pytest.raises(DependencyUnavailable): await svc.upload(actor, upload(), 0, str(uuid4()))
    assert len(sb.storage.objects) == 1
