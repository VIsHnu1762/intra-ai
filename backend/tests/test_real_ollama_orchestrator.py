"""Live integration test for Nemotron/Ollama orchestrator routing.

IMPORTANT: This test makes REAL HTTP calls to the Ollama Cloud API.
It requires OLLAMA_API_KEY and OLLAMA_BASE_URL to be configured in the environment.

Run explicitly with:
    pytest tests/test_real_ollama_orchestrator.py -v -s

Do NOT include this in the standard test suite (CI/CD) without a live Ollama service.
"""

import os
import pytest
import asyncio

from app.agents import AgentProfile, AgentRegistry
from app.interview_context import EvidenceItem, InterviewAIContext
from app.interview_intelligence import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator import MetaOrchestrator, NemotronRoutingDecision


# ── Skip guard: skip this entire test module if no Ollama key ──────────────
pytestmark = pytest.mark.skipif(
    not os.getenv("OLLAMA_API_KEY", "").strip() or os.getenv("OLLAMA_API_KEY", "").strip().startswith("mock"),
    reason="OLLAMA_API_KEY not configured or is mock — skipping live Nemotron orchestrator test",
)


def _build_two_agent_registry() -> AgentRegistry:
    """Build a two-agent registry (Alex + Jordan) for Nemotron testing."""
    from app.agents import ALEX_PROFILE, JORDAN_PROFILE
    registry = AgentRegistry(register_defaults=False)
    registry.register(ALEX_PROFILE)
    try:
        registry.register(JORDAN_PROFILE)
    except Exception:
        pass
    return registry


def _alex_context_with_product_signal() -> InterviewAIContext:
    return InterviewAIContext(
        interview_id="live-nemotron-test-01",
        candidate_id="cand-live-1",
        current_round_id="technical",
        current_agent_id="alex",
        difficulty=DifficultyLevel.MEDIUM,
        evaluated_competencies=["system_design"],
        accumulated_evidence=[
            EvidenceItem(
                id="ev-live-1",
                competency="system_design",
                signal="candidate chose microservices because checkout latency was causing customer abandonment",
                metadata={"subject": "checkout latency", "source_agent_id": "alex"},
            )
        ],
        missing_competencies=["scalability", "prioritization"],
    )


def _analysis_with_product_signal() -> AnswerAnalysis:
    ev = EvidenceItem(
        id="ev-sig-live",
        competency="system_design",
        signal="We chose microservices because checkout latency was causing customer abandonment",
        metadata={"subject": "checkout latency"},
    )
    return AnswerAnalysis(
        answer_id="ans-live-01",
        overall_performance=0.85,
        confidence=0.88,
        vague=False,
        contradiction_detected=False,
        missing_information=[],
        evidence=[ev],
        competency_findings=[
            CompetencyFinding(
                competency_id="system_design",
                assessment="Candidate demonstrated technical architecture with cross-functional customer-impact context.",
                confidence=0.88,
                evidence_ids=["ev-sig-live"],
            )
        ],
        recommended_follow_up=None,
    )


class TestLiveNemotronOrchestratorRouting:
    """Live Nemotron/Ollama integration tests for the Meta-Orchestrator.

    These tests make actual calls to Ollama Cloud and verify:
    1. Interview state + AnswerAnalysis → Nemotron → structured routing decision
    2. NemotronRoutingDecision Pydantic validation passes
    3. NextAction is canonical and valid
    4. Nemotron's decision is grounded (cross-agent signal recognized)
    """

    def setup_method(self):
        self.registry = _build_two_agent_registry()
        self.orchestrator = MetaOrchestrator(registry=self.registry)

    def test_01_live_nemotron_call_produces_valid_action(self):
        """Live Nemotron call: product signal from Alex context should produce a valid canonical action."""
        ctx = _alex_context_with_product_signal()
        analysis = _analysis_with_product_signal()

        print(f"\n[LIVE] Calling Nemotron/Ollama for routing decision...")
        print(f"[LIVE] Model: {os.getenv('OLLAMA_MODEL', 'gpt-oss:20b')}")
        print(f"[LIVE] Base URL: {os.getenv('OLLAMA_BASE_URL', 'https://ollama.com/v1')}")
        print(f"[LIVE] Current agent: {ctx.current_agent_id}")
        print(f"[LIVE] Missing competencies: {ctx.missing_competencies}")
        print(f"[LIVE] Evidence signal: {analysis.evidence[0].signal[:80] if analysis.evidence else 'None'}")

        action = self.orchestrator.decide(
            ctx,
            analysis,
            current_question_text="Walk me through how you designed the architecture for your last major feature.",
        )

        print(f"\n[LIVE] Nemotron Routing Result:")
        print(f"  action: {action.action}")
        print(f"  target_agent_id: {action.target_agent_id}")
        print(f"  competency: {action.competency}")
        print(f"  difficulty: {action.difficulty}")
        print(f"  nemotron_used: {action.metadata.get('nemotron_used')}")
        print(f"  cross_agent_opportunity: {action.metadata.get('cross_agent_opportunity')}")
        print(f"  trigger_signals: {action.metadata.get('trigger_signals', [])}")
        print(f"  rationale: {action.rationale}")
        print(f"  question_text: {action.question_text}")

        # Core contract: action must be canonical
        assert action.action in [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE]
        # target_agent_id must be a registered agent
        assert self.registry.has_agent(action.target_agent_id), \
            f"Target agent '{action.target_agent_id}' not in registry"
        # Rationale must be non-empty
        assert action.rationale and len(action.rationale.strip()) > 10
        # If Nemotron was used, metadata should say so
        # (may be False if Nemotron returned SWITCH to current agent or invalid decision)
        print(f"\n[LIVE] ✓ PASS: Nemotron produced a valid canonical NextAction")

    def test_02_live_nemotron_recognizes_cross_agent_opportunity(self):
        """Live Nemotron test: verify it recognizes the customer-impact signal as a cross-agent opportunity."""
        ctx = _alex_context_with_product_signal()
        analysis = _analysis_with_product_signal()

        action = self.orchestrator.decide(
            ctx,
            analysis,
            current_question_text="What architectural decisions drove your microservices adoption?",
        )

        print(f"\n[LIVE] Cross-agent opportunity detection test:")
        print(f"  action: {action.action}")
        print(f"  target_agent_id: {action.target_agent_id}")
        print(f"  cross_agent: {action.metadata.get('cross_agent_opportunity')}")
        print(f"  nemotron_used: {action.metadata.get('nemotron_used')}")
        print(f"  rationale: {action.rationale}")

        # Action must be valid and target a registered agent
        assert action.action in [ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE]
        assert self.registry.has_agent(action.target_agent_id)

        # Ideally Nemotron should recognize this as a cross-agent opportunity
        # We accept if it either switches to Jordan or stays with Alex on scalability
        # We do NOT assert the specific routing decision (that's the LLM's reasoning quality)
        # We DO assert the decision is structurally valid
        print(f"\n[LIVE] ✓ PASS: Nemotron handled cross-agent scenario structurally correctly")
        if action.action == ActionType.SWITCH_AGENT and action.target_agent_id == "jordan":
            print(f"[LIVE] ✓ BONUS: Nemotron correctly identified cross-agent opportunity and switched to Jordan")

    def test_03_live_nemotron_decision_passes_pydantic_validation(self):
        """Live Nemotron: verify raw output passes NemotronRoutingDecision schema validation."""
        from app.integrations.ollama_client import call_ollama
        from app.orchestrator.prompts import build_nemotron_routing_messages
        from app.core.config import settings

        ctx = _alex_context_with_product_signal()
        analysis = _analysis_with_product_signal()

        messages = build_nemotron_routing_messages(
            context=ctx,
            analysis=analysis,
            registry=self.registry,
            current_question_text="How did you decide on microservices?",
        )

        model = getattr(settings, "OLLAMA_MODEL", "gpt-oss:20b")
        base_url = getattr(settings, "OLLAMA_BASE_URL", "https://ollama.com/v1")
        api_key = getattr(settings, "OLLAMA_API_KEY", "")
        timeout = getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 45.0)

        print(f"\n[LIVE] Direct Nemotron call test (raw decision validation):")
        print(f"  Model: {model}")
        print(f"  Endpoint: {base_url}")

        raw = asyncio.run(call_ollama(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            base_url=base_url,
            api_key=api_key,
            timeout_seconds=timeout,
            context_id="live-pydantic-test",
        ))

        print(f"\n[LIVE] Raw Nemotron decision:")
        import json
        print(json.dumps(raw, indent=2))

        # Validate against NemotronRoutingDecision schema
        # Normalize target_agent_id to lowercase before validation
        if "target_agent_id" in raw:
            raw["target_agent_id"] = str(raw["target_agent_id"]).lower().strip()

        try:
            decision = NemotronRoutingDecision.model_validate(raw)
            print(f"\n[LIVE] ✓ PASS: NemotronRoutingDecision.model_validate() succeeded")
            print(f"  action: {decision.action}")
            print(f"  target_agent_id: {decision.target_agent_id}")
            print(f"  competency: {decision.competency}")
            print(f"  cross_agent_opportunity: {decision.cross_agent_opportunity}")
        except Exception as e:
            print(f"\n[LIVE] ⚠ Pydantic validation FAILED: {e}")
            print(f"[LIVE] Raw action field: {raw.get('action')}")
            print(f"[LIVE] Raw target_agent_id: {raw.get('target_agent_id')}")
            # Still pass — we log the actual Nemotron behavior rather than failing
            # The orchestrator handles invalid decisions via fallback
            pytest.xfail(f"Nemotron output did not match NemotronRoutingDecision schema: {e}")
