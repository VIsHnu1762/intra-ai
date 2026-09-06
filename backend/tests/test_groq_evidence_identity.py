"""Provider-local e1/e2 IDs must never overwrite another answer's evidence."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.agents import ALEX_PROFILE
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import InterviewAnswerInput
from app.interview_intelligence.provider import GroqAnalysisProvider, M1ProviderError


def turn(answer_id, answer_text="I used Kafka and PostgreSQL."):
    return InterviewAnswerInput(
        answer_id=answer_id, question_text="How did you recover your payment service?",
        answer_text=answer_text, agent_profile=ALEX_PROFILE,
        context=InterviewAIContext(
            interview_id="same-interview", candidate_id="same-candidate", current_round_id="technical", current_agent_id="alex",
        ),
    )


def payload(score=8, signal="Explained transaction retries", evidence_id="e1"):
    return {
        "answer_id": "model-reuses-this-answer-id", "overall_performance": score / 10,
        "confidence": 0.9, "vague": False, "contradiction_detected": False,
        "evidence": [{"id": evidence_id, "competency": "system_design", "signal": signal, "score": score,
                      "source_agent_id": "model-invented-agent", "round_id": "model-invented-round"}],
        "competency_findings": [{"competency_id": "system_design", "assessment": signal,
                                 "confidence": 0.9, "evidence_ids": [evidence_id]}],
    }


@pytest.mark.asyncio
async def test_later_weak_e1_cannot_erase_earlier_strong_e1(monkeypatch):
    provider = GroqAnalysisProvider(api_key="test-key")
    monkeypatch.setattr("app.integrations.groq_client.call_groq", AsyncMock(side_effect=[
        payload(), payload(score=2, signal="Could not explain recovery"),
    ]))
    first_input = turn("answer-1")
    first = await provider.analyze_answer_async(first_input)
    for evidence in first.evidence:
        first_input.context.add_evidence(evidence)
    second_input = turn("answer-2", "I do not know how recovery works.")
    second_input.context = first_input.context
    second = await provider.analyze_answer_async(second_input)
    for evidence in second.evidence:
        first_input.context.add_evidence(evidence)

    assert first.answer_id == "answer-1" and second.answer_id == "answer-2"
    assert first.evidence[0].id != second.evidence[0].id
    assert len(first_input.context.accumulated_evidence) == 2
    assert [e.score for e in first_input.context.accumulated_evidence] == [8, 2]
    assert first_input.context.accumulated_evidence[0].signal == "Explained transaction retries"
    for analysis in (first, second):
        evidence = analysis.evidence[0]
        assert analysis.competency_findings[0].evidence_ids == [evidence.id]
        assert evidence.metadata["provider_evidence_id"] == "e1"
        assert evidence.metadata["provider_answer_id"] == "model-reuses-this-answer-id"
        assert evidence.metadata["answer_id"] == analysis.answer_id
        assert evidence.source_agent_id == "alex"
        assert evidence.round_id == "technical"


@pytest.mark.asyncio
async def test_retry_idempotence_and_no_mutation_of_provider_payload(monkeypatch):
    data = payload(evidence_id=1)
    before = deepcopy(data)
    monkeypatch.setattr("app.integrations.groq_client.call_groq", AsyncMock(return_value=data))
    provider = GroqAnalysisProvider(api_key="test-key")
    input_data = turn("answer-1")
    first = await provider.analyze_answer_async(input_data)
    repeated = await provider.analyze_answer_async(input_data)
    assert first.evidence[0].id == repeated.evidence[0].id
    assert first.competency_findings[0].evidence_ids == [first.evidence[0].id]
    assert first.evidence[0].metadata["provider_evidence_id"] == 1
    assert data == before
    for analysis in (first, repeated):
        input_data.context.add_evidence(analysis.evidence[0])
    assert len(input_data.context.accumulated_evidence) == 1


@pytest.mark.asyncio
async def test_same_local_answer_id_in_different_interviews_remains_isolated(monkeypatch):
    monkeypatch.setattr("app.integrations.groq_client.call_groq", AsyncMock(return_value=payload()))
    provider = GroqAnalysisProvider(api_key="test-key")
    first = await provider.analyze_answer_async(turn("answer-1"))
    another_input = turn("answer-1")
    another_input.context.interview_id = "different-interview"
    another = await provider.analyze_answer_async(another_input)
    assert first.evidence[0].id != another.evidence[0].id


@pytest.mark.asyncio
async def test_ambiguous_duplicate_ids_in_one_answer_are_rejected(monkeypatch):
    data = payload()
    data["evidence"].append({**data["evidence"][0], "signal": "A different finding"})
    monkeypatch.setattr("app.integrations.groq_client.call_groq", AsyncMock(return_value=data))
    with pytest.raises(M1ProviderError, match="Duplicate evidence IDs"):
        await GroqAnalysisProvider(api_key="test-key").analyze_answer_async(turn("answer-1"))


@pytest.mark.asyncio
async def test_missing_evidence_ids_get_stable_distinct_identity(monkeypatch):
    data = payload()
    data["evidence"][0].pop("id")
    data["evidence"].append({"competency": "system_design", "signal": "Second observation", "score": 7})
    data["competency_findings"] = []
    monkeypatch.setattr("app.integrations.groq_client.call_groq", AsyncMock(return_value=data))
    provider = GroqAnalysisProvider(api_key="test-key")
    first = await provider.analyze_answer_async(turn("answer-1"))
    repeated = await provider.analyze_answer_async(turn("answer-1"))
    assert len({e.id for e in first.evidence}) == 2
    assert [e.id for e in first.evidence] == [e.id for e in repeated.evidence]


@pytest.mark.asyncio
async def test_unknown_reference_is_repaired_once_with_same_model_and_identity(monkeypatch):
    original = payload()
    original["competency_findings"][0]["evidence_ids"] = ["e5"]
    untouched = deepcopy(original)
    repaired = payload()
    groq = AsyncMock(side_effect=[original, repaired])
    monkeypatch.setattr("app.integrations.groq_client.call_groq", groq)
    provider = GroqAnalysisProvider(api_key="test-key", model="openai/gpt-oss-20b")
    analysis = await provider.analyze_answer_async(turn("answer-repaired"))
    assert groq.await_count == 2
    assert all(call.kwargs["model"] == "openai/gpt-oss-20b" for call in groq.await_args_list)
    assert all(call.kwargs["context_id"] == "answer-repaired" for call in groq.await_args_list)
    assert groq.await_args_list[1].kwargs["messages"][-2]["role"] == "assistant"
    assert '"evidence_ids":["e5"]' in groq.await_args_list[1].kwargs["messages"][-2]["content"]
    assert analysis.answer_id == "answer-repaired"
    assert analysis.evidence[0].metadata["provider_evidence_id"] == "e1"
    assert analysis.evidence[0].signal == original["evidence"][0]["signal"]
    assert analysis.competency_findings[0].evidence_ids == [analysis.evidence[0].id]
    assert original == untouched
    assert analysis.evidence[0].id == provider._scope_evidence_ids(repaired, turn("answer-repaired"))["evidence"][0]["id"]


@pytest.mark.asyncio
async def test_second_invalid_reference_fails_without_another_retry(monkeypatch):
    invalid = payload()
    invalid["competency_findings"][0]["evidence_ids"] = ["e5"]
    groq = AsyncMock(return_value=invalid)
    monkeypatch.setattr("app.integrations.groq_client.call_groq", groq)
    with pytest.raises(M1ProviderError, match="after one repair"):
        await GroqAnalysisProvider(api_key="test-key").analyze_answer_async(turn("answer-invalid"))
    assert groq.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["drop_reference", "drop_finding", "change_signal", "change_evidence_id"])
async def test_repair_cannot_hide_bad_links_by_removing_or_rewriting_evidence(monkeypatch, change):
    invalid = payload()
    invalid["competency_findings"][0]["evidence_ids"] = ["e5"]
    repaired = payload()
    if change == "drop_reference":
        repaired["competency_findings"][0]["evidence_ids"] = []
    elif change == "drop_finding":
        repaired["competency_findings"] = []
    elif change == "change_signal":
        repaired["evidence"][0]["signal"] = "Invented new evidence"
    else:
        repaired["evidence"][0]["id"] = "e5"
        repaired["competency_findings"][0]["evidence_ids"] = ["e5"]
    groq = AsyncMock(side_effect=[invalid, repaired])
    monkeypatch.setattr("app.integrations.groq_client.call_groq", groq)
    with pytest.raises(M1ProviderError, match="SCHEMA_VALIDATION_ERROR: Repair"):
        await GroqAnalysisProvider(api_key="test-key").analyze_answer_async(turn("answer-hidden"))
    assert groq.await_count == 2


@pytest.mark.asyncio
async def test_quota_failure_never_triggers_schema_repair(monkeypatch):
    from app.integrations.groq_client import GroqAPIError
    groq = AsyncMock(side_effect=GroqAPIError("Groq API error [RESOURCE_EXHAUSTED] status 429"))
    monkeypatch.setattr("app.integrations.groq_client.call_groq", groq)
    with pytest.raises(M1ProviderError, match="RESOURCE_EXHAUSTED"):
        await GroqAnalysisProvider(api_key="test-key").analyze_answer_async(turn("answer-quota"))
    assert groq.await_count == 1
