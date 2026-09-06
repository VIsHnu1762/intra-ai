"""Deterministic adaptive decision policies for Intra AI Meta-Orchestrator."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Optional
from app.agents.models import AgentProfile
from app.agents.registry import AgentRegistry
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.models.enums import DifficultyLevel

# Canonical progression order
DIFFICULTY_STEPS: list[DifficultyLevel] = [
    DifficultyLevel.EASY,
    DifficultyLevel.MEDIUM,
    DifficultyLevel.HARD,
    DifficultyLevel.EXPERT,
]


def clamp_difficulty(
    target: DifficultyLevel,
    min_diff: DifficultyLevel,
    max_diff: DifficultyLevel,
) -> DifficultyLevel:
    """Clamp a target difficulty between agent profile min and max bounds."""
    try:
        min_idx = DIFFICULTY_STEPS.index(min_diff)
        max_idx = DIFFICULTY_STEPS.index(max_diff)
        target_idx = DIFFICULTY_STEPS.index(target)

        if min_idx > max_idx:
            min_idx, max_idx = max_idx, min_idx

        clamped_idx = max(min_idx, min(max_idx, target_idx))
        return DIFFICULTY_STEPS[clamped_idx]
    except ValueError:
        return target


def get_effective_missing_competencies(
    context: InterviewAIContext,
    agent_profile: AgentProfile,
) -> list[str]:
    """Determine remaining competencies requiring evaluation in this interview.

    Prevents turn-0 false completions when an interview is initialized without an
    explicit missing_competencies list. If missing_competencies is empty and no
    competencies have been evaluated yet, defaults to the active agent's focal competencies.
    """
    if context.missing_competencies:
        return [c for c in context.missing_competencies if c not in context.evaluated_competencies and not context.is_competency_sufficiently_asked(c)]

    # If missing_competencies was never explicitly provided and interview has no progress yet,
    # target competencies default to active agent's focal competencies
    if not context.evaluated_competencies and not context.accumulated_evidence:
        return list(agent_profile.focal_competencies)

    return []


def is_competency_sufficiently_evaluated(
    analysis: AnswerAnalysis,
) -> bool:
    """Assess whether the candidate demonstrated SUFFICIENT DEPTH on the current competency.

    Separates Performance from Coverage and Information Quality.
    A competency is sufficiently evaluated ONLY when:
    1. Performance is strong (>= 0.70).
    2. Not vague.
    3. No contradiction detected.
    4. No critical missing information gaps remain.
    5. Confidence is high (>= 0.70).
    """
    if analysis.contradiction_detected or analysis.vague:
        return False

    if analysis.overall_performance < 0.70:
        return False

    if analysis.missing_information and len(analysis.missing_information) > 0:
        return False

    if analysis.confidence < 0.70:
        return False

    # A score without grounded, linked M1 findings is not verified depth.
    grounded_ids = {e.id for e in analysis.evidence if e.signal.strip()}
    # Legacy M1 callers may supply grounded evidence without the optional
    # competency_findings list. Keep that valid contract; a naked score still
    # cannot establish depth.
    if not analysis.competency_findings:
        return bool(grounded_ids)
    return any(
        finding.confidence >= 0.70 and (
            bool(grounded_ids.intersection(finding.evidence_ids))
            or (not finding.evidence_ids and any(
                e.id in grounded_ids and normalize_competency(e.competency) == normalize_competency(finding.competency_id)
                for e in analysis.evidence
            ))
        )
        for finding in analysis.competency_findings
    )


def calculate_adaptive_difficulty(
    current_difficulty: DifficultyLevel,
    performance: float,
    has_sufficient_depth: bool,
    is_vague: bool,
    contradiction: bool,
    agent_profile: AgentProfile,
) -> DifficultyLevel:
    """Calculate next difficulty based on technical depth, not merely a numeric score.

    Rules:
    - Vague: Decrease one step to ask a simpler, concrete question.
    - Contradiction: Maintain difficulty while resolving the factual discrepancy.
    - Strong (>= 0.70) WITH sufficient depth: Increase difficulty (+1 step).
    - Strong (>= 0.70) WITHOUT sufficient depth: Maintain difficulty and probe deeper.
    - Weak (< 0.45): Decrease difficulty (-1 step) to probe fundamentals.
    - Moderate (0.45–0.70): Maintain difficulty.
    """
    try:
        curr_idx = DIFFICULTY_STEPS.index(current_difficulty)
    except ValueError:
        curr_idx = DIFFICULTY_STEPS.index(DifficultyLevel.MEDIUM)

    # A contradiction is an unresolved fact, not proof of low ability.
    if contradiction:
        next_diff = current_difficulty
    elif is_vague:
        next_diff = DIFFICULTY_STEPS[max(0, curr_idx - 1)]

    # 2. Strong performance with verified depth: increase difficulty
    elif performance >= 0.70 and has_sufficient_depth:
        new_idx = min(len(DIFFICULTY_STEPS) - 1, curr_idx + 1)
        next_diff = DIFFICULTY_STEPS[new_idx]

    # 3. Strong performance but shallow/missing information: maintain difficulty to probe depth
    elif performance >= 0.70 and not has_sufficient_depth:
        next_diff = current_difficulty

    # 4. Weak performance: reduce difficulty to probe core fundamentals
    elif performance < 0.45:
        new_idx = max(0, curr_idx - 1)
        next_diff = DIFFICULTY_STEPS[new_idx]

    # 5. Moderate performance: maintain difficulty
    else:
        next_diff = current_difficulty

    return clamp_difficulty(
        next_diff,
        min_diff=agent_profile.min_difficulty,
        max_diff=agent_profile.max_difficulty,
    )


def answered_question(context: InterviewAIContext, question_text: str | None):
    """Resolve the actual question, independently of M1's evidence labels."""
    if not question_text:
        return None
    normalized = " ".join(question_text.casefold().split())
    return next((question for question in reversed(context.question_history)
                 if question.agent_id == context.current_agent_id
                 and " ".join(question.question_text.casefold().split()) == normalized), None)


def plan_competency_difficulty(
    context: InterviewAIContext,
    analysis: AnswerAnalysis,
    agent_profile: AgentProfile,
    competency: str,
    current_question_text: str | None = None,
) -> tuple[DifficultyLevel, dict[str, Any]]:
    """Plan one bounded step without mutating context or adding a model call.

    History retains the level for each competency across persona switches. A
    reversal requires two consecutive opposing signals, so alternating strong
    and weak answers do not bounce difficulty every turn.
    """
    history = context.get_questions_for_competency(competency)
    previous = history[-1] if history else None
    before = previous.difficulty if previous else context.difficulty
    before = clamp_difficulty(before, agent_profile.min_difficulty, agent_profile.max_difficulty)
    findings = {normalize_competency(f.competency_id) for f in analysis.competency_findings}
    asked = answered_question(context, current_question_text)
    evaluates_target = (not findings or normalize_competency(competency) in findings
                        or (asked is not None and normalize_competency(asked.competency) == normalize_competency(competency)))
    policy = previous.metadata.get("difficulty_policy", {}) if previous else {}
    # On a known competency, evidence about another competency cannot alter its level.
    proposed = before if history and not evaluates_target else calculate_adaptive_difficulty(
        before, analysis.overall_performance,
        is_competency_sufficiently_evaluated(analysis), analysis.vague,
        analysis.contradiction_detected, agent_profile,
    )
    direction = DIFFICULTY_STEPS.index(proposed) - DIFFICULTY_STEPS.index(before)
    last_direction = policy.get("last_direction", 0)
    pending_direction = 0
    reason = "evidence_policy"
    if direction and last_direction and direction != last_direction:
        if policy.get("pending_direction") != direction:
            pending_direction = direction
            proposed = before
            reason = "await_second_reversal_signal"
    if proposed != before:
        last_direction = direction
    return proposed, {
        "competency": competency,
        "answer_id": analysis.answer_id,
        "before": before.value,
        "after": proposed.value,
        "performance": analysis.overall_performance,
        "confidence": analysis.confidence,
        "vague": analysis.vague,
        "contradiction": analysis.contradiction_detected,
        "evidence_ids": [e.id for e in analysis.evidence],
        "last_direction": last_direction,
        "pending_direction": pending_direction,
        "reason": reason,
    }


def normalize_competency(value: str) -> str:
    return re.sub(r"[\s-]+", "_", value.strip().lower())


_NON_SUBJECT_UTTERANCE = re.compile(
    r"\b(?:not sure|unsure|don['’]?t know|do not know|don['’]?t understand|do not understand|"
    r"can['’]?t answer|cannot answer|no idea|don['’]?t remember|do not remember|no experience)\b"
    r"|^(?:hello|hey|hi|good morning|good afternoon|good evening)\b"
    r"|^(?:yes|no|okay|ok|thanks|thank you|sorry|i see)[.!?]*$",
    re.IGNORECASE,
)


def substantive_subject(value: Any) -> str | None:
    """A conversational utterance or lack of knowledge is never a project name."""
    if not isinstance(value, str):
        return None
    subject = value.strip(" \t\r\n\"'")
    if not subject or len(subject.split()) > 12 or len(subject) > 160:
        return None
    if subject.lower().strip(".!?") in {"unknown", "none", "n/a", "unclear", "not provided"}:
        return None
    # Provider metadata may contain a truncated answer instead of a noun
    # phrase. Neither a discourse opener nor a finite clause names a project.
    if re.search(r"[,!?;]|\b(?:i|we|you|my|our|your|is|are|was|were|have|has|had|did|would|could|should)\b", subject, re.IGNORECASE):
        return None
    if re.match(r"^(?:so|well|actually|basically|for|regarding|when|because|then|and|but|it|this|that)\b", subject, re.IGNORECASE):
        return None
    return None if _NON_SUBJECT_UTTERANCE.search(subject) else subject


def choose_evidence_subject(
    analysis: AnswerAnalysis,
    context: InterviewAIContext,
    competency: str | None = None,
) -> str | None:
    """Use a substantive current subject, then the latest real prior example."""
    evidence = [*analysis.evidence, *reversed(context.accumulated_evidence)]
    for item in evidence:
        if competency and normalize_competency(item.competency) != normalize_competency(competency):
            continue
        # M1 can attach a familiar noun to an admission of ignorance; that
        # admission still does not introduce an example to reference.
        if _NON_SUBJECT_UTTERANCE.search(item.signal):
            continue
        subject = substantive_subject(item.metadata.get("subject"))
        if subject:
            return subject
    return None


def configured_agent_ids(context: InterviewAIContext, registry: AgentRegistry) -> set[str]:
    """Resolve the session roster; absent metadata keeps standalone N-agent use."""
    selected = next((context.metadata[key] for key in ("configured_agent_ids", "allowed_agent_ids", "agent_ids") if key in context.metadata), None)
    if selected is None:
        return set(registry.list_agent_ids())
    return {str(agent_id).strip().lower() for agent_id in selected if registry.has_agent(str(agent_id))}


def question_was_asked(question: str, history: list[Any], current_question: str | None = None) -> bool:
    """Catch exact and close rewordings without an extra inference request."""
    normalize = lambda text: " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    candidate = normalize(question)
    previous = [item.question_text for item in history]
    if current_question:
        previous.append(current_question)
    return any(
        candidate == normalize(text)
        or SequenceMatcher(None, candidate, normalize(text)).ratio() >= 0.86
        for text in previous if text
    )


def question_has_grounding(question: str, competency: str, analysis: AnswerAnalysis, turn_context: Any = None) -> bool:
    """Conservative lexical guard for generated questions against available facts.

    This supplements semantic grounding in the existing orchestrator prompt; it
    does not claim to prove semantic relevance. Unanchored questions fall back
    to the configured competency's explicit objective.
    """
    stop = {"what", "which", "where", "when", "would", "could", "should", "about", "your", "with", "that", "this", "have", "does", "their", "they", "were", "from", "into", "some", "explain", "example", "approach", "candidate", "statement", "details", "specific", "provide", "please", "tell", "more", "used", "using", "how", "why", "who", "did", "can", "was", "the", "and", "for", "you", "not", "are", "has", "had", "its", "one", "own"}
    def tokens(text: str) -> set[str]:
        # Preserve common inflections without treating unrelated words such as
        # integration and interaction as the same four-letter grounding token.
        result = set()
        for word in re.findall(r"\b[a-z]{3,}\b", text.lower()):
            if word in stop:
                continue
            if word.endswith("ation") and len(word) > 7:
                word = word[:-5] + "ate"
            elif word.endswith("ing") and len(word) > 6:
                word = word[:-3]
            elif word.endswith("ed") and len(word) > 5:
                word = word[:-2]
            elif word.endswith("s") and not word.endswith("ss") and len(word) > 4:
                word = word[:-1]
            result.add(word.removesuffix("e"))
        return result

    facts = [competency.replace("_", " "), *analysis.missing_information]
    facts.extend(e.signal for e in analysis.evidence)
    if analysis.contradiction_detected and analysis.contradiction_details:
        facts.append(analysis.contradiction_details)
    if turn_context is not None:
        facts.append(getattr(turn_context, "current_answer", "") or "")
        # A short answer such as "Through API" or a pronoun still refers to
        # the active question's concrete subject. Do not require restating it.
        facts.append(getattr(turn_context, "current_question", "") or "")
        job = getattr(turn_context, "job", None)
        facts.extend(getattr(job, "required_skills", []))
    return bool(tokens(question).intersection(tokens(" ".join(facts))))


def select_next_competency(
    missing_competencies: list[str],
    focal_competencies: list[str],
) -> Optional[str]:
    """Identify the highest-priority missing competency covered by the active agent."""
    for comp in missing_competencies:
        if comp in focal_competencies:
            return comp
    return None


def find_best_switch_agent(
    missing_competencies: list[str],
    current_agent_id: str,
    registry: AgentRegistry,
    allowed_agent_ids: set[str] | None = None,
) -> Optional[tuple[AgentProfile, str]]:
    """Generic N-agent selector finding the best alternative registered agent to evaluate remaining gaps.

    Does NOT hardcode persona transitions (e.g. Alex -> Jordan).
    Selects the registered agent with the greatest overlap with missing_competencies.
    """
    candidates = [
        agent for agent in registry.list_agents()
        if agent.agent_id.strip().lower() != current_agent_id.strip().lower()
        and (allowed_agent_ids is None or agent.agent_id in allowed_agent_ids)
    ]

    best_agent: Optional[AgentProfile] = None
    best_overlap_count = 0
    selected_target_comp: Optional[str] = None

    for agent in candidates:
        overlap = [c for c in missing_competencies if c in agent.focal_competencies]
        if len(overlap) > best_overlap_count:
            best_overlap_count = len(overlap)
            best_agent = agent
            selected_target_comp = overlap[0]

    if best_agent and selected_target_comp:
        return best_agent, selected_target_comp

    return None


def build_adaptive_probe_question(
    target_competency: str,
    missing_information: list[str],
    recommended_follow_up: str | None,
    current_agent: AgentProfile,
    evidence_subject: Optional[str] = None,
) -> str:
    """Select one spoken objective; internal gap labels are never speech."""
    from app.orchestrator.questions import objective_questions, spoken_question_is_clear, targeted_gap_objective
    evidence_subject = substantive_subject(evidence_subject)
    if recommended_follow_up and recommended_follow_up.strip():
        rf = recommended_follow_up.strip()
        if spoken_question_is_clear(rf, DifficultyLevel.MEDIUM):
            return rf
    targeted = targeted_gap_objective(normalize_competency(target_competency), missing_information)
    question = (targeted or objective_questions(normalize_competency(target_competency), DifficultyLevel.MEDIUM)[0])[1]
    prefix = f"You mentioned {evidence_subject}. " if evidence_subject and len(evidence_subject.split()) <= 4 else ""
    return prefix + question


def build_competency_question_options(
    competency: str,
    difficulty: DifficultyLevel,
    context: InterviewAIContext,
    analysis: AnswerAnalysis,
) -> list[tuple[str, str]]:
    """Return finite objective IDs and concrete questions, never raw gap labels."""
    from app.orchestrator.questions import objective_questions, targeted_gap_objective
    from app.interview_intelligence.provider import is_project_subject
    competency = normalize_competency(competency)
    current_subject = substantive_subject(context.metadata.get("current_candidate_subject"))
    project_candidates = [substantive_subject(context.metadata.get("current_candidate_project")), current_subject]
    project_candidates.extend(substantive_subject(item.metadata.get("subject"))
        for item in [*analysis.evidence, *reversed(context.accumulated_evidence)]
        if not _NON_SUBJECT_UTTERANCE.search(item.signal))
    # Redis, Kafka, or another newly mentioned dependency must not replace
    # the application under discussion. A genuinely new project can replace it.
    subject = (next((value for value in project_candidates if value and is_project_subject(value)), None)
               or current_subject or choose_evidence_subject(analysis, context, competency)
               or choose_evidence_subject(analysis, context))
    options = objective_questions(competency, difficulty)
    if difficulty != DifficultyLevel.EASY and (targeted := targeted_gap_objective(competency, analysis.missing_information)):
        options = [targeted, *(item for item in options if item[0] != targeted[0])]
    # Stay with an explicitly named project across competencies. This only
    # changes wording; objective identity and assessment limits remain fixed.
    project_subject = bool(subject and is_project_subject(subject))
    if project_subject and difficulty == DifficultyLevel.EASY:
        display = re.sub(r"\b(?:llm|ml|lms)\b", lambda match: match.group().upper(), subject, flags=re.IGNORECASE)
        project_variants = {
            "technical_depth": (
                f"What task does your {display} help someone complete?",
                f"What input does your {display} receive?",
                f"How did you check whether your {display} produced the right output?",
                f"What limitation did you find in your {display}?",
            ),
            "system_design": (
                f"What information does your {display} need to keep?",
                f"How does one request move through your {display}?",
                f"How would you find which part of your {display} is slow?",
                f"What should happen if one part of your {display} stops working?",
            ),
            "software_architecture": (
                f"What are the main parts of your {display}?",
                f"Which two parts of your {display} need to communicate?",
                f"How would you test one part of your {display} separately?",
                f"What change would be difficult to make in your {display}?",
            ),
            "scalability": (
                f"If twice as many people used your {display}, what would you check first?",
                f"What repeated work could your {display} avoid doing?",
                f"How would you check whether your {display} handles more requests?",
                f"Which part of your {display} might become overloaded first?",
            ),
            "debugging": (
                f"If your {display} returned a wrong result, what would you check first?",
                f"How would you reproduce a problem in your {display}?",
                f"What test would show that a fix to your {display} worked?",
                f"What could make a problem in your {display} difficult to reproduce?",
            ),
            "technical_decision_making": (
                f"What was one tool you chose for your {display}?",
                f"Why did you choose that tool for your {display}?",
                f"How did you check that the tool met your {display}'s needs?",
                f"What would make you reconsider that tool for your {display}?",
            ),
            "product_sense": (
                f"Who would use your {display}?",
                f"What problem does your {display} solve for that person?",
                f"How would you check whether your {display} helped that person?",
                f"What user need does your {display} leave unsolved?",
            ),
            "customer_understanding": (
                f"What difficulty would a user have without your {display}?",
                f"How would you learn what users need from your {display}?",
                f"How would you check whether users of your {display} share the same problem?",
                f"How would you handle conflicting feedback about your {display}?",
            ),
            "customer_impact": (
                f"What would become easier for someone using your {display}?",
                f"What number could show whether your {display} helped a user?",
                f"How would you check whether an improvement came from your {display}?",
                f"What negative effect could your {display} have on a user?",
            ),
            "prioritization": (
                f"What would you improve first in your {display}?",
                f"How would you choose between two improvements to your {display}?",
                f"How would you check whether your first improvement to your {display} was useful?",
                f"What would make you change priorities for your {display}?",
            ),
            "requirements_thinking": (
                f"What is one thing your {display} must do for a user?",
                f"How would you make that requirement for your {display} testable?",
                f"How would you check whether your {display} meets that requirement?",
                f"What would you do if a requirement for your {display} conflicted with a deadline?",
            ),
            "trade_off_decisions": (
                f"What was one choice you made when building your {display}?",
                f"What did you give up by making that choice for your {display}?",
                f"How would you check whether that choice helped your {display}?",
                f"What evidence would make you reverse that choice for your {display}?",
            ),
            "communication_of_product_decisions": (
                f"How would you explain a delay in your {display} to a teammate?",
                f"How would you explain a priority for your {display} to someone who disagrees?",
                f"How would you check that a teammate understood a decision about your {display}?",
                f"How would you handle disagreement about the next release of your {display}?",
            ),
        }
        if competency in project_variants:
            by_objective = dict(zip(("purpose", "apply", "verify", "limits"), project_variants[competency]))
            return [(key, by_objective[key.rsplit(":", 1)[-1]]) for key, _ in options]
        # An unrelated assessment example is a deliberate transition, rather
        # than silently presenting a new scenario as the candidate's project.
        return [(key, f"For a separate example: {question}") for key, question in options]
    # The subject is a supported prior claim, not an instruction or a guessed
    # project name. Its presence does not create another assessment objective.
    if subject and len(subject.split()) <= 4:
        options = [(objective, f"You mentioned {subject}. {question}") for objective, question in options]
    return options


def build_fresh_competency_question(
    competency: str,
    difficulty: DifficultyLevel,
    context: InterviewAIContext,
    analysis: AnswerAnalysis,
    current_question: str | None = None,
) -> str | None:
    """Select an unasked objective, independent of regenerated question wording."""
    asked = {item.metadata.get("objective_id") for item in context.get_questions_for_competency(competency)}
    return next((question for objective, question in
                 build_competency_question_options(competency, difficulty, context, analysis)
                 if objective not in asked and not question_was_asked(question, context.question_history, current_question)), None)


# Backwards compatibility alias
calculate_difficulty_adjustment = calculate_adaptive_difficulty
