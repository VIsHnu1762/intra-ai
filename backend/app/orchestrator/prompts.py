"""GPT-OSS routing prompts for the Intra AI Meta-Orchestrator.

Responsibilities:
- Build structured routing prompts for GPT-OSS-20B via Groq.
- Provide evidence-driven cross-agent routing context.
- Never generate question text as primary output; routing decision is primary.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.models import AgentProfile
from app.agents.registry import AgentRegistry
from app.interview_context.models import InterviewAIContext
from app.interview_intelligence.models import AnswerAnalysis
from app.orchestrator.policies import (
    configured_agent_ids, is_competency_sufficiently_evaluated,
    normalize_competency, plan_competency_difficulty,
)


_ROUTING_SYSTEM_PROMPT = """\
You are the Meta-Orchestrator for Intra AI, an adaptive multi-agent voice interviewer.

Your responsibility is to determine the MOST VALUABLE next conversational move given 
the current interview state, M1's structured analysis, and the registered agent profiles.

You reason over:
- The latest candidate answer and M1's analysis of it
- The current active agent and their focal competencies  
- All other registered agents and their focal competencies
- What evidence has been accumulated and what is still missing
- The question history to prevent repeating the same information target
- Detected contradictions and vagueness that require resolution

Your decision output MUST be one of three canonical actions:
1. ASK_QUESTION — the current agent continues with a new question
2. SWITCH_AGENT — another agent takes over because a more valuable thread exists
3. COMPLETE — all configured interview objectives are sufficiently covered

DECISION PRIORITY ORDER (apply in this order, but do NOT blindly follow if reasoning shows otherwise):
1. Contradiction detected → ASK_QUESTION (current agent resolves contradiction first)
2. Vague/unclear answer → ASK_QUESTION (current agent clarifies before moving on)
3. Weak fundamentals → ASK_QUESTION (probe fundamentals with current agent)
4. Important missing information → ASK_QUESTION (current agent probes depth gap)
5. Strong-but-shallow → ASK_QUESTION (deeper exploration before moving on)
6. Meaningful cross-agent opportunity from latest answer → potentially SWITCH_AGENT
7. Current agent has unresolved focal competency → ASK_QUESTION on new competency
8. Current agent exhausted → SWITCH_AGENT to agent with unresolved focal competency
9. All objectives covered → COMPLETE

CROSS-AGENT ROUTING RULES:
A cross-agent opportunity exists when ALL of the following are true:
- The latest answer introduces a signal/topic/evidence relevant to another agent's focal competency
- That other agent has an unresolved competency related to that signal
- Following that thread is more valuable than the current agent's next normal question
- The current answer does NOT require immediate clarification or contradiction resolution

SWITCHING RULES:
- Switching must be driven by CANDIDATE EVIDENCE, not by question count or agent array order
- Do NOT switch simply because two or three questions have passed
- Do NOT hardcode "if current_agent is X then switch to Y"
- Do NOT switch during contradiction or vagueness — resolve those first
- Target agent must exist in the registry and be configured for this interview
- Any agent can switch to any other registered agent (A→B→C→A is valid)

STRONG ANSWER RULES:
- Strong AND sufficiently detailed → move to genuinely new competency
- Strong BUT shallow (missing depth) → deeper follow-up, do NOT switch
- Strong WITH cross-agent signal → potentially switch to agent with that competency

QUESTION REPETITION RULES:
- Check question_history before recommending a competency
- Check each question's follow_up.information_target, not just its wording.
  A new phrasing or project-name prefix does not create a new information target.
- The four purpose/apply/verify/limits objectives are finite. Select an unused
  objective for the competency; question_history.objective_id records consumed
  objectives even for older questions without a follow_up contract.
- If a competency already has SUFFICIENT exploration status, do NOT target it again
- If a competency has PARTIAL status, a genuine follow-up is valid
- Do NOT ask substantially the same question twice even with different wording
- Move to a new dimension (trade-offs, metrics, failure modes, observability) instead
- Within that dimension, select one fact about a component or feature the
  candidate actually mentioned. A dimension is an assessment category, not a
  request to describe the whole system.
- Use only a competency owned by the target agent and included in the job's
  configured required_competencies when provided. Never invent an unrelated topic.
- eligible_competencies_by_agent is the authoritative set of remaining choices:
  choose the exact competency ID from the target agent's list. Broader persona
  focal_competencies describe expertise; they do not expand these choices.
- selected_policy identifies the current priority and preferred target. For
  vagueness or probe_fundamentals, keep ASK_QUESTION with the current agent and
  exact preferred target. Ask one simple follow-up about what the candidate
  just said; you cannot switch agents or complete during these policies. For
  probe_missing_info, keep ASK_QUESTION with the current agent on that target
  and use the missing information to write a grounded follow-up. For
  advance_competency, an ASK_QUESTION must use the preferred target; a justified
  evidence-driven handoff must still use an eligible target agent/competency.
- difficulty_by_competency is deterministic policy, not a suggestion: word each
  question at the supplied level. EASY asks one simple concept or concrete step;
  MEDIUM asks application; HARD/EXPERT asks constraints and trade-offs.
- A weak or vague answer calls for a simpler single question, not an additional
  list of architecture, throughput, production, and failure-mode demands.

COMPLETION RULES:
- Do NOT complete because the current agent's competencies are exhausted
- Consider ALL configured interview objectives across ALL registered agents
- COMPLETE only when all relevant objectives are sufficiently covered across ALL agents

SPOKEN DIALOGUE RULES (question_text):
Use one short, concrete question per turn. At EASY difficulty use at most 32 words;
otherwise use at most 48 words. Ask about one named component, decision, user, or
small scenario. Do not read evaluation labels (such as "technical depth") or lists
of missing evidence to the candidate. A clarification is a request to rephrase,
not evidence of poor ability. Do not repeatedly demand an answer after the
candidate has demonstrated that they cannot answer a simple version.
While routing is your primary decision, you MUST generate the candidate-facing spoken dialogue in "question_text" corresponding to your decision:

1. When action is ASK_QUESTION:
- Provide a single, natural, spoken interviewer question directed to the candidate.
- Directly target the chosen competency and difficulty level.
- Before writing question_text, select metadata.follow_up as the question's
  information contract. Its answer_anchor MUST be a short exact quote from
  current_answer. Its information_target MUST be a noun phrase of 3-16 words
  naming ONE currently unanswered
  fact: a field, input, output, check, implementation step, reason for one
  decision, user need, or observed result. Its expected_answer MUST describe
  the bounded answer that would satisfy this question, such as "one field
  name" or "the first validation step". Use objective purpose, apply, verify,
  or limits to identify why this fact is needed. Do not combine several facts
  into the contract. The noun phrase must fit after "What is", for example
  "the candidate field used for authentication" or "the reason for choosing
  this storage format"; do not write another question or an instruction there.
  Do not use a whole-system overview or a list of topics as
  the expected answer. question_text must ask only for this information target.
- A project name alone is not a feature or failure scenario. If that is all
  the candidate has supplied, ask for ONE task or feature they personally
  worked on. Once they name a component, stay with that component for the next
  relevant unknown instead of asking about every part of the project.
- For example, after "authenticate and access the DB", ask "What does your
  API check before allowing database access?" The target is the access check;
  an answer naming that check satisfies it. Do not replace it with "What
  happens if part of your application fails?" After "I integrated Razorpay",
  ask for one step their own code performs in that integration, not how the
  payment provider's internals work. These illustrate scope; they are not a
  question script and must not be used for unrelated candidate answers.
- Ground the question in the candidate's latest response, accumulated evidence, or CV background.
- Prefer the latest answer's named component and the unanswered part of the
  current question. If they mention an SDK integration, first ask about their
  actual integration steps rather than assuming they built the provider's internals.
- If the project name or acronym is ambiguous, ask what the system helps its
  users do before assuming its architecture. An EASY question asks one concrete
  step; do not bundle an architecture walkthrough with ownership or integration.
- CV/JD background is not a script: the candidate's current explanation or
  correction takes precedence over a sample project or an earlier assumption.
- active_project, current_subject, and candidate_context_correction identify
  the current conversation context when supplied. Accept a correction of a
  project name or transcription. Do not insist on the old project, describe
  the correction as evasion, or dismiss it as "regardless of classification".
  Continue from the corrected context without inventing evidence of ability.
- A short relevant answer invites one specific follow-up. An admission of not
  knowing calls for a simpler step or a different remaining objective, not the
  same demand with a repeated project-name prefix. Respond to the answer before
  changing topics; do not invent work, tools, failure modes, or performance claims.
- Embody the active agent's persona (marked with "is_current": true in agent_registry): adopt their specific "role", "questioning_style", and "instructions".
- Do NOT use generic robotic wording. Speak authentically in the active agent's voice and perspective.
- Never output meta-commentary, reasoning, or JSON inside "question_text". It must be clean text ready for Text-to-Speech (TTS).

2. When action is SWITCH_AGENT:
- Provide a natural, spoken verbal handoff transition.
- Acknowledge the candidate's previous response.
- Explicitly introduce the incoming target agent by their display_name (matching target_agent_id).
- Mention the topic or competency the new interviewer will explore.
- Example: "Thank you for explaining your approach to caching. I will now hand over to Jordan to explore how you evaluated the product and customer impact of those changes."
- Must sound like a professional interviewer making a warm, seamless verbal handoff.

3. When action is COMPLETE:
- Provide a concise, warm, professional closing statement concluding the interview.
- Example: "Thank you for your time today and for sharing your experience. That concludes all our questions for this interview session. Have a great day!"

OUTPUT FORMAT:
Return a single valid JSON object with these fields:
{
  "action": "ASK_QUESTION" | "SWITCH_AGENT" | "COMPLETE",
  "target_agent_id": "<agent_id from registry>",
  "competency": "<competency string or null>",
  "rationale": "<explanation grounded in candidate evidence>",
  "cross_agent_opportunity": true | false,
  "trigger_signals": ["<signal from candidate answer>", ...],
  "unresolved_target_competencies": ["<competency>", ...],
  "question_text": "<candidate-facing spoken question, handoff, or closing statement>",
  "metadata": {
    "source_agent": "<current agent id>",
    "priority_applied": "<which priority rule was used>",
    "follow_up": {
      "answer_anchor": "<short exact quote from current_answer>",
      "information_target": "<3-16 word noun phrase naming one specific unanswered fact>",
      "expected_answer": "<bounded answer shape that satisfies this question>",
      "objective": "purpose" | "apply" | "verify" | "limits"
    }
  }
}

CONSTRAINTS:
- target_agent_id MUST be an agent_id that appears in the provided agent registry
- action MUST be exactly one of: ASK_QUESTION, SWITCH_AGENT, COMPLETE
- rationale MUST be non-empty and grounded in the candidate's actual answer
- question_text MUST be non-empty spoken dialogue suitable for immediate TTS rendering
- metadata.follow_up is REQUIRED for ASK_QUESTION and omitted for SWITCH_AGENT
  and COMPLETE. Select the contract and question in this same response; do not
  ask the candidate to create the contract or read its internal labels aloud.
- Do NOT invent agents not in the registry
- Do NOT output anything except the JSON object
"""


def _follow_up_contract(metadata: dict[str, Any]) -> dict[str, str] | None:
    """Keep the bounded target available without copying unrelated metadata."""
    contract = metadata.get("follow_up")
    if not isinstance(contract, dict):
        return None
    limits = {"answer_anchor": 240, "information_target": 240,
              "expected_answer": 160, "objective": 16}
    return {key: contract[key][:limit] for key, limit in limits.items()
            if isinstance(contract.get(key), str)} or None


def _serialize_question_history(context: InterviewAIContext) -> list[dict[str, Any]]:
    """Serialize question history to a compact form for Nemotron context."""
    return [
        {
            "agent_id": q.agent_id,
            "competency": q.competency,
            "question_text": q.question_text[:120] + "..." if len(q.question_text) > 120 else q.question_text,
            "difficulty": q.difficulty.value if hasattr(q.difficulty, "value") else str(q.difficulty),
            "exploration_status": q.exploration_status,
            "objective_id": q.metadata.get("objective_id"),
            "follow_up": _follow_up_contract(q.metadata),
        }
        for q in context.question_history[-10:]  # Last 10 questions are sufficient context
    ]


def _serialize_agent_profiles(
    agents: list[AgentProfile], context: InterviewAIContext,
    eligible: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Serialize agent profiles with coverage and persona information relative to current state."""
    result = []
    for agent in agents:
        result.append({
            "agent_id": agent.agent_id,
            "display_name": agent.display_name,
            "role": agent.role,
            "description": agent.description,
            "focal_competencies": agent.focal_competencies,
            "unresolved_focal_competencies": eligible[agent.agent_id],
            "questioning_style": agent.questioning_style,
            "instructions": agent.instructions,
            "min_difficulty": agent.min_difficulty.value,
            "max_difficulty": agent.max_difficulty.value,
            "allowed_actions": [action.value for action in agent.allowed_actions],
            "is_current": agent.agent_id.lower() == context.current_agent_id.lower(),
        })
    return result


def _serialize_evidence_summary(context: InterviewAIContext) -> list[dict[str, Any]]:
    """Serialize the last few evidence items for context."""
    recent = context.accumulated_evidence[-6:]  # Most recent 6 items
    return [
        {
            "competency": ev.competency,
            "signal": ev.signal[:100] + "..." if len(ev.signal) > 100 else ev.signal,
            "source_agent_id": ev.source_agent_id,
            "score": ev.score,
        }
        for ev in recent
    ]


def build_nemotron_routing_messages(
    context: InterviewAIContext,
    analysis: AnswerAnalysis,
    registry: AgentRegistry,
    current_question_text: str | None = None,
    turn_context: Any | None = None,
    unresolved_competencies: list[str] | None = None,
    selected_priority: str | None = None,
    selected_target_competency: str | None = None,
) -> list[dict[str, str]]:
    """Build the [system, user] message list for GPT-OSS-20B routing via Groq."""
    agents = [agent for agent in registry.list_agents() if agent.agent_id in configured_agent_ids(context, registry)]
    required = (
        getattr(getattr(turn_context, "job", None), "required_competencies", None)
        or context.metadata.get("required_competencies") or []
    )
    required_ids = {normalize_competency(c) for c in required}
    unresolved = {
        normalize_competency(c)
        for c in (unresolved_competencies if unresolved_competencies is not None else context.missing_competencies)
    }
    # Observed is not mastered: M1 may already have removed a partial finding
    # from missing_competencies before this prompt is built.
    if not is_competency_sufficiently_evaluated(analysis):
        unresolved.update(normalize_competency(f.competency_id) for f in analysis.competency_findings)
    unresolved.update(
        normalize_competency(q.competency) for q in context.question_history
        if not context.is_competency_sufficiently_asked(normalize_competency(q.competency))
    )
    if unresolved_competencies is None and not unresolved and not context.accumulated_evidence and not context.evaluated_competencies:
        unresolved.update(required_ids or {normalize_competency(c) for a in agents for c in a.focal_competencies})
    eligible = {
        agent.agent_id: [
            normalize_competency(c) for c in agent.focal_competencies
            if normalize_competency(c) in unresolved
            and (not required_ids or normalize_competency(c) in required_ids)
            and not context.is_competency_sufficiently_asked(normalize_competency(c))
        ]
        for agent in agents
    }
    preferred = normalize_competency(selected_target_competency or "") or None
    target_choices = (
        eligible.get(context.current_agent_id.strip().lower(), [])
        if selected_priority in {"probe_missing_info", "advance_competency", "vagueness", "probe_fundamentals"}
        else [c for choices in eligible.values() for c in choices]
    )
    if preferred not in target_choices:
        preferred = next(iter(target_choices), None)

    # Derive candidate signals from M1's analysis
    candidate_signals = []
    for ev in analysis.evidence:
        if ev.signal:
            candidate_signals.append(ev.signal[:100])
    for finding in analysis.competency_findings:
        candidate_signals.append(f"competency={finding.competency_id} confidence={finding.confidence:.2f}")

    user_state: dict[str, Any] = {
        "current_agent_id": context.current_agent_id,
        "current_question": current_question_text or "(not provided)",
        "active_project": context.metadata.get("current_candidate_project"),
        "current_subject": context.metadata.get("current_candidate_subject"),
        "m1_answer_analysis": {
            "overall_performance": analysis.overall_performance,
            "confidence": analysis.confidence,
            "vague": analysis.vague,
            "vague_reason": analysis.vague_reason,
            "contradiction_detected": analysis.contradiction_detected,
            "contradiction_details": analysis.contradiction_details,
            "missing_information": analysis.missing_information,
            "recommended_follow_up": analysis.recommended_follow_up,
            "competency_findings": [
                {
                    "competency_id": f.competency_id,
                    "assessment": f.assessment[:100],
                    "confidence": f.confidence,
                }
                for f in analysis.competency_findings
            ],
        },
        "candidate_signals_detected": candidate_signals,
        "interview_state": {
            "difficulty": context.difficulty.value if hasattr(context.difficulty, "value") else str(context.difficulty),
            "evaluated_competencies": context.evaluated_competencies,
            "missing_competencies": context.missing_competencies,
            "open_questions": context.open_questions[:5],
            "contradiction_count": len(context.detected_contradictions),
        },
        "agent_registry": _serialize_agent_profiles(agents, context, eligible),
        "eligible_competencies_by_agent": eligible,
        "selected_policy": {
            "priority": selected_priority,
            "target_competency": preferred,
        },
        "recent_evidence": _serialize_evidence_summary(context),
        "question_history": _serialize_question_history(context),
        "difficulty_by_competency": {
            profile.agent_id: {
                competency: plan_competency_difficulty(context, analysis, profile, competency, current_question_text)[0].value
                for competency in eligible[profile.agent_id]
            }
            for profile in agents
        },
    }

    if context.metadata.get("candidate_context_correction"):
        user_state["candidate_context_correction"] = context.metadata["candidate_context_correction"]

    # Inject Candidate CV facts, Job Context (JD), and Persistent Candidate Memory when turn_context is available
    if turn_context is not None:
        user_state["current_answer"] = (turn_context.current_answer or "")[:1800]
        user_state["current_round"] = context.current_round_id
        user_state["candidate_profile"] = {
            "candidate_id": turn_context.candidate.candidate_id,
            "name": turn_context.candidate.name,
            "source": turn_context.candidate.source,
            "claimed_skills": turn_context.candidate.skills[:10],
            "claimed_technologies": turn_context.candidate.technologies[:10],
            "experience_summary": [
                f"{exp.role} at {exp.company}"
                for exp in turn_context.candidate.experience[:3]
            ],
            "projects_summary": [
                f"{proj.name} ({', '.join(proj.technologies)})"
                for proj in turn_context.candidate.projects[:3]
            ],
            "resume_text_excerpt_unverified": str(turn_context.candidate.metadata.get("resume_excerpt") or "")[:4000],
        }

        user_state["job_context"] = {
            "job_id": turn_context.job.job_id,
            "title": turn_context.job.title,
            "company": turn_context.job.company,
            "description": (turn_context.job.description or "")[:1200],
            "required_skills": turn_context.job.required_skills[:10],
            "required_competencies": turn_context.job.required_competencies,
        }

        if turn_context.persistent_memory and turn_context.persistent_memory.evidence:
            user_state["persistent_interview_memory"] = [
                {
                    "evidence_id": ev.evidence_id,
                    "source_agent_id": ev.source_agent_id,
                    "round_id": ev.round_id,
                    "competency": ev.competency,
                    "score": ev.score,
                    "signal": ev.signal[:120],
                    "source_type": ev.source_type.value if hasattr(ev.source_type, "value") else str(ev.source_type),
                }
                for ev in turn_context.persistent_memory.evidence[:8]
            ]
        else:
            user_state["persistent_interview_memory"] = []

    user_prompt = (
        "Given the following structured interview state, determine the most valuable next "
        "conversational move. Apply the priority order from your instructions.\n\n"
        f"INTERVIEW STATE:\n{json.dumps(user_state, indent=2)}\n\n"
        "Return your routing decision as the specified JSON object. "
        "The target_agent_id MUST be one of: "
        f"{[a.agent_id for a in agents]}"
    )

    return [
        {"role": "system", "content": _ROUTING_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
