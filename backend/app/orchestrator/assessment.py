"""Finite assessment progress is separate from demonstrated competency mastery."""

from __future__ import annotations

import re
from typing import Any

from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.models.enums import DifficultyLevel


def assessed_insufficient_competencies(context: InterviewAIContext) -> set[str]:
    return set(context.metadata.get("assessed_insufficient", {}))


def _standalone_inability(answer: str) -> bool:
    """An admission without an attempted answer, not ordinary uncertainty.

    A score cannot turn a short relevant fact into an inability to answer.
    Match the complete utterance so "I don't know X, but I implemented Y"
    remains an answer, and do not assess unfinished speech as an admission.
    """
    if re.search(r"(?:[—–-]|\.{3}|…)\s*$", answer):
        return False
    filler = r"(?:okay|ok|sorry|actually|honestly|unfortunately|well|so|um|uh)"
    admission = re.compile(
        r"(?:(?:i )?(?:do not|don't) know(?: (?:the answer|how to (?:answer|explain|do) (?:this|that|it)))?"
        r"|i (?:cannot|can't|am unable to) (?:answer|explain|do)(?: (?:this|that|it|the question|the task))?"
        r"|(?:i have )?no idea)"
    )
    clauses = []
    for clause in re.split(r"[.!?;]+", answer.lower().replace("’", "'")):
        text = " ".join(re.sub(r"[^\w\s']", " ", clause).split())
        text = re.sub(rf"^(?:{filler} )+|(?: {filler})+$", "", text)
        text = re.sub(rf"^i (?:{filler} )+", "i ", text)
        if text:
            clauses.append(text)
    return bool(clauses) and all(admission.fullmatch(clause) for clause in clauses)


def _supported_legacy_inability(analysis: AnswerAnalysis, competency: str) -> bool:
    """Compatibility for callers without raw speech requires cited inability.

    Evidence describing a contribution, even alongside an inability, means
    there is more to probe. Missing evidence or a low score alone is not proof.
    """
    evidence = [item for item in analysis.evidence if item.competency == competency]
    if not evidence:
        return False
    inability = re.compile(
        r"^(?:(?:the )?candidate|they|he|she|i)?\s*"
        r"(?:could not|couldn't|cannot|can't|did not|does not|do not|don't|"
        r"was unable to|is unable to|unable to)\s+(?:yet\s+)?"
        r"(?:explain|answer|demonstrate|describe|identify|perform|solve|do|know)\b",
        re.IGNORECASE,
    )
    for item in evidence:
        signal = item.signal.strip().replace("’", "'")
        if not (_standalone_inability(signal) or inability.search(signal)):
            return False
        if re.search(r"\b(?:but|however|although|and)\b", signal, re.IGNORECASE):
            return False
    evidence_ids = {item.id for item in evidence}
    return any(
        finding.competency_id == competency
        and bool(evidence_ids.intersection(finding.evidence_ids))
        and inability.search(finding.assessment.strip().replace("’", "'"))
        for finding in analysis.competency_findings
    )


def plan_insufficient_assessment(
    context: InterviewAIContext, analysis: AnswerAnalysis,
    current_question: str | None = None,
    current_answer: str | None = None,
) -> dict[str, dict[str, Any]]:
    """An explicit inability to answer an offered simple task establishes a gap.

    Low scores and brief or partial evidence do not establish inability. Other
    answers retain the finite distinct-objective budget before closing a gap.
    Broad opening questions and clarification controls have no objective ID.
    """
    previous = next((question for question in reversed(context.question_history)
        if question.agent_id == context.current_agent_id
        and (not current_question or question.question_text == current_question)), None)
    if not previous or not previous.metadata.get("objective_id"):
        return {}
    if previous.difficulty != DifficultyLevel.EASY or analysis.confidence < 0.7:
        return {}
    if analysis.overall_performance >= 0.45 or analysis.contradiction_detected:
        return {}
    if previous.metadata.get("answered_by"):
        return {}
    unable = (_standalone_inability(current_answer) if current_answer is not None
              else _supported_legacy_inability(analysis, previous.competency))
    if not unable:
        return {}
    return {previous.competency: {
        "status": "ASSESSED_INSUFFICIENT", "reason": "insufficient_response_to_simple_objective",
        "objective_id": previous.metadata["objective_id"], "answer_id": analysis.answer_id,
        "performance": analysis.overall_performance, "confidence": analysis.confidence,
        "missing_information": list(analysis.missing_information),
        "evidence_ids": [e.id for e in analysis.evidence if e.competency == previous.competency],
    }}


def exhausted_assessment(analysis: AnswerAnalysis) -> dict[str, Any]:
    return {
        "status": "ASSESSED_INSUFFICIENT", "reason": "distinct_objectives_exhausted",
        "answer_id": analysis.answer_id, "performance": analysis.overall_performance,
        "confidence": analysis.confidence, "missing_information": list(analysis.missing_information),
        "evidence_ids": [e.id for e in analysis.evidence],
    }
