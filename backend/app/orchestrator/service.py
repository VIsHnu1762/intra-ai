"""Meta-Orchestrator service interface for Intra AI."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional
import structlog
from app.agents.models import NextAction
from app.agents.registry import AgentRegistry, agent_registry
from app.interview_context.models import InterviewAIContext, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis
from app.models.enums import ActionType, DifficultyLevel
from app.orchestrator.graph import build_orchestrator_graph
from app.orchestrator.policies import normalize_competency

logger = structlog.stdlib.get_logger("intra_ai.orchestrator.service")


class MetaOrchestrator:
    """Intra AI Meta-Orchestrator.

    Consumes InterviewAIContext and M1 AnswerAnalysis, runs the LangGraph decision
    state machine, and produces the canonical NextAction (ASK_QUESTION, SWITCH_AGENT,
    COMPLETE).

    Optionally accepts the question_text that produced the current answer so Nemotron
    can reason about what was already asked (for repetition prevention).
    """

    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or agent_registry
        self.graph = build_orchestrator_graph(self.registry)

    def decide(
        self,
        context: InterviewAIContext,
        analysis: AnswerAnalysis,
        current_question_text: Optional[str] = None,
        turn_context: Optional[Any] = None,
    ) -> NextAction:
        """Synchronously execute the LangGraph state machine to decide the NextAction.

        Does NOT mutate context directly. Callers should record QuestionHistoryItems
        after calling decide() based on the returned NextAction.
        """
        logger.info(
            "orchestrator_deciding_action",
            interview_id=context.interview_id,
            current_agent=context.current_agent_id,
            answer_id=analysis.answer_id,
        )

        initial_state = {
            "context": context,
            "analysis": analysis,
            "current_question_text": current_question_text,
            "turn_context": turn_context,
        }

        output = self.graph.invoke(initial_state)
        action: NextAction = output["next_action"]

        logger.info(
            "orchestrator_action_decided",
            action=action.action.value,
            target_agent=action.target_agent_id,
            competency=action.competency,
            difficulty=action.difficulty.value if action.difficulty else None,
            nemotron_used=action.metadata.get("nemotron_used", False),
        )
        return action

    async def decide_async(
        self,
        context: InterviewAIContext,
        analysis: AnswerAnalysis,
        current_question_text: Optional[str] = None,
        turn_context: Optional[Any] = None,
    ) -> NextAction:
        """Asynchronously execute the LangGraph state machine to decide the NextAction."""
        logger.info(
            "orchestrator_deciding_action_async",
            interview_id=context.interview_id,
            current_agent=context.current_agent_id,
            answer_id=analysis.answer_id,
        )

        initial_state = {
            "context": context,
            "analysis": analysis,
            "current_question_text": current_question_text,
            "turn_context": turn_context,
        }

        output = await self.graph.ainvoke(initial_state)

        action: NextAction = output["next_action"]

        logger.info(
            "orchestrator_action_decided_async",
            action=action.action.value,
            target_agent=action.target_agent_id,
            competency=action.competency,
            difficulty=action.difficulty.value if action.difficulty else None,
            nemotron_used=action.metadata.get("nemotron_used", False),
        )
        return action

    @staticmethod
    def record_assessment(context: InterviewAIContext, action: NextAction) -> None:
        """Commit assessment outcomes for every action without claiming mastery."""
        coverage = action.metadata.get("coverage_policy", {})
        if "answered_question_id" in coverage:
            # M1's evidence classification can differ from the competency of
            # the question the candidate actually answered. Preserve that
            # classification without attaching the answer to an older question.
            answered = next((question for question in context.question_history
                             if question.id == coverage["answered_question_id"]), None)
            if answered is not None:
                assessed = {normalize_competency(c) for c in coverage.get("competencies", [])}
                answered_competency = normalize_competency(coverage.get("answered_competency") or "")
                sufficient = coverage.get("sufficient") and answered_competency in assessed
                answered.exploration_status = "SUFFICIENT" if sufficient else "PARTIAL"
                answered.metadata["answered_by"] = coverage.get("answer_id")
        else:
            # Standalone/legacy callers may not supply exact question identity.
            for competency in coverage.get("competencies", []):
                previous = context.get_questions_for_competency(competency)
                if previous:
                    previous[-1].exploration_status = "SUFFICIENT" if coverage.get("sufficient") else "PARTIAL"
                    previous[-1].metadata["answered_by"] = coverage.get("answer_id")
        outcomes = action.metadata.get("assessment_policy", {})
        if outcomes:
            saved = context.metadata.setdefault("assessed_insufficient", {})
            for competency, outcome in outcomes.items():
                saved[competency] = deepcopy(outcome)
                previous = context.get_questions_for_competency(competency)
                if previous:
                    previous[-1].exploration_status = "ASSESSED_INSUFFICIENT"
                    previous[-1].metadata["answered_by"] = outcome.get("answer_id")
                    previous[-1].metadata["assessment_outcome"] = deepcopy(outcome)

    @staticmethod
    def record_question(
        context: InterviewAIContext,
        action: NextAction,
        exploration_status: str = "FOLLOW_UP_REQUIRED",
    ) -> None:
        """Record the question from a NextAction into the context's question_history.

        Callers SHOULD invoke this after decide() so the next orchestrator call
        has a complete question history for repetition prevention.

        exploration_status:
            SUFFICIENT       — competency is fully explored
            PARTIAL          — some depth achieved, follow-up may be needed
            FOLLOW_UP_REQUIRED — shallow or vague answer, more needed
        """
        MetaOrchestrator.record_assessment(context, action)
        if action.action != ActionType.ASK_QUESTION or not action.question_text:
            return
        item = QuestionHistoryItem(
            agent_id=action.target_agent_id or context.current_agent_id,
            competency=action.competency or "general",
            question_text=action.question_text,
            difficulty=action.difficulty or DifficultyLevel.MEDIUM,
            exploration_status=exploration_status,
            metadata=deepcopy(action.metadata),
        )
        context.add_question_history(item)


# Default global instance
meta_orchestrator = MetaOrchestrator()
