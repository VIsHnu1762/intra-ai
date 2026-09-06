"""AICredits changes M1 transport, preserving its evidence and schema contracts."""
from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from app.agents import ALEX_PROFILE
from app.core.config import settings
from app.integrations.aicredits_client import AICreditsError
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import InterviewAnswerInput
from app.interview_intelligence.prompts import build_m1_system_prompt, build_m1_user_prompt
from app.interview_intelligence.provider import AICreditsAnalysisProvider, M1ProviderError, get_m1_provider


@pytest.fixture
def turn():
    return InterviewAnswerInput(answer_id="answer-one", question_text="How did you prevent duplicate payments?",
        answer_text="I built a payment ledger and used idempotency keys to prevent duplicate charges.",
        context=InterviewAIContext(interview_id="interview-one", candidate_id="candidate-one", current_round_id="round-one", current_agent_id="alex"),
        agent_profile=ALEX_PROFILE, job_description="Build reliable payment services.",
        candidate_profile={"skills": ["PostgreSQL"], "projects": ["Payment ledger"]})


@pytest.fixture
def valid():
    return {"answer_id": "model-answer-id", "overall_performance": 0.7, "confidence": 0.8,
        "vague": False, "contradiction_detected": False,
        "evidence": [{"id": "e1", "competency": "reliability", "signal": "Used idempotency keys to prevent duplicate charges.",
                      "score": 7, "round_id": "wrong", "source_agent_id": "wrong"}],
        "competency_findings": [{"competency_id": "reliability", "assessment": "Explains a duplicate prevention mechanism.",
                                 "confidence": 0.8, "evidence_ids": ["e1"]}]}


@pytest.mark.asyncio
async def test_preserves_prompt_context_and_scopes_evidence_to_current_answer(turn, valid):
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    with patch("app.integrations.groq_client.call_groq", side_effect=AssertionError("Groq must not be called")):
        result = await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    args, kwargs = client.generate_intelligence.call_args
    assert args == ("m1",) and kwargs["context_id"] == turn.answer_id
    assert kwargs["messages"][0]["content"].startswith(build_m1_system_prompt(ALEX_PROFILE))
    assert kwargs["messages"][1] == {"role": "user", "content": build_m1_user_prompt(turn)}
    assert "PostgreSQL" in kwargs["messages"][1]["content"] and "reliable payment services" in kwargs["messages"][1]["content"]
    assert result.answer_id == turn.answer_id
    assert result.evidence[0].id != "e1"
    assert result.evidence[0].source_agent_id == "alex" and result.evidence[0].round_id == "round-one"
    assert result.evidence[0].metadata["answer_id"] == "answer-one"
    assert result.competency_findings[0].evidence_ids == [result.evidence[0].id]
    assert valid["evidence"][0]["id"] == "e1"  # scope copied the provider output


@pytest.mark.asyncio
@pytest.mark.parametrize("signal", [
    "Used exponential backoff to prevent duplicate charges.",
    "Used idempotency keys to guarantee exactly-once end-to-end delivery.",
    "Demonstrates professional humility.",
    "dempotency keys",  # Not a complete word from the answer.
])
async def test_unsupported_evidence_is_rejected_without_persisting_or_extra_calls(turn, valid, signal):
    valid["evidence"][0]["signal"] = signal
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    with pytest.raises(M1ProviderError, match="GROUNDING_VALIDATION_ERROR"):
        await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 1
    assert valid["evidence"][0]["signal"] == signal


@pytest.mark.asyncio
async def test_exact_evidence_keeps_numeric_score_scale_and_tolerates_asr_whitespace(turn, valid):
    valid["evidence"][0].update(signal="used  idempotency\nkeys", score=7.5)
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    result = await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert result.evidence[0].score == 7.5
    assert result.overall_performance == .7


@pytest.mark.asyncio
async def test_single_structural_repair_preserves_original_turn_and_finding(turn, valid):
    invalid = deepcopy(valid)
    invalid["competency_findings"][0]["evidence_ids"] = ["unknown"]
    client = AsyncMock()
    client.generate_intelligence.side_effect = [invalid, valid]
    result = await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 2
    second = client.generate_intelligence.call_args_list[1].kwargs["messages"]
    assert [message["role"] for message in second] == ["system", "user", "assistant", "user"]
    assert second[1]["content"] == build_m1_user_prompt(turn)
    assert "unknown" in second[2]["content"] and "ORIGINAL current answer" in second[3]["content"]
    assert len(result.evidence) == len(result.competency_findings) == 1


@pytest.mark.asyncio
async def test_repair_cannot_delete_findings_to_hide_broken_refs(turn, valid):
    invalid = deepcopy(valid)
    invalid["competency_findings"][0]["evidence_ids"] = ["unknown"]
    changed = deepcopy(valid)
    changed["competency_findings"] = []
    client = AsyncMock()
    client.generate_intelligence.side_effect = [invalid, changed]
    with pytest.raises(M1ProviderError, match="Repair removed or added findings"):
        await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 2


@pytest.mark.asyncio
async def test_duplicate_evidence_is_rejected_without_repair(turn, valid):
    valid["evidence"].append(deepcopy(valid["evidence"][0]))
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    with pytest.raises(M1ProviderError, match="Duplicate evidence IDs"):
        await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 1


@pytest.mark.asyncio
async def test_second_invalid_output_stops_after_one_repair(turn, valid):
    valid["overall_performance"] = 7
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    with pytest.raises(M1ProviderError, match="AICredits output failed AnswerAnalysis validation after one repair"):
        await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["rate_limited", "authentication_failed", "configuration_missing", "timeout", "response_invalid"])
async def test_transport_errors_do_not_trigger_schema_repair_or_groq_fallback(turn, code):
    client = AsyncMock()
    client.generate_intelligence.side_effect = AICreditsError(code)
    with patch("app.integrations.groq_client.call_groq", side_effect=AssertionError("No Groq fallback")):
        with pytest.raises(M1ProviderError, match=code):
            await AICreditsAnalysisProvider(client).analyze_answer_async(turn)
    assert client.generate_intelligence.call_count == 1


def test_resolver_requires_nano_key_even_if_other_keys_exist(monkeypatch):
    monkeypatch.setattr(settings, "AICREDITS_API_KEY_GPT5_NANO", "")
    monkeypatch.setattr(settings, "AICREDITS_API_KEY_GEMINI_FLASH_LITE", "gemini-present")
    monkeypatch.setattr(settings, "GROQ_M1_API_KEY", "groq-present")
    with pytest.raises(M1ProviderError, match="AICREDITS_API_KEY_GPT5_NANO"):
        get_m1_provider("aicredits")
    monkeypatch.setattr(settings, "AICREDITS_API_KEY_GPT5_NANO", "nano-present")
    assert isinstance(get_m1_provider("aicredits"), AICreditsAnalysisProvider)


def test_provider_model_metadata_uses_neutral_override_without_changing_report_model(monkeypatch):
    monkeypatch.setattr(settings, "AICREDITS_M1_MODEL", "google/gemini-3.1-flash-lite")
    monkeypatch.setattr(settings, "AICREDITS_GPT5_NANO_MODEL", "openai/gpt-5-nano")
    assert AICreditsAnalysisProvider(AsyncMock()).model == "google/gemini-3.1-flash-lite"
    assert settings.AICREDITS_GPT5_NANO_MODEL == "openai/gpt-5-nano"
    monkeypatch.setattr(settings, "AICREDITS_M1_MODEL", " ")
    assert AICreditsAnalysisProvider(AsyncMock()).model == "openai/gpt-5-nano"


def test_synchronous_m1_interface_is_preserved(turn, valid):
    client = AsyncMock()
    client.generate_intelligence.return_value = valid
    assert AICreditsAnalysisProvider(client).analyze_answer(turn).answer_id == turn.answer_id
