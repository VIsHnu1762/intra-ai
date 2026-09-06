"""The Meta provider swap preserves routing guards and makes failures observable."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import settings
from app.integrations.aicredits_client import AICreditsError
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType
from app.orchestrator.service import MetaOrchestrator


def inputs():
    context = InterviewAIContext(
        interview_id="aicredits-routing", candidate_id="candidate", current_round_id="panel",
        current_agent_id="alex", missing_competencies=["system_design", "product_sense"],
        metadata={"configured_agent_ids": ["alex", "jordan"],
                  "required_competencies": ["system_design", "product_sense"]},
    )
    analysis = AnswerAnalysis(
        answer_id="payment-answer", overall_performance=.6, confidence=.9, vague=False,
        contradiction_detected=False, missing_information=["Kafka payment recovery"],
        competency_findings=[CompetencyFinding(competency_id="system_design", confidence=.9,
                                              assessment="Payment recovery needs clarification")],
    )
    return context, analysis


def decision(**changes):
    return {"action": "ASK_QUESTION", "target_agent_id": "alex", "competency": "system_design",
            "question_text": "How would you recover the Kafka payment service after a consumer failure?",
            "rationale": "Clarify Kafka payment recovery.", **changes}


def run_with_provider(response=None, error=None, contradiction=False):
    context, analysis = inputs()
    if contradiction:
        analysis.contradiction_detected = True
        analysis.contradiction_details = "The claimed recovery behavior conflicts with the earlier answer."
    adapter = AsyncMock(return_value=response or decision(), side_effect=error)
    groq = AsyncMock(side_effect=AssertionError("Groq must not be called when AICredits is selected"))
    with patch.object(settings, "ORCHESTRATOR_PROVIDER", "aicredits"), \
         patch("app.orchestrator.graph.generate_intelligence", adapter), \
         patch("app.orchestrator.graph.call_groq", groq):
        action = asyncio.run(MetaOrchestrator().decide_async(context, analysis))
    groq.assert_not_called()
    return action, adapter


def test_gemini_uses_original_prompt_contract_and_observable_model_metadata():
    action, adapter = run_with_provider()
    adapter.assert_awaited_once()
    assert adapter.call_args.args == ("orchestrator",)
    assert adapter.call_args.kwargs["context_id"] == "aicredits-routing"
    messages = adapter.call_args.kwargs["messages"]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert "INTERVIEW STATE:" in messages[1]["content"]
    assert "Kafka payment recovery" in messages[1]["content"]
    assert action.action == ActionType.ASK_QUESTION
    assert action.question_text == decision()["question_text"]
    assert action.metadata["orchestrator_provider"] == "aicredits"
    assert action.metadata["orchestrator_model"] == (settings.AICREDITS_ORCHESTRATOR_MODEL or settings.AICREDITS_GEMINI_FLASH_LITE_MODEL)
    assert action.metadata["orchestrator_model_used"] is True


@pytest.mark.parametrize("change", [
    {"target_agent_id": "unknown-agent", "action": "SWITCH_AGENT"},
    {"competency": "compiler_internals", "question_text": "Explain compiler optimizations."},
    {"action": "DELETE_INTERVIEW"},
])
def test_invalid_model_decision_still_uses_existing_guardrails(change):
    action, adapter = run_with_provider(response=decision(**change))
    adapter.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.target_agent_id == "alex"
    assert action.competency == "system_design"
    assert action.metadata["orchestrator_model_used"] is False


def test_provider_failure_is_visible_and_does_not_switch_to_another_model():
    action, adapter = run_with_provider(error=AICreditsError("credits_exhausted"))
    adapter.assert_awaited_once()
    assert action.action == ActionType.ASK_QUESTION
    assert action.metadata["orchestrator_model_used"] is False
    assert action.metadata["orchestrator_error_code"] == "AICREDITS_CREDITS_EXHAUSTED"


def test_forced_contradiction_resolution_still_bypasses_models():
    action, adapter = run_with_provider(contradiction=True)
    adapter.assert_not_called()
    assert action.action == ActionType.ASK_QUESTION
    assert action.metadata["nemotron_used"] is False
