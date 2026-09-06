"""Two-tier Conversational Turn Understanding Engine for Intra AI.

Classifies incoming candidate utterances into:
1. AUDIO_CHECK
2. TIME_PAUSE
3. REPEAT_QUESTION
4. INTERVIEW_ANSWER

Design Invariants:
- Zero external API / LLM calls (strictly in-process and deterministic).
- Ambiguous content falls back to INTERVIEW_ANSWER; explicit requests about the
  interview question are handled before technical vocabulary or ignorance guards.
- Zero mutation of InterviewAIContext.
- Does NOT make strategic interview decisions (competency, difficulty, next question, routing).
"""

from __future__ import annotations

from enum import Enum
import math
import re
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field
import structlog

from app.interview_context.models import InterviewAIContext

logger = structlog.stdlib.get_logger("intra_ai.custom_llm.classifier")


class TurnIntent(str, Enum):
    """Canonical turn intent taxonomy for conversational turn understanding."""

    AUDIO_CHECK = "AUDIO_CHECK"
    TIME_PAUSE = "TIME_PAUSE"
    REPEAT_QUESTION = "REPEAT_QUESTION"
    INTERVIEW_ANSWER = "INTERVIEW_ANSWER"
    END_INTERVIEW = "END_INTERVIEW"
    CLARIFICATION = "CLARIFICATION"
    CONTINUE_INTERVIEW = "CONTINUE_INTERVIEW"
    GENERAL_CONVERSATION = "GENERAL_CONVERSATION"
    INCOMPLETE_ANSWER = "INCOMPLETE_ANSWER"


class ClassificationResult(BaseModel):
    """Structured output of the Conversational Turn Understanding Engine."""

    model_config = ConfigDict(extra="ignore")

    intent: TurnIntent = Field(..., description="Classified turn intent.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence score.")
    tier: str = Field(..., description="Engine tier that produced the decision ('tier_1', 'tier_2', 'fallback').")
    matched_rule: Optional[str] = Field(default=None, description="Identifier of the rule or anchor matched.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Diagnostic classification metadata.")

    @property
    def is_control_turn(self) -> bool:
        """Return True if this turn is a conversational control turn that bypasses M1 evaluation."""
        return self.intent != TurnIntent.INTERVIEW_ANSWER


# ── Text Normalization ───────────────────────────────────────────────────────

def normalize_transcript(text: Optional[str]) -> str:
    """Normalize raw ASR transcript for robust pattern and vector matching.

    - Trims whitespace and normalizes case
    - Normalizes internal punctuation and contractions
    - Collapses repeated whitespace
    """
    if not text:
        return ""
    cleaned = text.strip().lower()
    # Replace curly apostrophes with standard single quote
    cleaned = cleaned.replace("’", "'").replace("`", "'")
    # Remove surrounding punctuation
    cleaned = re.sub(r"[^\w\s\']", " ", cleaned)
    # Collapse multiple spaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


# ── Substantive Content & Compound Utterance Guards ──────────────────────────

TECHNICAL_CONCEPTS: frozenset[str] = frozenset({
    "redis", "kafka", "postgres", "postgresql", "mysql", "mongodb", "cassandra",
    "dynamodb", "elasticsearch", "database", "databases", "db", "sharding",
    "partition", "partitions", "partitioning", "replica", "replicas", "replication",
    "cache", "caches", "caching", "invalidation", "microservice", "microservices",
    "kubernetes", "k8s", "docker", "cluster", "clusters", "latency", "throughput",
    "acid", "sql", "nosql", "schema", "endpoint", "endpoints", "api", "apis",
    "concurrency", "threads", "threading", "lock", "locking", "deadlock", "queue",
    "queues", "event", "events", "architecture", "tradeoff", "tradeoffs",
    "trade-off", "trade-offs", "pipeline", "load balancer", "proxy", "nginx",
    "grpc", "rest", "json", "index", "indexing", "indexes", "query", "queries",
    "table", "tables", "system design", "distributed", "backend", "frontend",
    "server", "servers", "node", "nodes", "broker", "brokers", "pubsub",
    "pub sub", "write model", "read model", "cqrs", "event sourcing",
    "consistent hashing", "pgbouncer", "connection pool", "pooling", "failover",
    "consensus", "raft", "paxos", "benchmark", "benchmarks", "deployment",
    "monitoring", "production", "consistency models", "eventual consistency",
    "sharded", "partitioned", "cached", "replicated",
})

IGNORANCE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b(?:i\s+)?don'?t\s+know\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+am|i'?m)\s+not\s+sure\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+)?haven'?t\s+(?:worked|used|touched|done|had)\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+)?don'?t\s+have\s+experience\b", re.IGNORECASE),
    re.compile(r"\bno\s+experience\s+with\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(?:worked|used|touched|implemented)\b", re.IGNORECASE),
    re.compile(r"\bno\s+idea\b", re.IGNORECASE),
)

SUBSTANTIVE_EXPLANATION_MARKERS: tuple[str, ...] = (
    "explain how", "explain why", "explain our", "explain the", "explaining how",
    "explaining why", "explaining the", "explaining our", "how we solved",
    "how we handled", "how we designed", "how we built", "how we implemented",
    "how we partitioned", "how we scaled", "how we configured", "and then i will",
    "and then i'll", "and i will explain", "and i'll explain",
)


def contains_technical_concepts(text: str) -> bool:
    """Check if the text contains explicit engineering vocabulary or substantive explanation markers."""
    lower_text = text.lower()
    tokens = set(re.findall(r"\b[a-z0-9_\-]+\b", lower_text))
    if tokens.intersection(TECHNICAL_CONCEPTS):
        return True
    # Check multi-word technical concepts
    for concept in TECHNICAL_CONCEPTS:
        if " " in concept and concept in lower_text:
            return True
    for marker in SUBSTANTIVE_EXPLANATION_MARKERS:
        if marker in lower_text:
            return True
    return False


def is_ignorance_statement(text: str) -> bool:
    """Check if the text is an admission of ignorance (substantive interview evidence)."""
    for pattern in IGNORANCE_PATTERNS:
        if pattern.search(text):
            return True
    return False


def is_unfinished_asr_fragment(text: str) -> bool:
    """Recognize a short unfinished clause, not every utterance ending in a dash.

    Agora may finalize ASR at a hesitation ("my code—", "the limitations
    were—"). Without an object/predicate there is nothing to assess yet.
    Complete claims, even with trailing pause punctuation, remain answers.
    """
    if not re.search(r"(?:[—–-]|\.{3}|…)\s*$", text):
        return False
    stem = re.sub(r"(?:[—–-]|\.{3}|…)\s*$", "", text).strip()
    # A long technical answer can still be cut off at its final object. Wait
    # for that object instead of grading the first segment and treating the
    # service/tool name that follows as an answer to the next question.
    if re.search(r"\b(?:like|such as|using|through|with)(?:\s+(?:a|an|the))?\s*$", stem, re.I):
        return True
    if re.search(r"[.!?;]", stem):
        return False  # Preserve any earlier complete statement in this turn.
    clause = re.sub(
        r"^(?:(?:okay|ok|sorry|actually|so|well|and|like|um|uh)\s+)+",
        "", normalize_transcript(stem),
    )
    noun = (
        r"(?:my|our|the) (?:(?:main|first|second|current|previous|own) )?"
        r"(?:code|implementation|project|approach|solution|limitations?|inputs?|"
        r"outputs?|results?|service|application|system)"
    )
    return bool(re.fullmatch(
        rf"(?:{noun}(?: (?:is|are|was|were|has|have|had))?|"
        r"(?:i|we) (?:am|are|was|were)|"
        r"(?:i|we) (?:used|built|implemented|designed|chose|created|developed|wrote|added|tested)"
        r"(?: (?:a|an|the|some|our|my))?)",
        clause,
    ))


def conversational_request(text: str) -> TurnIntent | None:
    """Recognize direct conversational requests before answer/technical guards.

    Match whole clauses and their subject/object, not isolated words like 'stop'.
    Reported, hypothetical and negated requests remain interview content.
    """
    raw_clauses: list[tuple[str, bool]] = []
    for sentence in re.finditer(r"([^.!?;]+)([.!?;]*)", text.lower().replace("’", "'")):
        parts = re.split(r"\bbut\b", sentence.group(1))
        raw_clauses.extend(
            (part, "?" in sentence.group(2) and index == len(parts) - 1)
            for index, part in enumerate(parts)
        )

    def clean_clause(clause: str) -> str:
        return re.sub(
            r"^(?:(?:okay|ok|sorry|actually|please|so|well|and|like|um|uh)\s+)+", "",
            normalize_transcript(clause),
        )

    # Scan every clause for END first. A clarification earlier in a compound
    # utterance must not override a later explicit request to end the interview.
    for raw_clause, _ in raw_clauses:
        clause = clean_clause(raw_clause)
        if re.fullmatch(r"(?:end|stop|finish) (?:the|this) interview(?: now| please)?", clause):
            return TurnIntent.END_INTERVIEW
        if re.match(r"(?:can|could|shall) we (?:please )?(?:end|stop|finish|wrap up)(?: the interview| this interview| this| here| now| please| for today)*$", clause):
            return TurnIntent.END_INTERVIEW
        if re.match(r"(?:i (?:want|need|have) to|i'd like to|i would like to|let's|let us|please) (?:end|stop|finish|wrap up)(?: the interview| this interview| this| here| now| please| for today)*$", clause):
            return TurnIntent.END_INTERVIEW
        if re.fullmatch(r"i (?:don't|do not) (?:want|wish) to continue(?: the interview| this interview| anymore| any more)?|i (?:need|have) to leave(?: now)?", clause):
            return TurnIntent.END_INTERVIEW

    for raw_clause, is_question in raw_clauses:
        clause = clean_clause(raw_clause)
        if re.fullmatch(r"(?:can|could) we (?:take|have) (?:a )?(?:short |quick )?break|(?:can|could) we pause(?: the interview)?", clause):
            return TurnIntent.TIME_PAUSE
        # A colon can separate an ASR topic preamble from the direct request.
        # Do not reinterpret reported or hypothetical speech as the candidate's
        # own request ("The customer asked: can you simplify?").
        reported = re.match(
            r"(?:if|when|suppose|imagine)\b|(?:i|we|he|she|they) (?:said|asked|say|ask)\b|"
            r"(?:the|my|our|a) (?:customer|user|client|interviewer|manager|colleague)\b.*\b(?:said|asked|says|asks)\b",
            clause,
        )
        if reported:
            continue
        # ASR self-repairs often separate the abandoned start from a direct
        # question with an em dash. Do not split hyphenated technical terms.
        for part in re.split(r":|[—–]|\s-\s", raw_clause):
            request = clean_clause(part)
            if is_question and request in {"what", "what exactly"}:
                return TurnIntent.CLARIFICATION
            if re.fullmatch(
                r"(?:what do you mean(?: by .+)?|what does .+ mean|"
                r"what (?:exactly |specifically )?(?:are|were) you asking(?: me)?(?: about)?(?: exactly| specifically)?|"
                r"(?:(?:one|a|an) )?(?:(?:simple|concrete|specific) )?example of what(?: exactly)?|"
                r"(?:can|could|would) you (?:please )?(?:clarify|simplify|rephrase|explain)(?: .+)?|"
                r"(?:clarify|simplify|rephrase)(?: (?:that|this|it|the question|your question))?(?: please)?|"
                r"i (?:can't|cannot|don't|do not|didn't|did not) understand "
                r"(?:what (?:you're|you are|you were) asking|what you (?:mean|asked)|(?:the|your|this) question)(?: me| here)?)",
                request,
            ):
                return TurnIntent.CLARIFICATION
            # Elliptical questions ask which object the interviewer means.
            # Match a short noun phrase, not an answer containing 'what'.
            # First-person explanations and reported/hypothetical clauses keep
            # the normal evidence path even when they end in a question mark.
            if (not re.match(r"(?:i|we|they|he|she|it|you)\b", request)
                    and re.fullmatch(
                        r"(?:for )?(?:the )?(?:[a-z][a-z-]* ){1,5}"
                        r"of (?:what|which (?:project|system|application|feature))(?: exactly)?",
                        request,
                    )):
                return TurnIntent.CLARIFICATION
            # A confirmation such as 'An example of the project I worked on?'
            # needs interrogative punctuation. The same clause as a statement
            # may introduce a substantive answer and must not bypass scoring.
            if is_question and re.fullmatch(
                r"(?:(?:one|a|an) )?(?:(?:simple|concrete|specific) )?example of "
                r"(?:a|the|my|our) (?:project|system|application|feature|work)"
                r"(?: (?:(?:that|which) )?(?:i|we) (?:worked on|built|developed|implemented))?",
                request,
            ):
                return TurnIntent.CLARIFICATION
            # Terminology confirmation is a question about the current wording,
            # not evidence that the candidate has explained the concept.
            if re.fullmatch(r"is (?:that|this|it) (?:called(?: as)?|known as|what you mean by) .+", request):
                return TurnIntent.CLARIFICATION
            if is_question and re.fullmatch(
                r"(?:that's|that is|this is|it's|it is) (?:called(?: as)?|known as) (?:a |an |the )?[\w ]+",
                request,
            ):
                return TurnIntent.CLARIFICATION
    normalized = normalize_transcript(text)
    if normalized in {"continue", "resume", "please continue", "please resume", "let's continue", "we can continue", "i'm ready to continue", "let's resume", "resume the interview", "continue the interview"}:
        return TurnIntent.CONTINUE_INTERVIEW
    if normalized in {"hi", "hello", "hey", "thank you", "thanks", "how are you", "nice to meet you"}:
        return TurnIntent.GENERAL_CONVERSATION
    return None


# ── Tier 1: Deterministic Matcher ───────────────────────────────────────────

TIER1_AUDIO_EXACT: frozenset[str] = frozenset({
    "am i audible",
    "am i audible now",
    "hi am i audible",
    "hello am i audible",
    "can you hear me",
    "can you hear me now",
    "can you hear me clearly",
    "are you able to hear me",
    "are you getting my audio",
    "did that come through",
    "is my audio working",
    "is my mic working",
    "can you hear my voice",
    "hello can you hear me",
    "hi can you hear me",
    "sorry did you hear that",
    "testing mic",
    "mic check",
})

TIER1_PAUSE_EXACT: frozenset[str] = frozenset({
    "give me a second",
    "give me a moment",
    "one second",
    "one moment",
    "hang on",
    "hang on a sec",
    "let me think",
    "just a moment",
    "give me a sec",
    "just a sec",
    "hold on",
    "wait a second",
    "wait a moment",
    "wait a sec",
    "one sec",
    "give me one second",
    "give me one moment",
    "let me think for a second",
    "let me think for a moment",
    "let me gather my thoughts",
    "sorry i need a moment",
    "i need a moment",
})

TIER1_REPEAT_EXACT: frozenset[str] = frozenset({
    "can you repeat the question",
    "could you repeat the question",
    "can you repeat that",
    "could you repeat that",
    "what was the question",
    "what did you ask",
    "sorry what was the question",
    "sorry what did you ask",
    "can you say that again",
    "could you say that again",
    "repeat the question please",
    "could you please repeat the question",
    "can you please repeat that",
    "sorry i didn't catch that",
    "sorry i did not catch that",
    "i didn't catch the question",
    "i did not catch the question",
    "can you repeat that last part",
    "could you repeat that last part",
    "could you say that last part again",
    "what was the question again",
    "sorry i missed the question",
    "could you go over the question again",
})


def match_tier1(normalized: str) -> Optional[tuple[TurnIntent, str]]:
    """Evaluate Tier 1 deterministic exact and anchored pattern matches."""
    if not normalized:
        return None

    # Check exact normalized phrase matches
    if normalized in TIER1_AUDIO_EXACT:
        return TurnIntent.AUDIO_CHECK, f"exact_audio:{normalized}"
    if normalized in TIER1_PAUSE_EXACT:
        return TurnIntent.TIME_PAUSE, f"exact_pause:{normalized}"
    if normalized in TIER1_REPEAT_EXACT:
        return TurnIntent.REPEAT_QUESTION, f"exact_repeat:{normalized}"

    # A common live request to hear the current question again. Match the
    # entire utterance: reported speech and a substantive answer mentioning
    # "come again" must still reach assessment.
    if re.fullmatch(
        r"(?:sorry )?(?:(?:can|could|would) you )?(?:please )?come again(?: please)?",
        normalized,
    ):
        return TurnIntent.REPEAT_QUESTION, "come_again_request"

    # Anchored prefixes for short phrases (<= 6 words)
    words = normalized.split()
    if len(words) <= 6:
        if normalized.startswith(("can you hear me", "am i audible", "are you able to hear me", "hi can you hear me", "hello can you hear me", "hi am i audible", "hello am i audible")):
            return TurnIntent.AUDIO_CHECK, "anchored_audio_prefix"
        if normalized.startswith(("give me a sec", "give me a moment", "let me think", "one second", "hang on a sec")):
            return TurnIntent.TIME_PAUSE, "anchored_pause_prefix"
        if normalized.startswith(("can you repeat", "could you repeat", "what was the question", "could you say that again")):
            return TurnIntent.REPEAT_QUESTION, "anchored_repeat_prefix"

    return None


# ── Tier 2: In-Process Semantic Vector Matcher ───────────────────────────────

CANONICAL_ANCHORS: dict[TurnIntent, list[str]] = {
    TurnIntent.AUDIO_CHECK: [
        "am i audible to you right now",
        "can you hear me clearly through the microphone",
        "sorry i think my mic cut out did that come through",
        "were you able to hear what i just said",
        "my headset glitched did you hear me",
        "my headset just glitched was my last sentence audible",
        "just checking if my microphone is working properly",
        "testing my audio connection can you hear me",
        "did my voice go through to you",
        "sorry my audio broke up could you hear that",
        "is the audio coming through on your end",
        "my mic seems weird can you hear me",
        "i think my headset glitched did you catch that",
        "are you getting my audio clearly",
        "sorry i think the audio dropped for a moment",
        "did you catch what i just said",
    ],
    TurnIntent.TIME_PAUSE: [
        "let me take a second to collect my thoughts",
        "give me a brief moment to think about this",
        "i am thinking about this give me a sec",
        "hang on a moment let me think",
        "give me a second to gather my thoughts",
        "let me think about how to explain this",
        "hold on one second please",
        "just taking a quick moment to think",
        "give me one minute to organize my thoughts",
        "sorry give me a second i am processing that",
        "let me collect my thoughts for a moment",
        "i am drawing a blank give me a moment",
        "just let me think through that",
        "one second i am trying to remember",
        "hold on let me think through this",
    ],
    TurnIntent.REPEAT_QUESTION: [
        "sorry could you please rephrase or repeat that",
        "i did not catch the last question could you repeat",
        "would you mind repeating what you just asked",
        "what exactly was the question again",
        "could you say the question one more time",
        "sorry i missed that could you repeat the question",
        "can you rephrase what you just asked me",
        "could you repeat that last part please",
        "what was that last question you asked",
        "i didn't quite catch the last part",
        "could you go over what you just asked",
        "sorry what did you just ask me",
    ],
}


def _build_char_and_word_ngrams(text: str) -> dict[str, float]:
    """Generate normalized char n-grams (3-4) and word n-grams (1-2) with TF weights."""
    features: dict[str, float] = {}
    tokens = text.split()

    # Word unigrams and bigrams
    for i, token in enumerate(tokens):
        features[f"w1:{token}"] = features.get(f"w1:{token}", 0.0) + 1.0
        if i < len(tokens) - 1:
            bi = f"w2:{token}_{tokens[i+1]}"
            features[bi] = features.get(bi, 0.0) + 1.5

    # Character 3-grams for phonetic / morphological variation
    compact = f" {text} "
    for i in range(len(compact) - 2):
        tri = f"c3:{compact[i:i+3]}"
        features[tri] = features.get(tri, 0.0) + 0.5

    # Normalize vector to unit length
    magnitude = math.sqrt(sum(v * v for v in features.values()))
    if magnitude > 0.0:
        for k in features:
            features[k] /= magnitude

    return features


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    """Compute cosine similarity between two unit-normalized sparse vectors."""
    dot_product = 0.0
    for k, val_a in vec_a.items():
        if k in vec_b:
            dot_product += val_a * vec_b[k]
    return max(0.0, min(1.0, dot_product))


class LocalSemanticMatcher:
    """In-process, zero-dependency semantic vector similarity matcher.

    Pre-computes sparse vector centroids for control intent clusters and evaluates
    candidate utterances via cosine similarity. Operates in < 0.1ms with 0 external calls.
    """

    def __init__(self, threshold: float = 0.60) -> None:
        self.threshold = threshold
        self._anchor_vectors: dict[TurnIntent, list[dict[str, float]]] = {}
        for intent, anchors in CANONICAL_ANCHORS.items():
            self._anchor_vectors[intent] = [
                _build_char_and_word_ngrams(normalize_transcript(a)) for a in anchors
            ]

    def score(self, normalized_text: str) -> tuple[Optional[TurnIntent], float, Optional[str]]:
        """Calculate maximum semantic similarity against all canonical control anchors.

        Returns:
            (matched_intent, confidence, matched_anchor)
        """
        if not normalized_text:
            return None, 0.0, None

        input_vec = _build_char_and_word_ngrams(normalized_text)
        best_intent: Optional[TurnIntent] = None
        best_score = 0.0
        best_anchor = None

        for intent, anchor_vecs in self._anchor_vectors.items():
            for idx, a_vec in enumerate(anchor_vecs):
                sim = _cosine_similarity(input_vec, a_vec)
                if sim > best_score:
                    best_score = sim
                    best_intent = intent
                    best_anchor = f"{intent.value}:{idx}"

        if best_score >= self.threshold and best_intent is not None:
            return best_intent, round(best_score, 3), best_anchor

        return None, round(best_score, 3), None


# ── Fast-Path Conversational Policy (Isolated) ───────────────────────────────

def get_fast_path_spoken_response(
    intent: TurnIntent,
    active_question: Optional[str] = None,
) -> str:
    """Produce isolated, deterministic conversational acknowledgment for control turns.

    Guarantees:
    - Zero strategic interview decisions.
    - Zero context mutation.
    - Preserves active interview state.
    """
    if intent == TurnIntent.AUDIO_CHECK:
        return "Yes, I can hear you clearly! Let's continue."
    if intent == TurnIntent.TIME_PAUSE:
        return "Sure, take your time."
    if intent == TurnIntent.REPEAT_QUESTION:
        if active_question and active_question.strip():
            return f"Sure! I asked: {active_question.strip()}"
        return "Sure, let me repeat the question."
    return ""


# ── Main Two-Tier Conversational Turn Classifier ─────────────────────────────

class FastPathTurnClassifier:
    """Two-tier Conversational Turn Understanding Engine.

    Tier 1: Deterministic exact & structural pattern matcher (< 0.05ms).
    Tier 2: In-process semantic vector similarity matcher (< 0.2ms).
    Fallback: Conservative INTERVIEW_ANSWER for content without an explicit
    conversational request, including admissions of technical ignorance.
    """

    def __init__(self, semantic_threshold: float = 0.60) -> None:
        self.semantic_matcher = LocalSemanticMatcher(threshold=semantic_threshold)

    def classify(
        self,
        text: Optional[str],
        context: Optional[InterviewAIContext] = None,
    ) -> ClassificationResult:
        """Classify candidate ASR text into a TurnIntent with confidence and tier tracking.

        Pure read-only operation: Never mutates context or global state.
        """
        raw_text = (text or "").strip()
        normalized = normalize_transcript(raw_text)

        # 1. Empty or whitespace input
        if not normalized:
            return ClassificationResult(
                intent=TurnIntent.INTERVIEW_ANSWER,
                confidence=1.0,
                tier="fallback",
                matched_rule="empty_input",
            )

        request_intent = conversational_request(raw_text)
        if request_intent is not None:
            return ClassificationResult(intent=request_intent, confidence=1.0,
                                        tier="tier_1", matched_rule="direct_conversational_request")

        # 2. Ignorance statements are substantive interview evidence
        if is_ignorance_statement(normalized):
            return ClassificationResult(
                intent=TurnIntent.INTERVIEW_ANSWER,
                confidence=1.0,
                tier="fallback",
                matched_rule="ignorance_substantive_signal",
            )

        if is_unfinished_asr_fragment(raw_text):
            return ClassificationResult(
                intent=TurnIntent.INCOMPLETE_ANSWER, confidence=1.0,
                tier="tier_1", matched_rule="unfinished_asr_clause",
            )

        # 3. Compound utterance and technical noun false-positive guard
        # If candidate utterance contains explicit technical nouns AND explanatory clauses,
        # it is strictly an interview answer.
        has_tech = contains_technical_concepts(normalized)
        word_count = len(normalized.split())

        # Disambiguate technical noun false positives:
        # e.g., "I need a second replica", "Can you hear me explain Redis"
        if has_tech:
            # Check if this is an explicit pure REPEAT request mentioning a topic
            # e.g., "Can you repeat the question about Redis replication?"
            # Must NOT contain an intent or clause to answer/explain/describe
            has_intent_to_answer = any(k in normalized for k in [
                "and then", "and i", "so i can", "explain", "explaining",
                "answer", "answering", "describe", "describing", "solved",
                "solving", "tell you", "walk through", "i want to", "i will",
                "then i", "to explain", "to answer",
            ])
            is_pure_repeat_with_topic = (
                normalized.startswith(("can you repeat", "could you repeat", "what was the question", "what did you ask", "repeat the question"))
                and not has_intent_to_answer
                and word_count <= 12
            )
            if is_pure_repeat_with_topic:
                return ClassificationResult(
                    intent=TurnIntent.REPEAT_QUESTION,
                    confidence=0.95,
                    tier="tier_1",
                    matched_rule="repeat_with_topic_mention",
                )
            return ClassificationResult(
                intent=TurnIntent.INTERVIEW_ANSWER,
                confidence=0.95,
                tier="fallback",
                matched_rule="technical_substantive_guard",
            )

        # 4. Tier 1: Deterministic Matcher
        tier1_match = match_tier1(normalized)
        if tier1_match is not None:
            intent, rule_name = tier1_match
            logger.debug("turn_classified_tier1", intent=intent.value, rule=rule_name, text=raw_text)
            return ClassificationResult(
                intent=intent,
                confidence=1.0,
                tier="tier_1",
                matched_rule=rule_name,
            )

        # 5. Tier 2: Local Semantic Matcher
        sem_intent, score, anchor_name = self.semantic_matcher.score(normalized)
        if sem_intent is not None:
            # Secondary compound guard: Long utterances (> 14 words) are conservative answers
            if word_count > 14 and sem_intent != TurnIntent.REPEAT_QUESTION:
                return ClassificationResult(
                    intent=TurnIntent.INTERVIEW_ANSWER,
                    confidence=score,
                    tier="fallback",
                    matched_rule="compound_length_conservative_guard",
                )

            logger.debug(
                "turn_classified_tier2",
                intent=sem_intent.value,
                confidence=score,
                anchor=anchor_name,
                text=raw_text,
            )
            return ClassificationResult(
                intent=sem_intent,
                confidence=score,
                tier="tier_2",
                matched_rule=anchor_name,
            )

        # 6. Conservative Fallback: INTERVIEW_ANSWER
        return ClassificationResult(
            intent=TurnIntent.INTERVIEW_ANSWER,
            confidence=max(0.5, 1.0 - score),
            tier="fallback",
            matched_rule="conservative_uncertainty_fallback",
        )


# Global default instance
turn_classifier = FastPathTurnClassifier()
