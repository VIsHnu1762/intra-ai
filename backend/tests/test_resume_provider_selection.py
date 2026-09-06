"""Resume parsing respects paid-provider selection; no model/network calls."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.config import settings
from app.integrations.aicredits_client import AICreditsError
from app.services.resume_service import ResumeService


@pytest.fixture
def parser(monkeypatch):
    aicredits = AsyncMock(return_value={"skills": ["Python"], "experience": [{"company": "Example", "role": "Developer"}],
        "education": [{"institution": "Example College", "degree": "BSc", "year": "2025"}],
        "projects": [{"name": "Payment ledger", "description": "Idempotent processing", "technologies": ["PostgreSQL"]}], "certifications": []})
    groq = AsyncMock(side_effect=AssertionError("Groq must not run unless explicitly selected"))
    monkeypatch.setattr("app.integrations.aicredits_client.generate_intelligence", aicredits)
    monkeypatch.setattr("app.integrations.groq_client.call_groq", groq)
    repo = SimpleNamespace(update_status=AsyncMock())
    return ResumeService(repo, Mock()), aicredits, groq


@pytest.mark.asyncio
async def test_aicredits_resume_retains_structured_fields_and_uses_m1_slot(parser, monkeypatch):
    service, aicredits, groq = parser
    monkeypatch.setattr(settings, "M1_PROVIDER", "aicredits")
    text = "Example Developer. Python and PostgreSQL. " + "x" * 16000
    result = await service._parse_structured_resume(text, "application-owned")
    aicredits.assert_awaited_once()
    args, kwargs = aicredits.call_args
    assert args == ("m1",) and kwargs["context_id"] == "application-owned"
    assert kwargs["messages"][1] == {"role": "user", "content": text[:16000]}
    assert "education" in kwargs["messages"][0]["content"] and "projects" in kwargs["messages"][0]["content"]
    assert result["experience"][0]["company"] == "Example"
    assert result["projects"][0]["name"] == "Payment ledger"
    groq.assert_not_awaited()


@pytest.mark.asyncio
async def test_explicit_groq_keeps_its_existing_model_and_key_contract(parser, monkeypatch):
    service, aicredits, groq = parser
    monkeypatch.setattr(settings, "M1_PROVIDER", "groq")
    monkeypatch.setattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setattr(settings, "GROQ_M1_API_KEY", "fixture-groq-key")
    groq.side_effect = None
    groq.return_value = {"skills": ["Python"]}
    assert await service._parse_structured_resume("Python", "application-owned") == {"skills": ["Python"]}
    assert groq.call_args.kwargs["model"] == "openai/gpt-oss-20b"
    assert groq.call_args.kwargs["api_key"] == "fixture-groq-key"
    aicredits.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["timeout", "rate_limited", "configuration_missing"])
async def test_aicredits_failure_uses_local_extraction_without_provider_fallback(parser, monkeypatch, code):
    service, aicredits, groq = parser
    monkeypatch.setattr(settings, "M1_PROVIDER", "aicredits")
    aicredits.side_effect = AICreditsError(code)
    result = await service._parse_structured_resume("Python and PostgreSQL developer", "application-owned")
    assert result == {"skills": ["python", "postgresql"], "experience": [], "education": [], "certifications": [], "projects": []}
    aicredits.assert_awaited_once()
    groq.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["mock", "unknown"])
async def test_non_groq_selection_never_implicitly_calls_groq(parser, monkeypatch, provider):
    service, aicredits, groq = parser
    monkeypatch.setattr(settings, "M1_PROVIDER", provider)
    result = await service._parse_structured_resume("Python developer", "application-owned")
    assert result["skills"] == ["python"]
    aicredits.assert_not_awaited()
    groq.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_flow_passes_rich_aicredits_parse_to_existing_persistence(parser, monkeypatch):
    service, aicredits, groq = parser
    monkeypatch.setattr(settings, "M1_PROVIDER", "aicredits")
    service._store_parsed_resume = AsyncMock(return_value="stored-resume")
    result = await service.parse_resume_content("application-owned", "candidate-owned", b"Python developer", "resume.txt", "text/plain")
    assert result == "stored-resume"
    service._app_repo.update_status.assert_awaited_once_with("application-owned", "parsing")
    service._store_parsed_resume.assert_awaited_once_with("application-owned", "candidate-owned", "Python developer", aicredits.return_value)
    groq.assert_not_awaited()
