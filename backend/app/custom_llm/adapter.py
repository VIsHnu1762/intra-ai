"""Custom LLM Adapter connecting Agora Agent Studio to M1 Intelligence and Meta-Orchestrator."""

from __future__ import annotations

import asyncio
import re
import time
from typing import AsyncIterator, Optional, Protocol
import uuid
import structlog

from app.agents.models import ActionType, AgentProfile, NextAction
from app.agents.registry import AgentRegistry, agent_registry
from app.core.config import settings
from app.custom_llm.classifier import (
    ClassificationResult,
    FastPathTurnClassifier,
    TurnIntent,
    get_fast_path_spoken_response,
    is_unfinished_asr_fragment,
    turn_classifier,
)
from app.custom_llm.timing import mark, report
from app.custom_llm.models import (
    ChatCompletionChunk,
    ChatCompletionChunkChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionResponseDelta,
    ChatCompletionResponseMessage,
    ChatCompletionChoice,
    ChatCompletionUsage,
    ChatMessage,
    InterviewTurn,
)
from app.interview_context.models import InterviewAIContext
from app.interview_context.store import InterviewSessionStore, interview_session_store
from app.interview_intelligence.analyzer import (
    M1InterviewAnalyzer,
    apply_analysis_to_context,
    m1_analyzer,
)
from app.interview_intelligence.models import InterviewAnswerInput
from app.interview_intelligence.provider import extract_key_subject, is_project_subject
from app.agent_context.builder import AgentTurnContextBuilder
from app.agent_context.personalization import candidate_first_name, relevant_cv_project, relevant_cv_skill
from app.knowledge_graph.service import KnowledgeGraphPersistenceService
from app.orchestrator.service import MetaOrchestrator, meta_orchestrator
from app.models.enums import DifficultyLevel
from app.orchestrator.questions import objective_questions

logger = structlog.stdlib.get_logger("intra_ai.custom_llm.adapter")



class ContextProvider(Protocol):
    """Protocol for resolving or injecting InterviewAIContext into an interview turn."""

    def get_context(self, turn: InterviewTurn) -> InterviewAIContext | None:
        """Return the InterviewAIContext for the given turn, or None if unattached."""
        ...


class PassThroughContextProvider:
    """Pass-through context provider that preserves explicitly provided context."""

    def get_context(self, turn: InterviewTurn) -> InterviewAIContext | None:
        return turn.context


class SessionContextProvider:
    """Context provider that resolves or initializes an InterviewAIContext from the session store."""

    def __init__(self, store: InterviewSessionStore, registry: AgentRegistry | None = None) -> None:
        self.store = store
        self.registry = registry or agent_registry

    def get_context(self, turn: InterviewTurn) -> InterviewAIContext | None:
        if turn.context is not None:
            return turn.context

        session_id = (turn.session_id or "").strip()
        if not session_id:
            session_id = f"sess-{uuid.uuid4().hex[:8]}"

        # x-agent-id is injected by router.py from the URL query parameter ?agent_id=<id>
        # set by agora_agent_service.py when starting each agent's pipeline.
        # Do NOT use a hardcoded fallback — if x-agent-id is absent, let the existing
        # session's current_agent_id stay authoritative (resolved below via get_or_create).
        requesting_agent_id = turn.raw_headers.get("x-agent-id") or ""
        round_id = turn.raw_headers.get("x-round-id", "technical")
        candidate_id = turn.raw_headers.get("x-candidate-id", f"cand-{session_id}")

        # If the session already exists in the store, return it directly without mutating
        # current_agent_id — the authoritative agent is whoever was set at session start.
        existing = self.store.get(session_id)
        if existing is not None:
            return existing

        # Session does not exist yet — create it with the requesting agent as the initial agent.
        # This should only happen on the very first turn of a fresh session.
        if not requesting_agent_id or not self.registry.has_agent(requesting_agent_id):
            requesting_agent_id = self.registry.list_agent_ids()[0]
            logger.warning(
                "session_created_without_agent_identity",
                session_id=session_id,
                fallback_agent=requesting_agent_id,
            )

        raw_missing = turn.raw_headers.get("x-missing-competencies") or turn.raw_headers.get("x-target-competencies")
        if raw_missing:
            missing_comps = [c.strip() for c in raw_missing.split(",") if c.strip()]
        else:
            profile = self.registry.get_profile(requesting_agent_id) if self.registry.has_agent(requesting_agent_id) else None
            missing_comps = list(profile.focal_competencies) if profile else ["system_design", "scalability"]

        return self.store.get_or_create(
            interview_id=session_id,
            candidate_id=candidate_id,
            round_id=round_id,
            agent_id=requesting_agent_id,
            missing_competencies=missing_comps,
        )


def extract_candidate_turn(messages: list[ChatMessage]) -> tuple[str, Optional[str]]:
    """Extract (candidate_answer, preceding_question) from the conversation history.

    Returns:
        candidate_answer: Latest user message plus any adjacent unfinished ASR clause.
        preceding_question: Content of the latest 'assistant' message preceding the user message.
    """
    latest_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        # Blank ASR callbacks are still the newest user turn. Looking past one
        # replays and scores a previous answer against an unrelated new request.
        if messages[i].role == "user":
            latest_user_idx = i
            break

    if latest_user_idx is None:
        return "", None

    candidate_answer = (messages[latest_user_idx].content or "").strip()

    # Agora may emit a tool/service name separately after an unfinished clause.
    # Reuse only adjacent, unassessed fragments from this request's history;
    # never cross a spoken assistant response or join complete previous answers.
    # Full restatements replace the prefix rather than duplicating it.
    fragments = []
    if candidate_answer:
        for prior in reversed(messages[max(0, latest_user_idx - 8):latest_user_idx]):
            text = (prior.content or "").strip()
            if not text:
                continue
            if prior.role != "user" or not is_unfinished_asr_fragment(text):
                break
            fragments.append(text)
    if fragments:
        try:
            join_fragments = not turn_classifier.classify(candidate_answer).is_control_turn
        except Exception:
            # Parsing must remain available when classification fails. The
            # processing gate owns its existing logged exception fallback.
            join_fragments = False
        for text in fragments if join_fragments else []:
            prefix = re.sub(r"(?:[—–-]|\.{3}|…)\s*$", "", text).strip()
            if not candidate_answer.casefold().startswith(prefix.casefold()):
                candidate_answer = prefix + " " + candidate_answer
            if len(candidate_answer) >= 10000:
                break

    preceding_question = None
    for j in range(latest_user_idx - 1, -1, -1):
        if messages[j].role == "assistant" and messages[j].content and messages[j].content.strip():
            preceding_question = messages[j].content.strip()
            break

    return candidate_answer, preceding_question


def generate_opening_question(profile: AgentProfile, context: InterviewAIContext) -> str:
    """Generate the initial interview opening question for the active agent."""
    comp = next((c for c in context.missing_competencies if c in profile.focal_competencies),
                profile.focal_competencies[0] if profile.focal_competencies else "your experience")
    job_title = context.metadata.get("job_title")
    cv_project = relevant_cv_project(context.metadata)
    project = cv_project
    if not project:
        project = next((e.metadata.get("subject") for e in context.accumulated_evidence
                        if e.source_agent_id != profile.agent_id and e.metadata.get("subject")), None)
    first_name = candidate_first_name(context.metadata)
    welcome = f"Hi {first_name}!" if first_name else "Hello!"
    introduction = f"{welcome} I'm {profile.display_name}, {profile.role}."
    objective = f" We'll discuss the {job_title} role." if job_title else ""
    example = f"your work on {project}" if project else "a recent project"
    if not project and (skill := relevant_cv_skill(context.metadata)):
        example += f" where you used {skill}"
    question = objective_questions(comp, DifficultyLevel.EASY)[0][1]
    if cv_project:
        # Every competency's opening must surface the selected CV project.
        # String replacement in generic bank prose silently omitted it for
        # debugging/coding, which contain no 'your project' placeholder.
        reference = f" Your CV mentions {cv_project}."
        if comp in {"technical_depth", "system_design", "software_architecture", "coding", "coding_problem_solving"}:
            question = "What is one feature you personally implemented in that project?"
        elif comp == "debugging":
            question = "What is one bug you investigated in that project?"
        elif comp in {"product_sense", "customer_understanding", "customer_impact"}:
            question = "Who was the main user of that project?"
        else:
            question = question.replace("a project you worked on", "that project").replace("your project", "that project")
        return f"{introduction}{objective}{reference} {question}"
    if comp in {"technical_depth", "system_design", "software_architecture"}:
        question = f"Thinking of {example}, what did you personally build?"
    else:
        question = question.replace("a project you worked on", example).replace("your project", example)
    return f"{introduction}{objective} {question}"


def generate_handoff_question(profile: AgentProfile, context: InterviewAIContext, competency: str | None) -> str:
    """Reference supported prior work, never the last clarification as a claim."""
    from app.orchestrator.policies import substantive_subject
    subject = substantive_subject(context.metadata.get("current_candidate_project")) or next((substantive_subject(item.metadata.get("subject"))
                    for item in reversed(context.accumulated_evidence)
                    if item.signal.strip() and substantive_subject(item.metadata.get("subject"))
                    and not FastPathTurnClassifier().classify(item.signal).is_control_turn), None)
    competency = competency or next(iter(profile.focal_competencies), "experience")
    reference = f" Earlier you described {subject}." if subject else ""
    if not subject and (project := relevant_cv_project(context.metadata)):
        reference = f" Your CV mentions {project}."
    question = objective_questions(competency, DifficultyLevel.EASY)[0][1]
    if reference:
        question = question.replace("a project you worked on", "that work")
    first_name = candidate_first_name(context.metadata)
    welcome = f"Thanks, {first_name}. " if first_name else ""
    return f"{welcome}I'm {profile.display_name}, {profile.role}.{reference} {question}"


def is_first_turn(messages: list[ChatMessage]) -> bool:
    """Determine if there are zero previous assistant questions in history."""
    previous_assistant_turns = [
        m for m in messages
        if m.role == "assistant" and m.content and m.content.strip()
    ]
    return len(previous_assistant_turns) == 0


def is_first_turn_or_greeting(
    candidate_answer: str,
    context: InterviewAIContext,
    active_agent_id: str | None = None,
    messages: Optional[list[ChatMessage]] = None,
) -> bool:
    """Determine if this turn represents the initial interview opening.

    Guarantees:
    - If evidence already exists in the context, this is NOT the opening turn.
    - If candidate provides a substantive technical answer, it is analyzed via M1, not treated as a greeting.
    - Short candidate answers (e.g. 'I don't know', 'One second') during an active interview do NOT trigger opening questions.
    - Agora's initial handshake (empty candidate content with 0 evidence) triggers the opening question.
    """
    # If any evidence or competency evaluation already exists, never restart opening
    if (context.accumulated_evidence or context.evaluated_competencies
            or context.question_history or context.metadata.get("active_interviewer_question")
            or context.metadata.get("native_greeting_pending")):
        return False

    # Allow the initial handshake, including a seeded welcome message, but do
    # not repeat an opening after a question or any earlier candidate answer.
    if not candidate_answer or not candidate_answer.strip():
        if context.question_history or context.metadata.get("active_interviewer_question"):
            return False
        return not any(
            (message.role == "user" and (message.content or "").strip())
            or (message.role == "assistant" and "?" in (message.content or ""))
            for message in (messages or [])
        )

    # Initial candidate greeting before any evidence exists
    cleaned = candidate_answer.strip().lower().rstrip(".!?,")
    greeting_tokens = {
        "hi", "hello", "hey", "ready", "begin", "start", "greetings",
        "morning", "afternoon", "meet", "jordan", "alex", "pleasure",
    }
    words = set(cleaned.replace(",", " ").replace("'", " ").split())
    if words.intersection(greeting_tokens) and len(words) <= 8 and (messages is None or len(messages) <= 2):
        return True

    return False


class CustomLLMAdapter:
    """Boundary adapter between external Agora Chat Completions requests and Intra AI systems.

    Connects Agora ASR/voice turns to:
    1. InterviewAIContext (short-term session store)
    2. M1 Interview Intelligence (answer analysis)
    3. Meta-Orchestrator (LangGraph decision engine)
    4. NextAction translation to assistant response
    5. Streaming SSE chunks back to Agora
    """

    def __init__(
        self,
        context_provider: Optional[ContextProvider] = None,
        session_store: Optional[InterviewSessionStore] = None,
        registry: Optional[AgentRegistry] = None,
        m1_service: Optional[M1InterviewAnalyzer] = None,
        orchestrator_service: Optional[MetaOrchestrator] = None,
        stream_delay_seconds: float = 0.0,
        m1_analyzer: Optional[M1InterviewAnalyzer] = None,
        orchestrator: Optional[MetaOrchestrator] = None,
        classifier: Optional[FastPathTurnClassifier] = None,
        kg_service: Optional[KnowledgeGraphPersistenceService] = None,
        background_kg_persistence: bool = False,
        context_builder: Optional[AgentTurnContextBuilder] = None,
    ) -> None:
        self.session_store = session_store or interview_session_store
        self.registry = registry or agent_registry
        self.context_provider = context_provider or SessionContextProvider(self.session_store, self.registry)
        self.m1_analyzer = m1_analyzer or m1_service or globals()["m1_analyzer"]
        self.orchestrator = orchestrator or orchestrator_service or globals()["meta_orchestrator"]
        self.classifier = classifier or globals().get("turn_classifier") or FastPathTurnClassifier()
        self.stream_delay_seconds = stream_delay_seconds
        self.kg_service = kg_service or KnowledgeGraphPersistenceService()
        self.background_kg_persistence = background_kg_persistence
        self.context_builder = context_builder or AgentTurnContextBuilder()
        self._background_tasks: set[asyncio.Task] = set()

    def parse_turn(
        self,
        request: ChatCompletionRequest,
        headers: Optional[dict[str, str]] = None,
        context: Optional[InterviewAIContext] = None,
    ) -> InterviewTurn:
        """Extract and structure an internal InterviewTurn from a ChatCompletionRequest."""
        raw_headers = {k.lower(): v for k, v in (headers or {}).items()}
        t0 = time.perf_counter()

        candidate_answer, _ = extract_candidate_turn(request.messages)

        # 1. Resolve stable candidate session ID from headers or request payload
        candidate_session_id = (
            raw_headers.get("x-agora-session-id")
            or raw_headers.get("x-session-id")
            or raw_headers.get("x-interview-id")
            or raw_headers.get("x-agora-channel-name")
            or raw_headers.get("x-channel-name")
            or raw_headers.get("x-agora-channel")
            or getattr(request, "channel", None)
            or getattr(request, "call_id", None)
            or getattr(request, "agent_uuid", None)
            or request.user
        )

        # Resolve the session ID. Use no default — if no valid identifier is found and there
        # is more than one session, generate a new isolated UUID rather than contaminating
        # an existing session with test-room-101 or another session's data.
        # The store's single-session shortcut (line 66-67 in store.py) handles the case where
        # there is exactly one active session (e.g. direct curl tests during development).
        session_id = self.session_store.resolve_interview_id(
            identifier=candidate_session_id,
            default=None,
        )
        if not session_id:
            # No usable identifier — generate a new isolated session ID.
            # This prevents contaminating real sessions with stale test state.
            session_id = f"sess-{uuid.uuid4().hex[:8]}"
            logger.warning(
                "[SESSION_IDENTITY_MISSING]",
                generated_session_id=session_id,
                candidate_session_id=candidate_session_id,
                note="No session_id in headers or query params — created isolated ephemeral session",
            )

        channel_name = (
            raw_headers.get("x-agora-channel-name")
            or raw_headers.get("x-channel-name")
            or raw_headers.get("x-agora-channel")
            or getattr(request, "channel", None)
            or (candidate_session_id if str(candidate_session_id or "").startswith("intra-") else None)
            or session_id
        )

        turn = InterviewTurn(
            messages=request.messages,
            latest_user_message=candidate_answer,
            session_id=session_id,
            channel_name=channel_name,
            model=request.model,
            stream=request.stream,
            context=context,
            raw_headers=raw_headers,
            metadata={"t0": t0},
        )

        mark(turn, "custom_llm_received")
        latest = next((m for m in reversed(request.messages) if m.role == "user"), None)
        turn.metadata["agora_turn_id"] = getattr(request, "turn_id", None) or (latest.turn_id if latest else None)
        if latest:
            turn.metadata["stt_final_timestamp_ms"] = latest.timestamp
            turn.metadata["candidate_speech_end_ms"] = (latest.metadata.get("speech_timing") or {}).get("speech_end_ms")

        if turn.context is None:
            turn.context = self.context_provider.get_context(turn)

        return turn

    async def process_turn_async(self, turn: InterviewTurn) -> tuple[str, Optional[NextAction]]:
        """Core cognitive loop: Turn Classification -> Fast Path OR Deep Reasoning (M1 -> Orchestrator)."""
        turn_logger = logger.bind(**self._turn_log_fields(turn))
        session_id = self.session_store.resolve_interview_id(turn.session_id)
        lock = self.session_store.get_lock(session_id)

        turn.metadata.setdefault("t0", time.perf_counter())
        mark(turn, "lock_wait_start")
        async with lock:
            mark(turn, "lock_acquired")
            # Load canonical context for this session
            if turn.context is not None:
                self.session_store.set(session_id, turn.context)
                context = turn.context
            else:
                context = self.session_store.get_or_create(session_id)
                turn.context = context

            # 1. Resolve active interviewer profile from authoritative session context
            curr_agent_id = context.current_agent_id.strip().lower()
            if not self.registry.has_agent(curr_agent_id):
                curr_agent_id = self.registry.list_agent_ids()[0]
                turn_logger.warning("unknown_agent_fallback", requested_agent=context.current_agent_id, fallback=curr_agent_id)
                context.current_agent_id = curr_agent_id

            if context.metadata.get("completed"):
                return "", None
            if context.metadata.get("pending_voice_action") and self.classifier.classify(turn.latest_user_message).intent != TurnIntent.END_INTERVIEW:
                return "", None
            profile = self.registry.get_profile(curr_agent_id)
            turn_logger = turn_logger.bind(agent_id=curr_agent_id)

            # 1b. Active-agent guard — only the current active agent may process a turn.
            # The requesting_agent_id comes from the ?agent_id= query parameter injected by
            # agora_agent_service.py into each agent's Custom LLM URL. If the requesting agent
            # is NOT the active agent, silently drop the turn by returning an empty SSE stream.
            # This prevents inactive agents (e.g. Jordan when Alex is active) from generating
            # competing responses, duplicate greetings, or overlapping voice output.
            requesting_agent_id = turn.raw_headers.get("x-agent-id", "").strip().lower()
            if requesting_agent_id and requesting_agent_id != curr_agent_id:
                turn_logger.info(
                    "[INACTIVE_AGENT_IGNORED]",
                    interview_id=context.interview_id,
                    requesting_agent_id=requesting_agent_id,
                    current_agent_id=curr_agent_id,
                    action="inactive_agent_ignored",
                )
                # Return empty string — generate_stream handles empty content gracefully
                return "", None

            # Log [AGORA_REQUEST], [CONTEXT_RESOLVE], [CONTEXT_LOAD] observability
            turn_logger.info(
                "[AGORA_REQUEST]",
                interview_id=context.interview_id,
                channel=turn.channel_name or context.interview_id,
                agent=curr_agent_id,
            )
            turn_logger.info(
                "[CONTEXT_RESOLVE]",
                interview_id=context.interview_id,
                agent=curr_agent_id,
                accumulated_evidence_count=len(context.accumulated_evidence),
                evaluated_competencies=context.evaluated_competencies,
            )
            turn_logger.info(
                "[CONTEXT_LOAD]",
                interview_id=context.interview_id,
                difficulty=context.difficulty.value if hasattr(context.difficulty, "value") else str(context.difficulty),
            )

            # 2. Extract candidate answer and preceding question
            candidate_answer, preceding_question = extract_candidate_turn(turn.messages)
            resumed_question = None
            t1 = time.perf_counter()
            turn.metadata["t1"] = t1

            # Silence/empty ASR is not a candidate answer or a request to repeat.
            # Preserve all context, including pause and active-question state.
            if not candidate_answer and not is_first_turn_or_greeting(
                candidate_answer, context, profile.agent_id, messages=turn.messages
            ):
                turn_logger.info("[EMPTY_CANDIDATE_TURN_IGNORED]", reason="no_transcribed_content")
                turn.metadata.update(t2=t1, t3=t1, t4=t1)
                return "", None

            # A greeting to the new interviewer is conversational, even though
            # the shared context already contains another agent's evidence.
            named_greeting = re.fullmatch(
                r"(?:hi|hello|hey)[,\s]+" + re.escape(profile.display_name) +
                r"(?:[,\s]+(?:nice|pleased|good) to meet you)?[.!\s]*",
                candidate_answer, flags=re.IGNORECASE,
            )
            if named_greeting:
                if (context.metadata.get("active_interviewer_question")
                        or context.metadata.get("native_greeting_pending")
                        or context.question_history):
                    # "Hi Alex" acknowledges the greeting; it is not a request
                    # to introduce the interviewer and repeat the question again.
                    return "I'm ready to listen. Take your time.", None
                opening = generate_opening_question(profile, context)
                context.metadata["active_interviewer_question"] = opening
                MetaOrchestrator.record_question(context, NextAction(
                    action=ActionType.ASK_QUESTION, target_agent_id=profile.agent_id,
                    competency=next(iter(profile.focal_competencies), "general"),
                    difficulty=context.difficulty, question_text=opening))
                return opening, None

            # A complete correction to the spoken project name is context, not
            # a technical contradiction or an attempt at the current question.
            from app.custom_llm.context_correction import project_name_correction, corrected_question
            correction = project_name_correction(candidate_answer)
            if correction:
                old_name, new_name = correction
                original_question = context.metadata.get("active_interviewer_question") or preceding_question
                question = corrected_question(original_question or "", old_name, new_name)
                context.metadata.update(
                    current_candidate_project=new_name,
                    current_candidate_subject=new_name,
                    candidate_context_correction={"previous_project": old_name, "active_project": new_name,
                                                  "source": "candidate_project_name_correction"},
                )
                if question:
                    context.metadata["active_interviewer_question"] = question
                    # Retain the question identity and coverage, recording its
                    # original wording so the transcript is still auditable.
                    for item in reversed(context.question_history):
                        if item.agent_id == curr_agent_id and item.question_text == original_question:
                            item.metadata.setdefault("original_spoken_question", original_question)
                            item.question_text = question
                            break
                self.session_store.set(context.interview_id, context)
                turn_logger.info("[PROJECT_NAME_CORRECTED]", interview_id=context.interview_id)
                return f"Thanks for correcting me. {question}" if question else "Thanks for correcting me. Please continue.", None

            # 3. Conversational Turn Understanding Gate
            try:
                classification = self.classifier.classify(candidate_answer, context)
            except Exception as exc:
                turn_logger.error("turn_classification_failed", error_type=type(exc).__name__, interview_id=context.interview_id)
                classification = ClassificationResult(
                    intent=TurnIntent.INTERVIEW_ANSWER,
                    confidence=0.0,
                    tier="error_fallback",
                    matched_rule="exception_fallback",
                )

            turn_logger.info(
                "[TURN_CLASSIFIED]",
                interview_id=context.interview_id,
                agent=curr_agent_id,
                intent=classification.intent.value,
                tier=classification.tier,
                confidence=classification.confidence,
                rule=classification.matched_rule,
            )

            # 4. Handle Fast-Path Control Turns (Bypass M1, Meta-Orchestrator, Zero Context Mutation)
            if classification.intent == TurnIntent.INCOMPLETE_ANSWER:
                turn_logger.info("[UNFINISHED_ANSWER_HELD]", agora_turn_id=turn.metadata.get("agora_turn_id"))
                return "", None

            service_pause = context.metadata.get("service_pause")
            if service_pause and classification.intent != TurnIntent.END_INTERVIEW:
                if classification.intent in {TurnIntent.CONTINUE_INTERVIEW, TurnIntent.INTERVIEW_ANSWER}:
                    if time.time() < service_pause["retry_at"]:
                        return ("The service is still unavailable. Please wait before continuing."
                                if classification.intent == TurnIntent.CONTINUE_INTERVIEW else ""), None
                    if classification.intent == TurnIntent.CONTINUE_INTERVIEW:
                        # An explicit retry processes the unevaluated answer,
                        # never the word "continue" as competency evidence.
                        candidate_answer = service_pause["answer"]
                        resumed_question = service_pause["question"]
                        classification = ClassificationResult(intent=TurnIntent.INTERVIEW_ANSWER,
                            confidence=1.0, tier="service_resume", matched_rule="retry_unevaluated_answer")
                    context.metadata.pop("service_pause", None)
                    context.metadata["paused"] = False

            if classification.is_control_turn:
                active_q = context.metadata.get("active_interviewer_question") or preceding_question
                if classification.intent == TurnIntent.END_INTERVIEW:
                    action = NextAction(action=ActionType.COMPLETE, target_agent_id=curr_agent_id,
                                        difficulty=context.difficulty,
                                        question_text="Absolutely. Thanks for your time today.",
                                        rationale="Candidate explicitly requested to end the interview.",
                                        metadata={"intent": "END_INTERVIEW", "completion_reason": "candidate_requested"})
                    context.metadata.update(completed=True, completion_reason="candidate_requested", paused=False,
                                            pending_voice_action=ActionType.COMPLETE.value, pending_voice_request_id=turn.turn_id)
                    self.session_store.set(context.interview_id, context)
                    return action.question_text, action
                if classification.intent == TurnIntent.CLARIFICATION:
                    from app.custom_llm.intent_policy import clarification_response
                    from app.orchestrator.policies import substantive_subject
                    active_competency = next((q.competency for q in reversed(context.question_history)
                                              if q.agent_id == curr_agent_id), None)
                    subject = substantive_subject(extract_key_subject(context.metadata.get("last_candidate_answer", "")))
                    subject = (substantive_subject(context.metadata.get("current_candidate_project"))
                               or subject or relevant_cv_project(context.metadata))
                    response_text = clarification_response(candidate_answer, active_q,
                        competency=active_competency, subject=subject, agent_role=profile.role)
                elif classification.intent == TurnIntent.CONTINUE_INTERVIEW:
                    context.metadata["paused"] = False
                    response_text = f"Of course. {active_q}" if active_q else generate_opening_question(profile, context)
                elif classification.intent == TurnIntent.GENERAL_CONVERSATION:
                    response_text = "You're welcome. Take your time." if "thank" in candidate_answer.lower() else "I'm here and ready to listen."
                elif classification.intent == TurnIntent.AUDIO_CHECK:
                    response_text = get_fast_path_spoken_response(TurnIntent.AUDIO_CHECK)
                elif classification.intent == TurnIntent.TIME_PAUSE:
                    context.metadata["paused"] = True
                    response_text = get_fast_path_spoken_response(TurnIntent.TIME_PAUSE)
                elif classification.intent == TurnIntent.REPEAT_QUESTION:
                    # Conversation history can end in an audio check or greeting;
                    # the session retains the actual unanswered question.
                    active_q = context.metadata.get("active_interviewer_question") or preceding_question
                    if active_q:
                        response_text = get_fast_path_spoken_response(
                            TurnIntent.REPEAT_QUESTION,
                            active_question=active_q,
                        )
                    else:
                        response_text = generate_opening_question(profile, context)
                else:
                    response_text = "Yes, let's continue."

                turn_logger.info(
                    "[FAST_PATH_RESPONSE]",
                    interview_id=context.interview_id,
                    agent=curr_agent_id,
                    intent=classification.intent.value,
                    response=response_text,
                )
                turn.metadata["t2"] = t1
                turn.metadata["t3"] = t1
                turn.metadata["t4"] = t1
                return response_text, None

            # A substantive answer resumes a requested pause without scoring the pause itself.
            context.metadata["paused"] = False
            # 5. Handle First Turn / Opening Greeting
            if is_first_turn_or_greeting(candidate_answer, context, profile.agent_id, messages=turn.messages):
                turn_logger.info("generating_opening_question", agent_id=profile.agent_id, session_id=context.interview_id)
                opening = generate_opening_question(profile, context)
                context.metadata["active_interviewer_question"] = opening
                MetaOrchestrator.record_question(context, NextAction(
                    action=ActionType.ASK_QUESTION, target_agent_id=profile.agent_id,
                    competency=next(iter(context.missing_competencies), next(iter(profile.focal_competencies), "general")),
                    difficulty=context.difficulty, question_text=opening))
                self.session_store.set(context.interview_id, context)
                turn.metadata["t2"] = t1
                turn.metadata["t3"] = t1
                turn.metadata["t4"] = t1
                return opening, None

            # Fast-path acknowledgements are assistant messages too, but do not
            # replace the unanswered interview question. Resolve this once so
            # analysis, routing, persistence, and outage retries share its identity.
            # An explicit service retry retains the question saved with that answer.
            answer_question = (
                resumed_question
                or context.metadata.get("active_interviewer_question")
                or preceding_question
                or generate_opening_question(profile, context)
            )

            # Read-only snapshots can run concurrently with the independent M1 pass.
            async def build_context():
                mark(turn, "context_start")
                try:
                    return await self.context_builder.build_turn_context_async(
                        context=context.model_copy(deep=True), agent_profile=profile,
                        current_question=answer_question,
                        current_answer=candidate_answer)
                except Exception as exc:
                    turn_logger.warning("agent_turn_context_build_failed", error_type=type(exc).__name__)
                    return None
                finally:
                    mark(turn, "context_complete")

            context_task = asyncio.create_task(build_context())
            # 7. Invoke M1 Interview Intelligence with independent error fallback
            mark(turn, "m1_start")
            t2 = time.perf_counter()
            turn.metadata["t2"] = t2
            m1_provider_name = getattr(settings, "M1_PROVIDER", "mock")
            if m1_provider_name == "gemini":
                m1_model_name = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
            elif m1_provider_name == "ollama":
                m1_model_name = getattr(settings, "OLLAMA_MODEL", "gpt-oss:20b")
            elif m1_provider_name == "groq":
                m1_model_name = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")
            elif m1_provider_name == "aicredits":
                m1_model_name = settings.AICREDITS_M1_MODEL or settings.AICREDITS_GPT5_NANO_MODEL
            elif m1_provider_name == "openai":
                m1_model_name = "gpt-4o"
            else:
                m1_model_name = "mock"

            try:
                # Let M1 see the latest positively stated project too. This is
                # an isolated snapshot: a cancelled turn cannot alter the
                # canonical topic before analysis/routing succeeds.
                analysis_context = context.model_copy(deep=True)
                candidate_subject = extract_key_subject(candidate_answer)
                if candidate_subject:
                    analysis_context.metadata["current_candidate_subject"] = candidate_subject
                    if is_project_subject(candidate_subject):
                        analysis_context.metadata["current_candidate_project"] = candidate_subject
                input_data = InterviewAnswerInput(
                    answer_id=f"ans-{uuid.uuid4().hex[:8]}",
                    question_text=answer_question,
                    answer_text=candidate_answer,
                    context=analysis_context,
                    agent_profile=profile,
                    job_description=context.metadata.get("job_description"),
                    candidate_profile=context.metadata.get("candidate_profile"),
                )
                turn_logger.info(
                    "[M1_START]",
                    provider=m1_provider_name,
                    provider_implementation=type(getattr(self.m1_analyzer, "provider", None)).__name__,
                    model=m1_model_name,
                    answer_id=input_data.answer_id,
                )
                try:
                    analysis = await self.m1_analyzer.analyze_async(input_data)
                    mark(turn, "m1_complete")
                    t3 = time.perf_counter()
                finally:
                    # Join context reads even on errors/cancellation; no orphan retrieval tasks.
                    if asyncio.current_task().cancelling():
                        context_task.cancel()
                    await asyncio.gather(context_task, return_exceptions=True)
                turn.metadata["t3"] = t3
                turn_logger.info(
                    "[M1_COMPLETE]",
                    answer_id=analysis.answer_id,
                    performance=round(analysis.overall_performance, 2),
                    latency_ms=round((t3 - t2) * 1000, 1),
                )
            except Exception as exc:
                turn_logger.error("m1_analysis_failed", error_type=type(exc).__name__, interview_id=context.interview_id)
                t3 = time.perf_counter()
                turn.metadata["t3"] = t3
                turn.metadata["t4"] = t3
                from app.custom_llm.service_pause import pause_for_service
                return pause_for_service(context, exc, stage="analysis", answer=candidate_answer,
                                         question=answer_question), None

            # 8. Stage analysis and routing against an isolated context. Agora
            # may cancel while the orchestrator runs because the candidate has
            # resumed speaking; that unfinished turn must not commit evidence,
            # coverage, difficulty, or an unspoken question to shared memory.
            canonical_context = context
            context = canonical_context.model_copy(deep=True)
            # A candidate's project mention is conversational context, not
            # scored evidence. Keep it even if M1 yields no evidence items.
            if subject := extract_key_subject(candidate_answer):
                context.metadata["current_candidate_subject"] = subject
                if is_project_subject(subject):
                    context.metadata["current_candidate_project"] = subject
            apply_analysis_to_context(analysis, context)
            turn_logger.info(
                "[CONTEXT_ANALYSIS_STAGED]",
                interview_id=context.interview_id,
                accumulated_evidence_count=len(context.accumulated_evidence),
                evaluated_competencies=context.evaluated_competencies,
                missing_competencies=context.missing_competencies,
            )

            # Attach current M1 findings to the independently retrieved snapshot.
            turn_context = context_task.result() if not context_task.cancelled() else None
            if turn_context is not None:
                turn_context.interview = context.model_copy(deep=True)
                turn_context.answer_analysis = analysis
                turn_context.current_question = input_data.question_text

            # 9. Invoke Meta-Orchestrator with independent error fallback
            mark(turn, "orchestrator_start")
            orch_start = time.perf_counter()
            turn_logger.info("[ORCHESTRATOR_START]", answer_id=analysis.answer_id)
            try:
                next_action = await self.orchestrator.decide_async(
                    context=context,
                    analysis=analysis,
                    current_question_text=input_data.question_text,
                    turn_context=turn_context,
                )
                mark(turn, "orchestrator_complete")
                t4 = time.perf_counter()
                turn.metadata["t4"] = t4
                turn_logger.info(
                    "[ORCHESTRATOR]",
                    answer_id=analysis.answer_id,
                    llm_used=bool(next_action.metadata.get("nemotron_used", False)),
                    action=next_action.action.value if hasattr(next_action.action, "value") else str(next_action.action),
                    target_agent=next_action.target_agent_id or "none",
                    difficulty=next_action.difficulty.value if hasattr(next_action.difficulty, "value") else str(next_action.difficulty),
                    latency_ms=round((t4 - orch_start) * 1000, 1),
                )
            except Exception as exc:
                turn_logger.error("orchestrator_decision_failed", error_type=type(exc).__name__, interview_id=context.interview_id)
                t4 = time.perf_counter()
                turn.metadata["t4"] = t4
                from app.custom_llm.service_pause import pause_for_service
                return pause_for_service(canonical_context, exc, stage="routing", answer=candidate_answer,
                                         question=input_data.question_text), None

            context.metadata["last_candidate_answer"] = candidate_answer
            context.metadata["last_m1_answer_id"] = analysis.answer_id
            MetaOrchestrator.record_assessment(context, next_action)
            # 10. Apply NextAction State Transitions to Context
            if next_action.difficulty:
                context.set_difficulty(next_action.difficulty)

            if next_action.action == ActionType.SWITCH_AGENT and next_action.target_agent_id:
                turn_logger.info(
                    "[AGENT_SWITCH]",
                    **{"from": curr_agent_id, "to": next_action.target_agent_id},
                )
                from app.sessions.service import interview_session_service
                live_session = interview_session_service.get_session(context.interview_id)
                if live_session is None:
                    context.switch_agent(next_action.target_agent_id)
                else:
                    # Keep the outgoing persona authoritative until its transition
                    # has been spoken and the physical handoff succeeds.
                    context.metadata["pending_voice_action"] = next_action.action.value
                    context.metadata["pending_voice_request_id"] = turn.turn_id

                # Construct shared handoff context for the target agent
                if turn_context and self.context_builder and self.registry.has_agent(next_action.target_agent_id):
                    target_profile = self.registry.get_profile(next_action.target_agent_id)
                    handoff_ctx = self.context_builder.build_handoff_context(turn_context, target_profile)
                    context.metadata["active_handoff_context"] = handoff_ctx.to_prompt_context()

            if next_action.action == ActionType.COMPLETE:
                context.metadata.update(completed=True, pending_voice_action=next_action.action.value,
                                        pending_voice_request_id=turn.turn_id)


            # 11. Format Assistant Response Text from NextAction
            q_text = (next_action.question_text or "").strip()
            if next_action.action == ActionType.ASK_QUESTION:
                response_text = q_text or "Could you elaborate on the technical implementation details?"
                context.metadata["active_interviewer_question"] = response_text
                MetaOrchestrator.record_question(context, next_action)

            elif next_action.action == ActionType.SWITCH_AGENT:
                target_id = next_action.target_agent_id or "interviewer"
                target_profile = self.registry.get_profile(target_id) if self.registry.has_agent(target_id) else None
                display = target_profile.display_name if target_profile else "our co-interviewer"
                response_text = (
                    q_text
                    or f"Thank you for sharing those insights. I will now hand over to {display} to continue our interview."
                )
                context.metadata["active_interviewer_question"] = response_text

            elif next_action.action == ActionType.COMPLETE:
                response_text = (
                    q_text
                    or "Thank you for your time today. That concludes our interview questions for this session. Have a great day!"
                )
                context.metadata["active_interviewer_question"] = response_text

            else:
                response_text = "Thank you. Let's continue."

            # Commit only once routing and response formatting both succeeded.
            # There is no await in this commit, and the session lock is held.
            # Retain the canonical model identity for existing readers/callers.
            for field_name in type(canonical_context).model_fields:
                setattr(canonical_context, field_name, getattr(context, field_name))
            context = canonical_context
            turn.context = canonical_context
            self.session_store.set(context.interview_id, context)
            turn_logger.info(
                "[CONTEXT_UPDATE]",
                interview_id=context.interview_id,
                accumulated_evidence_count=len(context.accumulated_evidence),
                evaluated_competencies=context.evaluated_competencies,
                missing_competencies=context.missing_competencies,
            )

            # 12. Knowledge Graph Persistence (Side-Effect Candidate Memory Projection)
            if self.kg_service:
                await self._persist_to_knowledge_graph_safe(
                    analysis=analysis,
                    context=context,
                    question_text=input_data.question_text,
                    answer_text=candidate_answer,
                    agent_id=curr_agent_id,
                    difficulty=next_action.difficulty if next_action else context.difficulty,
                )

            return response_text, next_action

    async def _persist_to_knowledge_graph_safe(
        self,
        analysis: AnswerAnalysis,
        context: InterviewAIContext,
        question_text: str,
        answer_text: str,
        agent_id: str,
        difficulty: Optional[DifficultyLevel | str] = None,
    ) -> None:
        """Safely persist turn evaluation to Knowledge Graph with complete error isolation."""
        try:
            async def persist():
                try:
                    await self.kg_service.persist_turn_evaluation_async(
                        analysis=analysis.model_copy(deep=True), context=snapshot,
                        question_text=question_text, answer_text=answer_text,
                        agent_id=agent_id, difficulty=difficulty)
                    logger.info("[KG_PERSIST_COMPLETE]", interview_id=snapshot.interview_id, answer_id=analysis.answer_id)
                except Exception as exc:
                    logger.error("[KG_PERSIST_FAILED]", interview_id=snapshot.interview_id,
                                 answer_id=analysis.answer_id, error_type=type(exc).__name__)
            snapshot = context.model_copy(deep=True)
            if self.background_kg_persistence:
                task = asyncio.create_task(persist())
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                await persist()
        except Exception as exc:
            logger.error(
                "knowledge_graph_persistence_failed",
                error=str(exc),
                interview_id=context.interview_id,
                answer_id=analysis.answer_id,
            )

    def _retain_task(self, coroutine) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def drain_background_tasks(self) -> None:
        if self._background_tasks:
            await asyncio.gather(*list(self._background_tasks), return_exceptions=True)

    def _response_lifecycle(self, turn, action, response_text):
        if action is None or action.action not in {ActionType.SWITCH_AGENT, ActionType.COMPLETE}:
            return None
        from app.sessions.service import interview_session_service
        from app.sessions.response_lifecycle import finish_response
        session = interview_session_service.get_session(turn.session_id or "")
        if not session:
            return None
        agent_id = session.current_agent_id
        cloud_id = session.started_agents.get(agent_id)
        if not cloud_id:
            return None
        response_started = int(time.time() * 1000)
        context = turn.context
        greeting = None
        if action.action == ActionType.SWITCH_AGENT:
            target = self.registry.get_profile(action.target_agent_id)
            greeting = generate_handoff_question(target, context, action.competency)
        async def apply_after_speech():
            result = await finish_response(
                turn.session_id, action, response_text,
                response_started_at_ms=response_started, expected_agent_id=agent_id,
                expected_agora_agent_id=cloud_id, greeting_text=greeting, request_id=turn.turn_id)
            if result.get("status") == "applied" and greeting and context:
                context.metadata["active_interviewer_question"] = greeting
                MetaOrchestrator.record_question(context, NextAction(
                    action=ActionType.ASK_QUESTION, target_agent_id=action.target_agent_id,
                    competency=action.competency, difficulty=DifficultyLevel.EASY,
                    question_text=greeting, metadata={"handoff": True,
                        "objective_id": objective_questions(action.competency, DifficultyLevel.EASY)[0][0]}))
        return apply_after_speech

    @staticmethod
    def _turn_log_fields(turn: InterviewTurn) -> dict:
        """Correlate stages without including transcript text or credentials."""
        return {
            "request_id": turn.turn_id,
            "session_id": turn.session_id,
            "channel": turn.channel_name,
            "requesting_agent_id": turn.raw_headers.get("x-agent-id"),
        }

    async def generate_stream(self, turn: InterviewTurn) -> AsyncIterator[str]:
        """Stream an OpenAI-compatible Server-Sent Events (SSE) response.

        Format:
            data: {"id": "...", "object": "chat.completion.chunk", ...}
            ...
            data: [DONE]
        """
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_ts = int(time.time())
        model_name = turn.model or "intra-ai"

        turn_logger = logger.bind(**self._turn_log_fields(turn), response_id=response_id)
        t0 = turn.metadata.get("t0", time.perf_counter())
        content_chunks = 0
        content_characters = 0
        turn.metadata.setdefault("t0", t0)
        mark(turn, "response_stream_start")
        turn_logger.info("[RESPONSE_STREAM_START]")

        try:
            # Execute cognitive chain
            response_text, next_action = await self.process_turn_async(turn)
            lifecycle = self._response_lifecycle(turn, next_action, response_text)

            # 1. Initial chunk: announce assistant role
            initial_chunk = ChatCompletionChunk(
                id=response_id,
                created=created_ts,
                model=model_name,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionResponseDelta(role="assistant", content=""),
                        finish_reason=None,
                    )
                ],
            )
            yield f"data: {initial_chunk.model_dump_json()}\n\n"

            t2 = turn.metadata.get("t2", t0)
            t3 = turn.metadata.get("t3", t2)
            t4 = turn.metadata.get("t4", t3)
            t5_first_token = None

            # 2. Content chunks: stream words (skip if response is empty — e.g. inactive agent guard)
            words = response_text.split(" ") if response_text.strip() else []
            for idx, word in enumerate(words):
                token = word if idx == 0 else f" {word}"
                if self.stream_delay_seconds > 0:
                    await asyncio.sleep(self.stream_delay_seconds)

                if t5_first_token is None:
                    mark(turn, "first_response_chunk_sent")
                    t5_first_token = time.perf_counter()
                    ttft_ms = (t5_first_token - t0) * 1000
                    m1_ms = (t3 - t2) * 1000
                    orch_ms = (t4 - t3) * 1000
                    turn_logger.info(
                        "[RESPONSE_STREAM]",
                        ttft_ms=round(ttft_ms, 1),
                        m1_ms=round(m1_ms, 1),
                        orch_ms=round(orch_ms, 1),
                    )

                chunk = ChatCompletionChunk(
                    id=response_id,
                    created=created_ts,
                    model=model_name,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=ChatCompletionResponseDelta(content=token),
                            finish_reason=None,
                        )
                    ],
                )
                content_chunks += 1
                content_characters += len(token)
                yield f"data: {chunk.model_dump_json()}\n\n"

            # 3. Terminal chunk: finish_reason="stop"
            final_chunk = ChatCompletionChunk(
                id=response_id,
                created=created_ts,
                model=model_name,
                choices=[
                    ChatCompletionChunkChoice(
                        index=0,
                        delta=ChatCompletionResponseDelta(),
                        finish_reason="stop",
                    )
                ],
            )
            # Retain the observer before either terminal marker: consumers may
            # close immediately on finish_reason or [DONE]. It still waits for
            # confirmed Agora speech completion before changing cloud agents.
            if lifecycle:
                self._retain_task(lifecycle())
            mark(turn, "response_stream_complete")
            report(turn)
            t6 = time.perf_counter()
            total_ms = (t6 - t0) * 1000
            # Exhausting the generator proves SSE was yielded to the HTTP transport;
            # it does not prove Agora consumed it, generated speech, or played audio.
            turn_logger.info(
                "[RESPONSE_STREAM_COMPLETE]",
                total_ms=round(total_ms, 1),
                content_chunks=content_chunks,
                content_characters=content_characters,
                boundary="http_response_iterator",
            )
            yield f"data: {final_chunk.model_dump_json()}\n\n"
            yield "data: [DONE]\n\n"

        except (asyncio.CancelledError, GeneratorExit):
            turn_logger.warning(
                "[RESPONSE_STREAM_CANCELLED]",
                total_ms=round((time.perf_counter() - t0) * 1000, 1),
                content_chunks=content_chunks,
                content_characters=content_characters,
            )
            raise
        except Exception as exc:
            turn_logger.error(
                "[RESPONSE_STREAM_FAILED]",
                error_type=type(exc).__name__,
                total_ms=round((time.perf_counter() - t0) * 1000, 1),
                content_chunks=content_chunks,
                content_characters=content_characters,
            )
            raise

    async def generate_response_async(self, turn: InterviewTurn) -> ChatCompletionResponse:
        """Generate a non-streaming OpenAI-compatible completion response asynchronously."""
        response_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_ts = int(time.time())

        response_text, action = await self.process_turn_async(turn)
        lifecycle = self._response_lifecycle(turn, action, response_text)
        if lifecycle:
            self._retain_task(lifecycle())

        return ChatCompletionResponse(
            id=response_id,
            created=created_ts,
            model=turn.model or "intra-ai",
            choices=[
                ChatCompletionChoice(
                    index=0,
                    message=ChatCompletionResponseMessage(
                        role="assistant",
                        content=response_text,
                    ),
                    finish_reason="stop",
                )
            ],
            usage=ChatCompletionUsage(
                prompt_tokens=sum(len((m.content or "").split()) for m in turn.messages),
                completion_tokens=len(response_text.split()),
                total_tokens=(
                    sum(len((m.content or "").split()) for m in turn.messages)
                    + len(response_text.split())
                ),
            ),
        )

    def generate_response(self, turn: InterviewTurn) -> ChatCompletionResponse:
        """Synchronous wrapper for generate_response_async."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # In an existing event loop, create a new task or run synchronous fallback
            return ChatCompletionResponse(
                id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
                created=int(time.time()),
                model=turn.model or "intra-ai",
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatCompletionResponseMessage(
                            role="assistant",
                            content="Could you elaborate on your experience with distributed systems?",
                        ),
                        finish_reason="stop",
                    )
                ],
            )
        return asyncio.run(self.generate_response_async(turn))

    def is_ready(self) -> bool:
        """Adapter readiness probe."""
        return True


# Default global adapter instance
custom_llm_adapter = CustomLLMAdapter(background_kg_persistence=True)
