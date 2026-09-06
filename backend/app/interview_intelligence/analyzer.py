"""M1 Interview Intelligence Engine — Core semantic answer analysis service."""

from __future__ import annotations

import structlog

from app.interview_context.models import ContradictionItem, InterviewAIContext
from app.interview_intelligence.models import (
    AnswerAnalysis,
    InterviewAnswerInput,
)
from app.interview_intelligence.provider import (
    DeterministicMockM1Provider,
    M1AnalysisProvider,
    get_m1_provider,
)

logger = structlog.stdlib.get_logger("intra_ai.interview_intelligence.analyzer")


def apply_analysis_to_context(
    analysis: AnswerAnalysis,
    context: InterviewAIContext,
) -> None:
    """Explicit helper to apply M1 analysis findings to InterviewAIContext.

    Separates analysis from context mutation so the future Meta-Orchestrator
    retains explicit control over orchestration state changes.
    """
    # 1. Accumulate grounded evidence
    for ev in analysis.evidence:
        context.add_evidence(ev)

    # 2. Update evaluated competencies and resolve missing ones
    for finding in analysis.competency_findings:
        context.add_evaluated_competency(finding.competency_id)
        context.resolve_missing_competency(finding.competency_id)

    # 3. Record contradiction if detected
    if analysis.contradiction_detected and analysis.contradiction_details:
        context.add_contradiction(
            ContradictionItem(
                contradiction=analysis.contradiction_details,
                detected_by_agent_id=context.current_agent_id,
                round_id=context.current_round_id,
            )
        )


class M1InterviewAnalyzer:
    """M1 Interview Intelligence Engine.

    Analyzes candidate answers in the context of the active interviewer persona,
    competencies, and orchestration state. Produces grounded AnswerAnalysis.

    Strict Boundaries:
    - Does NOT decide next interview actions.
    - Does NOT switch agents or produce NextAction.
    - Does NOT make hiring decisions.
    - Does NOT mutate InterviewAIContext during analysis.
    """

    def __init__(self, provider: M1AnalysisProvider | None = None) -> None:
        self.provider = provider or get_m1_provider()

    def analyze(self, input_data: InterviewAnswerInput) -> AnswerAnalysis:
        """Synchronously evaluate an interview turn answer.

        Does NOT mutate input_data.context.
        """
        logger.info(
            "m1_analyzing_turn",
            answer_id=input_data.answer_id,
            agent_id=input_data.agent_profile.agent_id,
            competencies=input_data.agent_profile.focal_competencies,
        )

        analysis = self.provider.analyze_answer(input_data)
        return analysis

    async def analyze_async(self, input_data: InterviewAnswerInput) -> AnswerAnalysis:
        """Asynchronously evaluate an interview turn answer.

        Does NOT mutate input_data.context.
        """
        logger.info(
            "m1_analyzing_turn_async",
            answer_id=input_data.answer_id,
            agent_id=input_data.agent_profile.agent_id,
            competencies=input_data.agent_profile.focal_competencies,
        )

        analysis = await self.provider.analyze_answer_async(input_data)
        return analysis


# Global default analyzer instance
m1_analyzer = M1InterviewAnalyzer()
