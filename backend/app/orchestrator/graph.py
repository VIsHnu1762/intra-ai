"""LangGraph StateGraph definition for Intra AI Meta-Orchestrator.

Architecture:
    1. validate_state          — Deterministic: validate inputs, load profiles
    2. analyze_decision_state  — Deterministic: check completion conditions
    3. build_complete_action   — Deterministic: emit COMPLETE action
    4. pre_nemotron_guardrails — Deterministic: resolve priority + detect forcing conditions
    5. query_nemotron          — Configured model: routing reasoning
    6. validate_nemotron       — Deterministic: validate Nemotron's decision
    7. build_action            — Deterministic: build NextAction from decision OR fallback
    8. validate_action         — Deterministic: final contract enforcement
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from typing import Any, Optional
import structlog
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError as PydanticValidationError

from app.agents.models import AgentProfile, NextAction
from app.agents.registry import AgentRegistry
from app.core.config import settings
from app.core.exceptions import AgentNotFoundError, ValidationError
from app.integrations.groq_client import GroqAPIError, call_groq  # module-level for test patching
from app.integrations.aicredits_client import AICreditsError, generate_intelligence
from app.interview_context.models import QuestionHistoryItem
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.models import NemotronRoutingDecision, OrchestratorGraphState
from app.orchestrator.assessment import (
    assessed_insufficient_competencies, exhausted_assessment, plan_insufficient_assessment,
)
from app.orchestrator.policies import (
    answered_question,
    build_adaptive_probe_question,
    build_fresh_competency_question,
    build_competency_question_options,
    calculate_adaptive_difficulty,
    clamp_difficulty,
    choose_evidence_subject,
    configured_agent_ids,
    find_best_switch_agent,
    get_effective_missing_competencies,
    is_competency_sufficiently_evaluated,
    normalize_competency,
    plan_competency_difficulty,
    question_has_grounding,
    question_was_asked,
    select_next_competency,
)
from app.orchestrator.prompts import build_nemotron_routing_messages
from app.orchestrator.questions import (
    spoken_question_is_clear, first_spoken_question, validate_follow_up_contract,
    question_matches_follow_up, question_has_unspecified_scope,
    repair_follow_up_question, information_target_was_asked,
)

logger = structlog.stdlib.get_logger("intra_ai.orchestrator.graph")


def _get_nemotron_config() -> tuple[str, str, Optional[float]]:
    """Retrieve the selected provider; historical node names preserve graph contracts."""
    if settings.ORCHESTRATOR_PROVIDER == "aicredits":
        return (settings.AICREDITS_ORCHESTRATOR_MODEL or settings.AICREDITS_GEMINI_FLASH_LITE_MODEL,
                settings.AICREDITS_BASE_URL, settings.AICREDITS_REALTIME_TIMEOUT_SECONDS)
    model = getattr(settings, "GROQ_ORCHESTRATOR_MODEL", "openai/gpt-oss-20b")
    base_url = getattr(settings, "GROQ_ORCHESTRATOR_BASE_URL", "https://api.groq.com/openai/v1")
    timeout = getattr(settings, "GROQ_ORCHESTRATOR_TIMEOUT_SECONDS", 20.0)
    return model, base_url, timeout


def build_action_from_nemotron(
    decision: NemotronRoutingDecision,
    registry: AgentRegistry,
    context: Any,
    analysis: Any,
    curr_profile: AgentProfile,
    effective_missing: list[str],
    routing_metadata: Optional[dict[str, Any]] = None,
) -> NextAction:
    """Build NextAction from a validated Nemotron routing decision with persona-grounded dialogue.

    Enforces safe target profile resolution and safe fallback handoff phrasing without
    dereferencing missing target profiles.
    """
    action_type = decision.to_action_type()
    target_id = decision.target_agent_id.strip().lower()
    target_comp = decision.competency or (
        effective_missing[0] if effective_missing else "general_competency"
    )

    if routing_metadata is None:
        routing_metadata = {
            "nemotron_used": True,
            "cross_agent_opportunity": decision.cross_agent_opportunity,
            "trigger_signals": decision.trigger_signals,
            "unresolved_target_competencies": decision.unresolved_target_competencies,
            "source_agent": curr_profile.agent_id,
            "target_agent": target_id,
            **decision.metadata,
        }

    if action_type == ActionType.SWITCH_AGENT:
        # 1. Safely resolve target agent profile through registry before attribute access
        target_profile = registry.get_profile(target_id) if registry.has_agent(target_id) else None
        if target_profile is not None:
            diff = clamp_difficulty(
                context.difficulty,
                target_profile.min_difficulty,
                target_profile.max_difficulty,
            )
        else:
            diff = context.difficulty

        # 2. Prefer Nemotron's valid handoff dialogue (>10 non-whitespace characters)
        nemotron_handoff = (decision.question_text or "").strip()
        comp_display = target_comp.replace("_", " ") if target_comp else "the next topic"

        if len(nemotron_handoff) > 10:
            question = nemotron_handoff
        elif target_profile is not None:
            question = (
                f"Thank you for sharing those insights. I will now hand over to "
                f"{target_profile.display_name} to continue exploring {comp_display}."
            )
        else:
            # Safe generic fallback if target agent is missing or unregistered
            question = (
                f"Thank you for sharing those insights. I will now hand over to "
                f"our co-interviewer to continue exploring {comp_display}."
            )

        return NextAction(
            action=ActionType.SWITCH_AGENT,
            target_agent_id=target_id,
            competency=target_comp,
            difficulty=diff,
            question_text=question,
            rationale=decision.rationale,
            metadata=routing_metadata,
        )

    elif action_type == ActionType.ASK_QUESTION:
        evidence_subject = choose_evidence_subject(analysis, context, target_comp)

        nemotron_q = (decision.question_text or "").strip()
        if len(nemotron_q) > 10:
            question = nemotron_q
        else:
            question = build_adaptive_probe_question(
                target_competency=target_comp,
                missing_information=analysis.missing_information,
                recommended_follow_up=analysis.recommended_follow_up,
                current_agent=curr_profile,
                evidence_subject=evidence_subject,
            )

        has_depth = is_competency_sufficiently_evaluated(analysis)
        new_diff = calculate_adaptive_difficulty(
            current_difficulty=context.difficulty,
            performance=analysis.overall_performance,
            has_sufficient_depth=has_depth,
            is_vague=analysis.vague,
            contradiction=analysis.contradiction_detected,
            agent_profile=curr_profile,
        )
        return NextAction(
            action=ActionType.ASK_QUESTION,
            target_agent_id=curr_profile.agent_id,
            competency=target_comp,
            difficulty=new_diff,
            question_text=question,
            rationale=decision.rationale,
            metadata=routing_metadata,
        )

    else:  # COMPLETE
        nemotron_closing = (decision.question_text or "").strip()
        if len(nemotron_closing) > 10:
            closing_text = nemotron_closing
        else:
            closing_text = "Thank you for your time today. That concludes our interview questions for this session. Have a great day!"

        return NextAction(
            action=ActionType.COMPLETE,
            target_agent_id=curr_profile.agent_id,
            competency=None,
            difficulty=context.difficulty,
            question_text=closing_text,
            rationale=decision.rationale,
            metadata=routing_metadata,
        )


def build_orchestrator_graph(registry: AgentRegistry) -> Any:

    """Build and compile the LangGraph StateGraph governing interview state routing."""

    # ── NODE 1: validate_state ──────────────────────────────────────────────
    def validate_state(state: OrchestratorGraphState) -> dict[str, Any]:
        context = state.get("context")
        analysis = state.get("analysis")

        if not context:
            raise ValidationError("Missing context in OrchestratorGraphState")
        if not analysis:
            raise ValidationError("Missing analysis in OrchestratorGraphState")

        curr_id = context.current_agent_id.strip().lower()
        if not registry.has_agent(curr_id):
            raise AgentNotFoundError(f"Active agent '{curr_id}' not found in registry")
        selected = configured_agent_ids(context, registry)
        if curr_id not in selected:
            raise ValidationError(f"Active agent '{curr_id}' is not configured for this interview")

        profile = registry.get_profile(curr_id)
        insufficient_assessments = plan_insufficient_assessment(
            context, analysis, state.get("current_question_text"),
            current_answer=getattr(state.get("turn_context"), "current_answer", None))
        assessed_insufficient = assessed_insufficient_competencies(context) | set(insufficient_assessments)
        effective_missing = get_effective_missing_competencies(context, profile)
        turn_context = state.get("turn_context")
        required = getattr(getattr(turn_context, "job", None), "required_competencies", [])
        if required:
            evaluated = {normalize_competency(c) for c in context.evaluated_competencies}
            effective_missing = [normalize_competency(c) for c in required if normalize_competency(c) not in evaluated and not context.is_competency_sufficiently_asked(normalize_competency(c))]
        # M1's evaluated list records observations, including weak findings.
        # Asked-but-unresolved history must not become coverage merely because
        # the analyzer removed the competency from its missing list.
        current_sufficient = is_competency_sufficiently_evaluated(analysis)
        current_findings = {normalize_competency(f.competency_id) for f in analysis.competency_findings}
        for question in context.question_history:
            comp = normalize_competency(question.competency)
            if current_sufficient and comp in current_findings:
                continue
            if comp not in assessed_insufficient and not context.is_competency_sufficiently_asked(comp) and comp not in effective_missing:
                effective_missing.append(comp)
        covered = {normalize_competency(c) for aid in selected for c in registry.get_profile(aid).focal_competencies}
        effective_missing = [c for c in effective_missing if normalize_competency(c) not in assessed_insufficient and normalize_competency(c) in covered and (not required or normalize_competency(c) in {normalize_competency(r) for r in required})]

        return {
            "current_agent_profile": profile,
            "effective_missing_competencies": effective_missing,
            "insufficient_assessments": insufficient_assessments,
            "nemotron_decision": None,
            "nemotron_used": False,
        }

    # ── NODE 2: analyze_decision_state ─────────────────────────────────────
    def analyze_decision_state(state: OrchestratorGraphState) -> dict[str, Any]:
        context = state["context"]
        profile = state["current_agent_profile"]
        analysis = state["analysis"]
        effective_missing = (
            state.get("effective_missing_competencies")
            if state.get("effective_missing_competencies") is not None
            else get_effective_missing_competencies(context, profile)
        )

        # Safety: Never complete if this is the very first turn / no evidence has been collected
        has_progress = bool(context.accumulated_evidence or context.evaluated_competencies)
        assessed_insufficient = assessed_insufficient_competencies(context) | set(state.get("insufficient_assessments", {}))
        # Completing assessment does not require the candidate to demonstrate
        # mastery. Keep explicit gaps and their evidence for the final report.
        if assessed_insufficient and not effective_missing:
            return {"is_complete": True}
        if not has_progress:
            return {"is_complete": False}

        # Safety: Never complete if candidate just generated an unresolved contradiction
        if analysis.contradiction_detected:
            return {"is_complete": False}

        # Safety: Never complete if answer was vague and needs clarification
        if analysis.vague:
            return {"is_complete": False}

        # Safety: Never complete if current answer lacks sufficient depth
        if not is_competency_sufficiently_evaluated(analysis):
            return {"is_complete": False}

        # If all effective missing competencies have been evaluated
        if not effective_missing and has_progress:
            return {"is_complete": True}

        # Check if current agent or any other registered agent covers any missing competency
        current_covers = any(c in profile.focal_competencies for c in effective_missing)
        other_covers = False
        for agent in registry.list_agents():
            if agent.agent_id in configured_agent_ids(context, registry) and agent.agent_id.strip().lower() != profile.agent_id.strip().lower():
                if any(c in agent.focal_competencies for c in effective_missing):
                    other_covers = True
                    break

        # If neither current agent nor any other registered agent covers remaining gaps
        if not current_covers and not other_covers and has_progress:
            return {"is_complete": True}

        return {"is_complete": False}

    # ── CONDITIONAL ROUTER: check_completion ────────────────────────────────
    def route_completion(state: OrchestratorGraphState) -> str:
        if state.get("is_complete"):
            return "build_complete_action"
        return "pre_nemotron_guardrails"

    # ── NODE 3: build_complete_action ──────────────────────────────────────
    def build_complete_action(state: OrchestratorGraphState) -> dict[str, Any]:
        context = state["context"]
        profile = state["current_agent_profile"]

        insufficient = assessed_insufficient_competencies(context) | set(state.get("insufficient_assessments", {}))
        action = NextAction(
            action=ActionType.COMPLETE,
            target_agent_id=profile.agent_id,
            competency=None,
            difficulty=context.difficulty,
            question_text=None,
            rationale=("All configured objectives assessed; insufficient evidence is retained for reporting."
                       if insufficient else "All required interview competencies evaluated and required depth reached."),
            metadata={
                "evaluated_competencies": context.evaluated_competencies,
                "missing_competencies": context.missing_competencies,
                "nemotron_used": False,
                "incomplete_competencies": sorted(insufficient),
            },
        )
        return {"next_action": action}

    # ── NODE 4: pre_nemotron_guardrails ────────────────────────────────────
    # Runs BEFORE Nemotron. Resolves forcing conditions (contradiction, vagueness)
    # that must override any LLM routing decision. Also calculates the deterministic
    # fallback priority in case Nemotron fails or produces an invalid decision.
    def pre_nemotron_guardrails(state: OrchestratorGraphState) -> dict[str, Any]:
        analysis = state["analysis"]
        profile = state["current_agent_profile"]
        effective_missing = state.get("effective_missing_competencies", [])

        # Clarification retains the assessed competency instead of falling into
        # an ungrounded "general_competency" bucket.
        focal = {normalize_competency(c) for c in profile.focal_competencies}
        required = (getattr(getattr(state.get("turn_context"), "job", None), "required_competencies", None)
                    or state["context"].metadata.get("required_competencies") or [])
        if required:
            focal &= {normalize_competency(c) for c in required}
        asked = answered_question(state["context"], state.get("current_question_text"))
        asked_comp = normalize_competency(asked.competency) if asked is not None else None
        curr_comp = (asked_comp if asked_comp in focal else None) or next((
            normalize_competency(f.competency_id) for f in analysis.competency_findings
            if normalize_competency(f.competency_id) in focal
        ), None) or select_next_competency(effective_missing, profile.focal_competencies)
        curr_comp = curr_comp or (profile.focal_competencies[0] if profile.focal_competencies else "general_competency")

        assessed_insufficient = assessed_insufficient_competencies(state["context"]) | set(state.get("insufficient_assessments", {}))
        if state.get("insufficient_assessments") or curr_comp in assessed_insufficient:
            next_comp = select_next_competency(effective_missing, profile.focal_competencies)
            return {
                "priority": "advance_competency" if next_comp else "switch_agent",
                "target_competency": next_comp or next(iter(effective_missing), None),
                "force_deterministic": True,
            }

        # Forcing conditions that always override Nemotron
        if analysis.contradiction_detected:
            return {"priority": "contradiction", "target_competency": curr_comp, "force_deterministic": True}

        if analysis.vague:
            return {"priority": "vagueness", "target_competency": curr_comp, "force_deterministic": True}

        # Identify base competency
        has_sufficient_depth = is_competency_sufficiently_evaluated(analysis)

        if not has_sufficient_depth and analysis.overall_performance < 0.45:
            return {
                "priority": "probe_fundamentals",
                "target_competency": curr_comp,
                "force_deterministic": True,
            }

        if not has_sufficient_depth and analysis.missing_information:
            return {
                "priority": "probe_missing_info",
                "target_competency": curr_comp,
                "force_deterministic": False,  # Nemotron can still weigh in
            }

        if not has_sufficient_depth:
            return {"priority": "probe_missing_info", "target_competency": curr_comp, "force_deterministic": False}

        # For advance/switch cases, let Nemotron decide. Store fallback priority.
        remaining_missing = [c for c in effective_missing if c != curr_comp]
        next_agent_comp = select_next_competency(remaining_missing, profile.focal_competencies)

        if next_agent_comp:
            return {
                "priority": "advance_competency",
                "target_competency": next_agent_comp,
                "force_deterministic": False,
            }

        return {
            "priority": "switch_agent",
            "target_competency": remaining_missing[0] if remaining_missing else None,
            "force_deterministic": False,
        }

    # ── CONDITIONAL ROUTER: should_use_nemotron ────────────────────────────
    def route_nemotron(state: OrchestratorGraphState) -> str:
        """Route to Nemotron unless a forcing condition requires deterministic resolution."""
        # Keep the assessment policy authoritative, but let the existing Meta
        # call phrase a brief/weak answer's follow-up from the actual answer.
        # Bypassing it here made these candidates cycle through a question bank.
        if state.get("force_deterministic") and state.get("priority") not in {"vagueness", "probe_fundamentals"}:
            return "build_action"

        # AICredits failures are explicit and use the existing deterministic
        # guardrails, never another provider/key. Legacy Groq stays selectable.
        if settings.ORCHESTRATOR_PROVIDER == "aicredits":
            return "query_nemotron"
        api_key = getattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "").strip()
        if not api_key:
            logger.info("nemotron_skipped_no_api_key", reason="GROQ_ORCHESTRATOR_API_KEY not configured")
            return "build_action"

        return "query_nemotron"

    # ── NODE 5: query_nemotron ─────────────────────────────────────────────
    async def query_nemotron_async(state: OrchestratorGraphState) -> dict[str, Any]:
        """Call the configured Meta model with the existing routing contract."""
        # call_groq and GroqAPIError are module-level imports (for test patching)

        context = state["context"]
        analysis = state["analysis"]
        current_question = state.get("current_question_text")
        model, base_url, timeout = _get_nemotron_config()
        provider = settings.ORCHESTRATOR_PROVIDER

        messages = build_nemotron_routing_messages(
            context=context,
            analysis=analysis,
            registry=registry,
            current_question_text=current_question,
            turn_context=state.get("turn_context"),
            unresolved_competencies=state.get("effective_missing_competencies"),
            selected_priority=state.get("priority"),
            selected_target_competency=state.get("target_competency"),
        )

        logger.info(
            "nemotron_routing_call",
            current_agent=context.current_agent_id,
            model=model,
            provider=provider,
            interview_id=context.interview_id,
        )

        try:
            if provider == "aicredits":
                raw_decision = await generate_intelligence("orchestrator", messages=messages, context_id=context.interview_id)
            else:
                raw_decision = await call_groq(
                    model=model, messages=messages, response_format={"type": "json_object"},
                    temperature=0.2, base_url=base_url,
                    api_key=getattr(settings, "GROQ_ORCHESTRATOR_API_KEY", "").strip(),
                    timeout_seconds=timeout, context_id=context.interview_id,
                )

            logger.info(
                "nemotron_raw_response",
                action=raw_decision.get("action"),
                target=raw_decision.get("target_agent_id"),
                cross_agent=raw_decision.get("cross_agent_opportunity"),
                interview_id=context.interview_id,
                competency=raw_decision.get("competency"),
                question_fingerprint=hashlib.sha256(str(raw_decision.get("question_text") or "").encode()).hexdigest()[:16],
            )
            return {"nemotron_decision": raw_decision, "orchestrator_provider": provider,
                    "orchestrator_model": model, "orchestrator_error_code": None}

        except AICreditsError as exc:
            code = "AICREDITS_" + exc.code.upper()
            logger.warning("orchestrator_provider_failed", provider=provider, model=model,
                           error_code=code, interview_id=context.interview_id)
            return {"nemotron_decision": None, "orchestrator_provider": provider,
                    "orchestrator_model": model, "orchestrator_error_code": code}

        except GroqAPIError as exc:
            logger.warning(
                "nemotron_routing_failed_groq_error",
                error=str(exc),
                interview_id=context.interview_id,
            )
            return {"nemotron_decision": None}

        except Exception as exc:
            logger.warning(
                "nemotron_routing_failed_unexpected",
                error=str(exc),
                error_type=type(exc).__name__,
                interview_id=context.interview_id,
            )
            return {"nemotron_decision": None}

    def query_nemotron(state: OrchestratorGraphState) -> dict[str, Any]:
        """Compatibility wrapper for synchronous callers; live ainvoke stays async."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(query_nemotron_async(state))
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(query_nemotron_async(state))).result()

    # ── NODE 6: validate_nemotron ──────────────────────────────────────────
    def validate_nemotron(state: OrchestratorGraphState) -> dict[str, Any]:
        """Validate Nemotron's raw output against NemotronRoutingDecision schema.

        Enforces:
        - Valid action type
        - Target agent exists in registry
        - SWITCH_AGENT cannot target the current agent
        - Rationale is non-empty
        - Completion is only allowed when state allows it
        """
        raw = state.get("nemotron_decision")
        context = state["context"]
        profile = state["current_agent_profile"]
        curr_id = context.current_agent_id.strip().lower()

        if raw is None:
            logger.info("nemotron_validate_skipped_no_decision")
            return {"nemotron_decision": None, "nemotron_used": False}

        # Parse into typed model
        try:
            decision = NemotronRoutingDecision.model_validate(raw)
        except (PydanticValidationError, Exception) as exc:
            logger.warning(
                "nemotron_decision_schema_invalid",
                error=str(exc),
                raw_action=raw.get("action") if isinstance(raw, dict) else None,
            )
            return {"nemotron_decision": None, "nemotron_used": False}

        # Validate target agent exists in registry
        target_id = decision.target_agent_id.strip().lower()
        if not registry.has_agent(target_id):
            logger.warning(
                "nemotron_invalid_target_agent",
                target=target_id,
                registered=sorted([a.agent_id for a in registry.list_agents()]),
            )
            return {"nemotron_decision": None, "nemotron_used": False}
        if target_id not in configured_agent_ids(context, registry):
            logger.warning("orchestrator_unconfigured_agent_rejected", target_agent=target_id)
            return {"nemotron_decision": None, "nemotron_used": False}

        # Validate SWITCH_AGENT doesn't target current agent
        if decision.action == "SWITCH_AGENT" and target_id == curr_id:
            logger.warning(
                "nemotron_switch_to_current_agent_rejected",
                current_agent=curr_id,
                target=target_id,
            )
            return {"nemotron_decision": None, "nemotron_used": False}

        if decision.action in ("ASK_QUESTION", "SWITCH_AGENT"):
            target_profile = registry.get_profile(target_id)
            competency = normalize_competency(decision.competency or "")
            owned = {normalize_competency(c) for c in target_profile.focal_competencies}
            turn_context = state.get("turn_context")
            required = getattr(getattr(turn_context, "job", None), "required_competencies", [])
            allowed = {normalize_competency(c) for c in required} if required else owned
            invalid = (
                competency not in owned or competency not in allowed
                or (decision.action == "ASK_QUESTION" and target_id != curr_id)
                or context.is_competency_sufficiently_asked(competency)
            )
            if invalid:
                logger.warning("orchestrator_ungrounded_target_rejected", competency=competency, target_agent=target_id)
                return {"nemotron_decision": None, "nemotron_used": False}

        # Validate COMPLETE is allowed (must have progress)
        if decision.action == "COMPLETE":
            has_progress = bool(context.accumulated_evidence or context.evaluated_competencies)
            if not has_progress:
                logger.warning("nemotron_premature_complete_rejected")
                return {"nemotron_decision": None, "nemotron_used": False}

        logger.info(
            "nemotron_decision_validated",
            action=decision.action,
            target_agent=target_id,
            competency=decision.competency,
            cross_agent=decision.cross_agent_opportunity,
        )
        return {"nemotron_decision": decision, "nemotron_used": True}

    # ── CONDITIONAL ROUTER: route_after_nemotron ───────────────────────────
    def route_after_nemotron(state: OrchestratorGraphState) -> str:
        """After Nemotron validation: use Nemotron decision or fall back."""
        if state.get("nemotron_decision") is not None and state.get("nemotron_used"):
            return "build_action"
        # Nemotron failed or was invalid — fall back to deterministic
        return "build_action"

    # ── NODE 7: build_action ───────────────────────────────────────────────
    def build_action(state: OrchestratorGraphState) -> dict[str, Any]:
        """Build the canonical NextAction from validated Nemotron decision or deterministic fallback."""
        priority = state.get("priority", "advance_competency")
        context = state["context"]
        analysis = state["analysis"]
        curr_profile = state["current_agent_profile"]
        effective_missing = state.get("effective_missing_competencies", [])
        nemotron_decision: Optional[NemotronRoutingDecision] = state.get("nemotron_decision")
        nemotron_used: bool = state.get("nemotron_used", False)

        if (priority in {"vagueness", "probe_fundamentals"} and nemotron_used and nemotron_decision
                and nemotron_decision.action == ActionType.ASK_QUESTION.value
                and nemotron_decision.target_agent_id == curr_profile.agent_id
                and normalize_competency(nemotron_decision.competency or "")
                    == normalize_competency(state.get("target_competency") or "")):
            # The model supplies wording only for this constrained policy. It
            # cannot escape clarification, change persona/competency, or finish.
            result = _build_action_from_nemotron(
                decision=nemotron_decision, state=state, context=context,
                analysis=analysis, curr_profile=curr_profile, effective_missing=effective_missing,
            )
            result["next_action"].metadata["priority"] = priority
            result["next_action"].rationale = (
                ("Answer was vague; clarify the candidate's stated work. " if priority == "vagueness"
                 else "Probe fundamentals at reduced difficulty. ") + nemotron_decision.rationale
            )
            return result

    # ── FORCING CONDITIONS (always deterministic) ──
        if priority == "contradiction":
            detail = analysis.contradiction_details or "earlier statements"
            question = analysis.recommended_follow_up or (
                f"Earlier you mentioned extensive experience in this area, but just now you "
                f"indicated otherwise. Could you clarify the discrepancy regarding {detail}?"
            )
            action = NextAction(
                action=ActionType.ASK_QUESTION,
                target_agent_id=curr_profile.agent_id,
                competency=state.get("target_competency") or "general_competency",
                difficulty=context.difficulty,
                question_text=question,
                rationale=f"Contradiction detected: {detail}; requesting clarification.",
                metadata={"nemotron_used": False, "priority": "contradiction"},
            )
            return {"next_action": action}

        if priority == "vagueness":
            reason = analysis.vague_reason or "lacked technical depth"
            target_comp = state.get("target_competency") or "general_competency"
            comp_display = target_comp.replace("_", " ")
            new_diff = calculate_adaptive_difficulty(
                current_difficulty=context.difficulty,
                performance=analysis.overall_performance,
                has_sufficient_depth=False,
                is_vague=True,
                contradiction=False,
                agent_profile=curr_profile,
            )
            question = (
                f"In a web app, when users report a problem, what is the first thing you would check first for {comp_display}?"
            )
            action = NextAction(
                action=ActionType.ASK_QUESTION,
                target_agent_id=curr_profile.agent_id,
                competency=target_comp,
                difficulty=new_diff,
                question_text=question,
                rationale=f"Answer was vague ({reason}); probing for concrete details.",
                metadata={"nemotron_used": False, "priority": "vagueness"},
            )
            return {"next_action": action}

        if priority == "probe_fundamentals":
            target_comp = state.get("target_competency") or (
                curr_profile.focal_competencies[0] if curr_profile.focal_competencies else "general_competency"
            )
            new_diff = calculate_adaptive_difficulty(
                current_difficulty=context.difficulty,
                performance=analysis.overall_performance,
                has_sufficient_depth=False,
                is_vague=False,
                contradiction=False,
                agent_profile=curr_profile,
            )
            comp_display = target_comp.replace("_", " ")
            question = analysis.recommended_follow_up or (
                f"Stepping back to the core concepts and fundamentals of {comp_display}, "
                f"how would you ensure data durability and consistency in production systems?"
            )
            action = NextAction(
                action=ActionType.ASK_QUESTION,
                target_agent_id=curr_profile.agent_id,
                competency=target_comp,
                difficulty=new_diff,
                question_text=question,
                rationale=(
                    f"Candidate struggled on '{target_comp}' ({analysis.overall_performance:.2f}); "
                    f"reducing difficulty to {new_diff.value} to probe core fundamentals."
                ),
                metadata={"nemotron_used": False, "priority": "probe_fundamentals"},
            )
            return {"next_action": action}

        # ── NEMOTRON-DRIVEN OR FALLBACK FOR NON-FORCING CONDITIONS ──

        # A remaining competency owned by another registered agent is a
        # deterministic handoff condition. Nemotron still gets a chance to
        # provide grounded dialogue, but it cannot keep the current persona
        # asking questions outside its ownership. The registry lookup remains
        # fully N-agent and does not encode a fixed Alex→Jordan chain.
        if (
            priority == "switch_agent"
            and nemotron_decision
            and nemotron_used
            and nemotron_decision.action == ActionType.ASK_QUESTION.value
            and not any(
                missing in curr_profile.focal_competencies
                for missing in effective_missing
            )
        ):
            logger.warning(
                "nemotron_non_switch_for_cross_agent_gap",
                current_agent=curr_profile.agent_id,
                target_competency=state.get("target_competency"),
            )
            nemotron_decision = None
            nemotron_used = False

        if nemotron_decision and nemotron_used:
            result = _build_action_from_nemotron(
                decision=nemotron_decision,
                state=state,
                context=context,
                analysis=analysis,
                curr_profile=curr_profile,
                effective_missing=effective_missing,
            )
            result["next_action"].metadata["priority"] = priority
            return result

        # ── DETERMINISTIC FALLBACK ──
        logger.info("nemotron_fallback_applied", priority=priority)
        return _build_action_deterministic(
            priority=priority,
            state=state,
            context=context,
            analysis=analysis,
            curr_profile=curr_profile,
            effective_missing=effective_missing,
        )

    def _build_action_from_nemotron(
        decision: NemotronRoutingDecision,
        state: OrchestratorGraphState,
        context: Any,
        analysis: Any,
        curr_profile: AgentProfile,
        effective_missing: list[str],
    ) -> dict[str, Any]:
        """Build NextAction from a validated Nemotron routing decision."""
        action = build_action_from_nemotron(
            decision=decision,
            registry=registry,
            context=context,
            analysis=analysis,
            curr_profile=curr_profile,
            effective_missing=effective_missing,
        )
        return {"next_action": action}


    def _build_action_deterministic(
        priority: str,
        state: OrchestratorGraphState,
        context: Any,
        analysis: Any,
        curr_profile: AgentProfile,
        effective_missing: list[str],
    ) -> dict[str, Any]:
        """Build NextAction using the deterministic fallback policy."""
        target_comp = state.get("target_competency")

        evidence_subject = choose_evidence_subject(analysis, context, target_comp)

        if priority == "vagueness":
            reason = analysis.vague_reason or "lacked technical depth"
            target_comp = target_comp or "general_competency"
            comp_display = target_comp.replace("_", " ")
            new_diff = calculate_adaptive_difficulty(
                current_difficulty=context.difficulty,
                performance=analysis.overall_performance,
                has_sufficient_depth=False,
                is_vague=True,
                contradiction=False,
                agent_profile=curr_profile,
            )
            question = (
                f"In a web app, when users report a problem, what is the first thing you "
                f"would check first for {comp_display}?"
            )
            action = NextAction(
                action=ActionType.ASK_QUESTION,
                target_agent_id=curr_profile.agent_id,
                competency=target_comp,
                difficulty=new_diff,
                question_text=question,
                rationale=f"Answer was vague ({reason}); probing for concrete details.",
                metadata={"nemotron_used": False, "priority": "vagueness"},
            )
            return {"next_action": action}

        if priority == "probe_missing_info":
            if not target_comp:
                target_comp = (
                    analysis.competency_findings[0].competency_id
                    if analysis.competency_findings
                    else (curr_profile.focal_competencies[0] if curr_profile.focal_competencies else "general_competency")
                )
            question = build_adaptive_probe_question(
                target_competency=target_comp,
                missing_information=analysis.missing_information,
                recommended_follow_up=analysis.recommended_follow_up,
                current_agent=curr_profile,
                evidence_subject=evidence_subject,
            )
            first_gap = analysis.missing_information[0] if analysis.missing_information else "trade-offs"
            action = NextAction(
                action=ActionType.ASK_QUESTION,
                target_agent_id=curr_profile.agent_id,
                competency=target_comp,
                difficulty=context.difficulty,
                question_text=question,
                rationale=(
                    f"Candidate gave a promising answer ({analysis.overall_performance:.2f}) on '{target_comp}', "
                    f"but omitted critical depth: '{first_gap}'; probing deeper before progressing."
                ),
                metadata={"nemotron_used": False, "priority": "probe_missing_info"},
            )
            return {"next_action": action}

        if priority == "switch_agent":
            switch_result = find_best_switch_agent(
                missing_competencies=effective_missing,
                current_agent_id=curr_profile.agent_id,
                registry=registry,
                allowed_agent_ids=configured_agent_ids(context, registry),
            )
            if switch_result:
                target_agent, switch_comp = switch_result
                diff = clamp_difficulty(
                    context.difficulty,
                    target_agent.min_difficulty,
                    target_agent.max_difficulty,
                )
                action = NextAction(
                    action=ActionType.SWITCH_AGENT,
                    target_agent_id=target_agent.agent_id,
                    competency=switch_comp,
                    difficulty=diff,
                    question_text=f"Handing over to {target_agent.display_name} to assess {switch_comp.replace('_', ' ')}.",
                    rationale=(
                        f"Current agent '{curr_profile.agent_id}' finished the available focal assessment objectives; "
                        f"switching to specialized agent '{target_agent.agent_id}' for '{switch_comp}'."
                    ),
                    metadata={"nemotron_used": False, "priority": "switch_agent"},
                )
                return {"next_action": action}

            # No switch candidate — advance competency with current agent
            fallback_comp = effective_missing[0] if effective_missing else (
                curr_profile.focal_competencies[0] if curr_profile.focal_competencies else "general_competency"
            )
            target_comp = fallback_comp

        # Advance competency (default)
        if not target_comp:
            target_comp = select_next_competency(effective_missing, curr_profile.focal_competencies) or (
                curr_profile.focal_competencies[0] if curr_profile.focal_competencies else "general_competency"
            )

        has_depth = is_competency_sufficiently_evaluated(analysis)
        new_diff = calculate_adaptive_difficulty(
            current_difficulty=context.difficulty,
            performance=analysis.overall_performance,
            has_sufficient_depth=has_depth,
            is_vague=analysis.vague,
            contradiction=analysis.contradiction_detected,
            agent_profile=curr_profile,
        )
        comp_display = target_comp.replace("_", " ")
        if analysis.recommended_follow_up and comp_display.casefold() in analysis.recommended_follow_up.casefold():
            question = analysis.recommended_follow_up
        else:
            question = (
                f"Let's move on to {comp_display}. How have you applied this in production, and where did it help?"
            )
        action = NextAction(
            action=ActionType.ASK_QUESTION,
            target_agent_id=curr_profile.agent_id,
            competency=target_comp,
            difficulty=new_diff,
            question_text=question,
            rationale=(
                f"Candidate demonstrated strong depth on previous topic; "
                f"advancing to '{target_comp}' at {new_diff.value} difficulty with {curr_profile.display_name}."
            ),
            metadata={"nemotron_used": False, "priority": priority},
        )
        return {"next_action": action}

    # ── NODE 8: validate_action ────────────────────────────────────────────
    def validate_action(state: OrchestratorGraphState) -> dict[str, Any]:
        action = state.get("next_action")
        if not action:
            raise ValidationError("Orchestrator failed to produce NextAction")

        if action.action not in (ActionType.ASK_QUESTION, ActionType.SWITCH_AGENT, ActionType.COMPLETE):
            raise ValidationError(f"Invalid canonical action: {action.action}")

        if not action.target_agent_id or not registry.has_agent(action.target_agent_id):
            raise AgentNotFoundError(f"Target agent '{action.target_agent_id}' is not registered")
        if action.target_agent_id not in configured_agent_ids(state["context"], registry):
            raise ValidationError(f"Target agent '{action.target_agent_id}' is not configured for this interview")
        analysis = state["analysis"]
        action.metadata["assessment_policy"] = dict(state.get("insufficient_assessments", {}))
        if state.get("orchestrator_provider"):
            action.metadata["orchestrator_provider"] = state["orchestrator_provider"]
            action.metadata["orchestrator_model"] = state["orchestrator_model"]
            action.metadata["orchestrator_model_used"] = bool(action.metadata.get("nemotron_used"))
            if state.get("orchestrator_error_code"):
                action.metadata["orchestrator_error_code"] = state["orchestrator_error_code"]
        action.metadata["coverage_policy"] = {
            "competencies": [f.competency_id for f in analysis.competency_findings],
            "sufficient": is_competency_sufficiently_evaluated(analysis),
            "answer_id": analysis.answer_id,
        }
        asked = answered_question(state["context"], state.get("current_question_text"))
        if asked is not None:
            action.metadata["coverage_policy"].update(
                answered_question_id=asked.id,
                answered_competency=normalize_competency(asked.competency),
            )

        if action.action == ActionType.SWITCH_AGENT:
            curr_id = state["context"].current_agent_id.strip().lower()
            if action.target_agent_id.strip().lower() == curr_id:
                raise ValidationError("SWITCH_AGENT cannot target the currently active agent")

        if not action.rationale or not action.rationale.strip():
            raise ValidationError("NextAction must have an explainable non-empty rationale")

        if action.action == ActionType.ASK_QUESTION:
            context, analysis = state["context"], state["analysis"]
            profile = registry.get_profile(action.target_agent_id)
            turn_context = state.get("turn_context")
            required = getattr(getattr(turn_context, "job", None), "required_competencies", [])
            allowed = {normalize_competency(c) for c in profile.focal_competencies}
            if required:
                allowed &= {normalize_competency(c) for c in required}
            target = normalize_competency(action.competency or "")
            if target not in allowed:
                target = next((normalize_competency(c) for c in state.get("effective_missing_competencies", []) if normalize_competency(c) in allowed), None)
                if not target:
                    raise ValidationError("No configured competency is owned by the active interviewer")
                action.competency = target
                action.question_text = None

            difficulty, policy = plan_competency_difficulty(
                context, analysis, profile, target, state.get("current_question_text"))
            action.difficulty = difficulty
            action.metadata["difficulty_policy"] = policy
            question = action.question_text or ""
            contract, contract_error = (validate_follow_up_contract(
                action.metadata["follow_up"], getattr(turn_context, "current_answer", "") or "")
                if "follow_up" in action.metadata else (None, None))
            if contract_error:
                action.metadata.pop("follow_up", None)
                action.metadata["follow_up_rejected"] = contract_error
            elif contract is not None:
                action.metadata["follow_up"] = contract
                # Preserve the selected information target when model prose
                # expands it into a checklist or an unspecified whole system.
                if (not spoken_question_is_clear(question, difficulty)
                        or question_has_unspecified_scope(question)
                        or not question_matches_follow_up(question, contract)):
                    repaired = repair_follow_up_question(contract, difficulty)
                    if repaired and not question_was_asked(repaired, context.question_history, state.get("current_question_text")):
                        question = action.question_text = repaired
                        action.metadata["follow_up_question_repaired"] = True
            m1_question_preferred = False
            probe = analysis.recommended_follow_up or ""
            # A weak/vague answer needs one concrete fact, not a list of requested
            # deliverables such as diagrams and metrics. Keep comparison questions
            # ("between X and Y") eligible for the existing grounding checks.
            compound_m1_probe = bool(
                (analysis.vague or analysis.overall_performance < 0.45)
                and re.search(r"\b(?:provide|give|list|share|include)\b[^?]*\band\b", probe, re.IGNORECASE)
            )
            if compound_m1_probe:
                action.metadata["m1_probe_rejected"] = "compound_deliverables"
            assessed_now = ({normalize_competency(asked.competency)} if asked is not None else
                            {normalize_competency(f.competency_id) for f in analysis.competency_findings})
            if (contract is None and contract_error is None
                    and not compound_m1_probe
                    and not spoken_question_is_clear(question, difficulty)
                    and probe and probe != question and (not assessed_now or target in assessed_now)
                    and spoken_question_is_clear(probe, difficulty)
                    and not question_has_unspecified_scope(probe)
                    and question_has_grounding(probe, target, analysis, turn_context)
                    and not question_was_asked(probe, context.question_history, state.get("current_question_text"))):
                # M1's existing focused probe is a better recovery than cutting
                # a broad first clause out of a failed multi-part Meta question.
                question = action.question_text = probe
                m1_question_preferred = True
            if contract is None and not spoken_question_is_clear(question, difficulty):
                single_question = first_spoken_question(question, difficulty)
                if single_question:
                    question = action.question_text = single_question
                    action.metadata["compound_question_split"] = True
            repeated = question_was_asked(question, context.question_history, state.get("current_question_text"))
            assessed = ({normalize_competency(asked.competency)} if asked is not None else
                        {normalize_competency(f.competency_id) for f in analysis.competency_findings})
            stale_followup = bool(assessed and target not in assessed and question == analysis.recommended_follow_up)
            simpler = analysis.vague or analysis.overall_performance < 0.45
            semantic_question = bool(action.metadata.get("nemotron_used")) or question == analysis.recommended_follow_up
            ungrounded = bool(contract_error or (contract and not question_matches_follow_up(question, contract))
                              or (semantic_question and not question_has_grounding(question, target, analysis, turn_context)))
            unclear = (not spoken_question_is_clear(question, difficulty)
                       or bool(semantic_question and question_has_unspecified_scope(question)))
            grounded_simple_question = (semantic_question and not ungrounded
                                        and spoken_question_is_clear(question, DifficultyLevel.EASY))
            action.metadata["question_source"] = ("m1" if m1_question_preferred else
                                                   "meta" if action.metadata.get("nemotron_used") else
                                                   "m1" if question == analysis.recommended_follow_up else "fallback")
            options = build_competency_question_options(target, difficulty, context, analysis)
            used_objectives = {q.metadata.get("objective_id") for q in context.get_questions_for_competency(target)}
            contract_objective = f"{target}:{contract['objective']}" if contract else None
            contract_repeated = bool(contract and (
                contract_objective in used_objectives or information_target_was_asked(contract, context.question_history)))
            repeated = repeated or contract_repeated
            objectives_exhausted = bool(options) and all(key in used_objectives for key, _ in options)
            if (
                objectives_exhausted or not question or repeated or stale_followup or ungrounded
                or unclear or (simpler and not analysis.contradiction_detected and not grounded_simple_question)
            ):
                # The existing M1 call often already selected a narrower fact.
                # Keep that probe when Meta's prose fails, before consulting the
                # generic bank. It may not reopen a consumed contract/objective.
                probe = analysis.recommended_follow_up or ""
                replacement_source = "fallback"
                replacement = None
                if (not objectives_exhausted and not contract_repeated and not compound_m1_probe and probe and probe != question
                        and (not assessed or target in assessed)
                        and spoken_question_is_clear(probe, DifficultyLevel.EASY if simpler else difficulty)
                        and not question_has_unspecified_scope(probe)
                        and question_has_grounding(probe, target, analysis, turn_context)
                        and not question_was_asked(probe, context.question_history, state.get("current_question_text"))):
                    replacement, replacement_source = probe, "m1"
                if replacement is None:
                    replacement = build_fresh_competency_question(target, difficulty, context, analysis, state.get("current_question_text"))
                # A replacement asks a different fact; never attach the rejected
                # model contract to its history or use it to grade that answer.
                action.metadata.pop("follow_up", None)
                action.metadata.pop("follow_up_question_repaired", None)
                contract = None
                if replacement:
                    action.question_text = replacement
                    action.metadata["question_source"] = replacement_source
                    action.metadata["question_policy"] = {"repetition_prevented": repeated, "simplified": simpler, "stale_followup_replaced": stale_followup, "ungrounded_question_replaced": ungrounded, "unclear_question_replaced": unclear}
                else:
                    action.metadata["assessment_policy"][target] = exhausted_assessment(analysis)
                    alternative = None
                    closed = assessed_insufficient_competencies(context) | set(action.metadata["assessment_policy"])
                    remaining = [normalize_competency(c) for c in state.get("effective_missing_competencies", []) if normalize_competency(c) not in closed]
                    # Exhausting a probe bank must not silently skip another
                    # configured interviewer or return an empty question.
                    for next_profile in [profile, *[p for p in registry.list_agents() if p.agent_id != profile.agent_id and p.agent_id in configured_agent_ids(context, registry)]]:
                        for next_comp in remaining:
                            if next_comp not in next_profile.focal_competencies:
                                continue
                            next_level, next_policy = plan_competency_difficulty(context, analysis, next_profile, next_comp)
                            next_question = build_fresh_competency_question(next_comp, next_level, context, analysis)
                            if next_question:
                                alternative = (next_profile, next_comp, next_level, next_policy, next_question)
                                break
                        if alternative:
                            break
                    if alternative:
                        next_profile, next_comp, next_level, next_policy, next_question = alternative
                        action.competency, action.difficulty = next_comp, next_level
                        action.metadata["difficulty_policy"] = next_policy
                        action.metadata["unresolved_competency"] = target
                        action.target_agent_id = next_profile.agent_id
                        if next_profile.agent_id != profile.agent_id:
                            action.action = ActionType.SWITCH_AGENT
                            action.question_text = f"Thank you. {next_profile.display_name} will continue with {next_comp.replace('_', ' ')}."
                        else:
                            action.question_text = next_question
                        action.rationale = f"Distinct probes for {target} exhausted; preserve its evidence gaps and assess {next_comp}."
                    else:
                        action.action = ActionType.COMPLETE
                        action.question_text = "Thank you for your time and for sharing what you could today. That concludes our questions."
                        action.rationale = "Available distinct probes exhausted; conclude with insufficient evidence explicitly retained for reporting."
                        action.metadata["incomplete_competencies"] = list(context.missing_competencies)
                        action.competency = None
            if action.action == ActionType.ASK_QUESTION:
                options = build_competency_question_options(action.competency, action.difficulty, context, analysis)
                objective = (f"{action.competency}:{contract['objective']}" if contract else None)
                objective = objective or next((key for key, text in options if text == action.question_text), None)
                # Accepted model prose remains intact. Bind it to an available
                # objective for legacy responses; a validated fact plan keeps
                # its actual objective rather than receiving an arbitrary one.
                used = {q.metadata.get("objective_id") for q in context.get_questions_for_competency(action.competency)}
                objective = objective or next((key for key, _ in options if key not in used), None)
                if objective:
                    action.metadata["objective_id"] = objective
            logger.info("orchestrator_difficulty_policy", interview_id=context.interview_id, **policy)
            logger.info(
                "orchestrator_question_selected", interview_id=context.interview_id,
                answer_id=analysis.answer_id, competency=action.competency,
                answered_competency=asked.competency if asked is not None else None,
                source=action.metadata.get("question_source"),
                policy=action.metadata.get("question_policy", {}),
                information_target_selected=bool(action.metadata.get("follow_up")),
                follow_up_repaired=bool(action.metadata.get("follow_up_question_repaired")),
                follow_up_rejected=action.metadata.get("follow_up_rejected"),
                objective_id=action.metadata.get("objective_id"),
                question_fingerprint=hashlib.sha256((action.question_text or "").encode()).hexdigest()[:16],
            )

        return {"next_action": action}

    # ── GRAPH ASSEMBLY ─────────────────────────────────────────────────────
    builder = StateGraph(OrchestratorGraphState)

    builder.add_node("validate_state", validate_state)
    builder.add_node("analyze_decision_state", analyze_decision_state)
    builder.add_node("build_complete_action", build_complete_action)
    builder.add_node("pre_nemotron_guardrails", pre_nemotron_guardrails)
    builder.add_node("query_nemotron", RunnableLambda(query_nemotron, afunc=query_nemotron_async))
    builder.add_node("validate_nemotron", validate_nemotron)
    builder.add_node("build_action", build_action)
    builder.add_node("validate_action", validate_action)

    builder.add_edge(START, "validate_state")
    builder.add_edge("validate_state", "analyze_decision_state")
    builder.add_conditional_edges(
        "analyze_decision_state",
        route_completion,
        {
            "build_complete_action": "build_complete_action",
            "pre_nemotron_guardrails": "pre_nemotron_guardrails",
        },
    )
    builder.add_edge("build_complete_action", "validate_action")
    builder.add_conditional_edges(
        "pre_nemotron_guardrails",
        route_nemotron,
        {
            "query_nemotron": "query_nemotron",
            "build_action": "build_action",
        },
    )
    builder.add_edge("query_nemotron", "validate_nemotron")
    builder.add_edge("validate_nemotron", "build_action")
    builder.add_edge("build_action", "validate_action")
    builder.add_edge("validate_action", END)

    return builder.compile()
