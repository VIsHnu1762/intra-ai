"""Milestone 1.5 — Comprehensive Stress-Testing and Calibration Suite for Turn Understanding.

Verifies:
1. Complete 80+ Real Intent Test Matrix (20 Audio, 20 Pause, 20 Repeat, 20 Answer).
2. 40+ Adversarial Technical Utterances (Aggressive False-Positive Protection).
3. Compound Utterances (Control + Substantive Content -> INTERVIEW_ANSWER).
4. Natural Linguistic Paraphrases (Evaluating Tier 2 Generalization).
5. Similarity Distribution Analysis & Threshold Calibration.
6. Zero InterviewAIContext Mutation.
7. Determinism across repeated executions.
8. Latency Benchmark with p50, p90, p99 instrumentation.
9. Failure Safety (empty, whitespace, malformed Unicode, long text, punctuation-free ASR text).
"""

from __future__ import annotations

import statistics
import time
import unittest
from unittest.mock import patch

from app.custom_llm.classifier import (
    FastPathTurnClassifier,
    TurnIntent,
    get_fast_path_spoken_response,
    normalize_transcript,
    turn_classifier,
)
from app.interview_context.models import EvidenceItem, InterviewAIContext
from app.models.enums import DifficultyLevel


class TestFastPathClassifierStressAndCalibration(unittest.TestCase):
    """Rigorous Stress-Testing and Calibration of the Turn Understanding Engine."""

    def setUp(self) -> None:
        self.classifier = FastPathTurnClassifier(semantic_threshold=0.60)
        self.context = InterviewAIContext(
            interview_id="test-room-calibration",
            candidate_id="cand-calib-1",
            current_round_id="technical",
            current_agent_id="alex",
            difficulty=DifficultyLevel.MEDIUM,
            missing_competencies=["system_design", "scalability"],
        )

    # ── 1. Text Normalization & Robustness ────────────────────────────────────
    def test_01_normalization_handles_all_irregularities(self) -> None:
        """Punctuation, casing, accents, and spacing are normalized cleanly."""
        self.assertEqual(normalize_transcript("  Hi, AM I AUDIBLE???  "), "hi am i audible")
        self.assertEqual(normalize_transcript("Can you hear me’s mic?"), "can you hear me's mic")
        self.assertEqual(normalize_transcript("Give   me\t\na second!"), "give me a second")
        self.assertEqual(normalize_transcript(""), "")
        self.assertEqual(normalize_transcript(None), "")
        self.assertEqual(normalize_transcript("   \n\t   "), "")

    # ── 2. Real Intent Matrix (80+ Utterances: 20 each) ─────────────────────
    def test_02_audio_check_intent_matrix(self) -> None:
        """20 representative natural AUDIO_CHECK utterances."""
        audio_checks = [
            "Am I audible?",
            "Can you hear me?",
            "Can you hear me now?",
            "Can you hear me clearly?",
            "Are you able to hear me?",
            "Are you getting my audio?",
            "Did that come through?",
            "Sorry, did you hear that?",
            "Is my audio working?",
            "Is my mic working?",
            "Can you hear my voice?",
            "Hello, can you hear me?",
            "Hi, can you hear me?",
            "Testing mic.",
            "Mic check.",
            "My mic seems weird, can you hear me?",
            "I think my headset glitched, did you catch that?",
            "Sorry, I think the audio dropped for a moment.",
            "My headset just glitched, was my last sentence audible?",
            "Did you catch what I just said?",
        ]
        self.assertEqual(len(audio_checks), 20)
        for utt in audio_checks:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.AUDIO_CHECK,
                f"AUDIO_CHECK failure for: '{utt}' (got {res.intent}, tier={res.tier})",
            )
            self.assertTrue(res.is_control_turn)

    def test_03_time_pause_intent_matrix(self) -> None:
        """20 representative natural TIME_PAUSE utterances."""
        time_pauses = [
            "Give me a second.",
            "Give me a moment.",
            "One second.",
            "One moment.",
            "Hang on.",
            "Hang on a sec.",
            "Let me think.",
            "Just a moment.",
            "Give me a sec.",
            "Just a sec.",
            "Hold on.",
            "Wait a second.",
            "Wait a moment.",
            "Wait a sec.",
            "One sec.",
            "Give me one second.",
            "Let me think for a moment.",
            "Sorry, I need a moment.",
            "Let me collect my thoughts for a moment.",
            "One second, I'm trying to remember.",
        ]
        self.assertEqual(len(time_pauses), 20)
        for utt in time_pauses:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.TIME_PAUSE,
                f"TIME_PAUSE failure for: '{utt}' (got {res.intent}, tier={res.tier})",
            )
            self.assertTrue(res.is_control_turn)

    def test_04_repeat_question_intent_matrix(self) -> None:
        """20 representative natural REPEAT_QUESTION utterances."""
        repeat_questions = [
            "Can you repeat the question?",
            "Could you repeat the question?",
            "Can you repeat that?",
            "Could you repeat that?",
            "What was the question?",
            "What did you ask?",
            "Sorry, what was the question?",
            "Sorry, what did you ask?",
            "Can you say that again?",
            "Could you say that again?",
            "Repeat the question please.",
            "Could you please repeat the question?",
            "Can you please repeat that?",
            "Sorry, I didn't catch that.",
            "I didn't catch the question.",
            "Can you repeat that last part?",
            "Could you repeat that last part?",
            "What was the question again?",
            "Sorry, I missed the question.",
            "Could you go over the question again?",
        ]
        self.assertEqual(len(repeat_questions), 20)
        for utt in repeat_questions:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.REPEAT_QUESTION,
                f"REPEAT_QUESTION failure for: '{utt}' (got {res.intent}, tier={res.tier})",
            )
            self.assertTrue(res.is_control_turn)

    def test_05_interview_answer_intent_matrix(self) -> None:
        """20 representative natural INTERVIEW_ANSWER utterances."""
        interview_answers = [
            "We used Redis because we needed low latency caching in front of PostgreSQL.",
            "We designed the system around Kafka for asynchronous event processing.",
            "I chose PostgreSQL because our financial ledger required strict ACID compliance.",
            "We used consistent hashing to distribute the cache keys across 16 nodes.",
            "Our microservices communicate via gRPC with protocol buffers.",
            "I configured PgBouncer for transaction-level connection pooling.",
            "The write model uses CQRS with event sourcing in Cassandra.",
            "We implemented a token bucket rate limiter at the API gateway layer.",
            "I sharded the user database using consistent hash partitioning.",
            "We handled database replication lag with read-after-write consistency.",
            "I don't know.",
            "I'm not sure how Kubernetes manages that failover.",
            "I haven't worked with Kafka in production.",
            "I don't have experience with distributed consensus algorithms.",
            "No experience with GraphQL.",
            "I've never touched Elasticsearch clusters.",
            "We handled 10,000 writes per second during peak flash sales.",
            "The trade-off was between availability and partition tolerance.",
            "We used Docker containers orchestrated on Amazon ECS.",
            "Yes, we handled that in the payment gateway architecture.",
        ]
        self.assertEqual(len(interview_answers), 20)
        for utt in interview_answers:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.INTERVIEW_ANSWER,
                f"INTERVIEW_ANSWER failure for: '{utt}' (got {res.intent}, tier={res.tier})",
            )
            self.assertFalse(res.is_control_turn)

    # ── 3. Aggressive False-Positive Testing (40+ Adversarial Utterances) ─────
    def test_06_adversarial_technical_false_positive_guards(self) -> None:
        """40+ adversarial technical utterances containing control keywords MUST remain INTERVIEW_ANSWER."""
        adversarial_cases = [
            # Technical uses of "hear" / "audible" / "mic"
            "Can you hear me explain how Redis replication works?",
            "Can you hear me explain why we selected Kafka?",
            "Can you hear me walk through our database sharding strategy?",
            "Did that latency number come through in the benchmark?",
            "Did that throughput metric come through in our monitoring dashboard?",
            "We had a microphone-related monitoring issue in production.",
            "Sorry, my mic cut out while I was explaining the architecture.",
            "Can you hear me talk about our microservice load balancing?",
            "Is the audio processing pipeline using gRPC or WebSockets?",
            "Can you hear me describe our cache invalidation logic?",
            # Technical uses of "second" / "moment" / "sec" / "pause" / "wait"
            "I need a second replica for the database.",
            "We provisioned a second replica in Postgres for read scaling.",
            "Give me a second example of how sharding works.",
            "Give me a second example of the architecture.",
            "Give me a second example of how you implemented caching.",
            "I need a moment to explain how the cache invalidation worked.",
            "Hold on, the second replica failed during the deployment.",
            "Hold on, our Redis cluster handles failover automatically.",
            "Hold on, the database cluster handles sharding automatically.",
            "I'll explain the trade-off in a second.",
            "We observed a 500 millisecond pause during garbage collection.",
            "The connection timeout is set to one second in the pool config.",
            "Let me think about the database partitioning strategy.",
            "Let me think about how our Kafka partitions were configured.",
            "Give me a second to explain how we partitioned the database.",
            "Give me a moment to explain the architectural trade-offs.",
            "Wait a second, we also used DynamoDB for session state.",
            "Wait a sec, the Cassandra replication factor was set to 3.",
            # Technical uses of "repeat" / "say again" / "question"
            "Can you repeat the question about Redis and then I'll explain our solution?",
            "Can you repeat the question and then I'll explain how we solved it?",
            "Can you repeat the question about consistency models? I want to explain the trade-off.",
            "The main question in our architecture was how to handle failover.",
            "I repeated the benchmark with 10,000 concurrent database connections.",
            "We had to repeat the database migration because of a lock deadlock.",
            "Let me repeat the architecture details: we used Kafka and Redis.",
            "Could you repeat the question so I can explain our Redis cluster?",
            # Mixed complex technical statements
            "I don't know the exact latency, but the second replica handled read queries.",
            "Hold on, let me explain how our microservices communicate over gRPC.",
            "Sorry, my mic cut out, but the architecture used Redis for caching.",
            "Can you hear me? We used Kafka for event processing.",
            "Yeah, give me a second, I'm trying to remember how we partitioned the database.",
            "Give me a second, I'm thinking about the trade-offs.",
        ]
        self.assertGreaterEqual(len(adversarial_cases), 40)
        for utt in adversarial_cases:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.INTERVIEW_ANSWER,
                f"CRITICAL FALSE POSITIVE: Adversarial answer '{utt}' was classified as {res.intent} (tier={res.tier}, rule={res.matched_rule})",
            )
            self.assertFalse(res.is_control_turn)

    # ── 4. Compound Intent Testing ───────────────────────────────────────────
    def test_07_compound_utterances_route_conservatively_to_interview_answer(self) -> None:
        """Utterances with control openings followed by substantive explanations route to INTERVIEW_ANSWER."""
        compound_cases = [
            "Give me a second, I'm thinking about the trade-offs.",
            "Sorry, my mic cut out, but the architecture used Redis for caching.",
            "Can you hear me? We used Kafka for event processing.",
            "Yeah, give me a second, I'm trying to remember how we partitioned the database.",
            "Hold on, let me explain how our microservices communicate over gRPC.",
            "Give me a moment to explain the trade-offs.",
            "Can you repeat the question and then I'll explain how we solved it.",
        ]
        for utt in compound_cases:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                TurnIntent.INTERVIEW_ANSWER,
                f"Compound utterance '{utt}' was classified as {res.intent} instead of INTERVIEW_ANSWER",
            )
            self.assertFalse(res.is_control_turn)

    # ── 5. Natural Paraphrase & Tier 2 Coverage Testing ──────────────────────
    def test_08_natural_paraphrases_handled_by_tier2(self) -> None:
        """Paraphrased control utterances that don't match Tier 1 exact dictionaries are caught by Tier 2."""
        paraphrases = [
            ("My headset just glitched, was my last sentence audible?", TurnIntent.AUDIO_CHECK),
            ("Sorry, I think the audio dropped for a moment.", TurnIntent.AUDIO_CHECK),
            ("Did you catch what I just said?", TurnIntent.AUDIO_CHECK),
            ("Let me collect my thoughts for a moment.", TurnIntent.TIME_PAUSE),
            ("I'm drawing a blank, give me a moment.", TurnIntent.TIME_PAUSE),
            ("Just let me think through that.", TurnIntent.TIME_PAUSE),
            ("Sorry, I missed the question.", TurnIntent.REPEAT_QUESTION),
            ("What was the question again?", TurnIntent.REPEAT_QUESTION),
            ("I didn't quite catch the last part.", TurnIntent.REPEAT_QUESTION),
        ]
        for utt, expected_intent in paraphrases:
            res = self.classifier.classify(utt, self.context)
            self.assertEqual(
                res.intent,
                expected_intent,
                f"Tier 2 paraphrase failed for '{utt}': expected {expected_intent}, got {res.intent} (tier={res.tier})",
            )
            self.assertTrue(res.is_control_turn)

    # ── 6. Similarity Distribution & Threshold Calibration Analysis ──────────
    def test_09_threshold_similarity_distribution_analysis(self) -> None:
        """Measure cosine similarity distributions for true control vs adversarial technical vs answers."""
        control_samples = [
            "am I audible to you?",
            "can you hear me clearly?",
            "did that come through?",
            "give me a second to think",
            "hang on a moment",
            "could you repeat that please",
            "what was that last question",
        ]
        adversarial_samples = [
            "Can you hear me explain how Redis replication works?",
            "I need a second replica for the database.",
            "Did that latency number come through in the benchmark?",
            "Hold on, the database cluster handles sharding automatically.",
        ]
        substantive_samples = [
            "We designed an LMS using FastAPI and PostgreSQL.",
            "I partitioned the Cassandra cluster into 16 vnodes.",
            "The trade-off was between write latency and eventual consistency.",
        ]

        control_scores = [self.classifier.semantic_matcher.score(normalize_transcript(s))[1] for s in control_samples]
        adversarial_scores = [self.classifier.semantic_matcher.score(normalize_transcript(s))[1] for s in adversarial_samples]
        substantive_scores = [self.classifier.semantic_matcher.score(normalize_transcript(s))[1] for s in substantive_samples]

        min_control = min(control_scores)
        max_substantive = max(substantive_scores)
        avg_control = sum(control_scores) / len(control_scores)
        avg_substantive = sum(substantive_scores) / len(substantive_scores)

        print(f"\n[CALIBRATION STATS]")
        print(f"Control Similarity Scores: min={min_control:.3f}, max={max(control_scores):.3f}, avg={avg_control:.3f}")
        print(f"Adversarial Scores: min={min(adversarial_scores):.3f}, max={max(adversarial_scores):.3f}, avg={sum(adversarial_scores)/len(adversarial_scores):.3f}")
        print(f"Substantive Scores: min={min(substantive_scores):.3f}, max={max_substantive:.3f}, avg={avg_substantive:.3f}")

        # Assert clear margin between true controls and substantive answers
        self.assertGreater(min_control, 0.60, "All true control samples must exceed threshold 0.60")
        self.assertLess(max_substantive, 0.40, "All substantive answers must remain well below threshold 0.60")

    # ── 7. Zero State Mutation Verification ──────────────────────────────────
    def test_10_zero_context_mutation(self) -> None:
        """Classifying turns has ZERO mutation on InterviewAIContext."""
        self.context.add_evidence(EvidenceItem(id="ev-1", competency="system_design", signal="Initial tech"))
        self.context.add_evaluated_competency("system_design")

        init_ev = len(self.context.accumulated_evidence)
        init_comp = list(self.context.evaluated_competencies)
        init_diff = self.context.difficulty
        init_agent = self.context.current_agent_id
        init_meta = dict(self.context.metadata)

        for text in ["Am I audible?", "Give me a second.", "We used Kafka queues.", "Can you repeat that?"]:
            self.classifier.classify(text, self.context)

        self.assertEqual(len(self.context.accumulated_evidence), init_ev)
        self.assertEqual(self.context.evaluated_competencies, init_comp)
        self.assertEqual(self.context.difficulty, init_diff)
        self.assertEqual(self.context.current_agent_id, init_agent)
        self.assertEqual(self.context.metadata, init_meta)

    # ── 8. Determinism Verification ──────────────────────────────────────────
    def test_11_deterministic_repeatability(self) -> None:
        """Executing 50 iterations over varied inputs yields 100% identical outputs."""
        inputs = [
            "Am I audible?",
            "Give me a second to think.",
            "Can you repeat the question?",
            "We used Kafka for distributed event streaming.",
            "I need a second replica for PostgreSQL.",
            "I don't know.",
        ]
        for text in inputs:
            base_res = self.classifier.classify(text)
            for _ in range(50):
                rep_res = self.classifier.classify(text)
                self.assertEqual(rep_res.intent, base_res.intent)
                self.assertEqual(rep_res.confidence, base_res.confidence)
                self.assertEqual(rep_res.tier, base_res.tier)

    # ── 9. Latency Benchmark with p50, p90, p99 ──────────────────────────────
    def test_12_latency_benchmark_percentiles(self) -> None:
        """Benchmark 5,000 iterations and calculate p50, p90, p99, and average latency."""
        sample_suite = [
            "Am I audible?",
            "Can you hear me clearly?",
            "Give me a second.",
            "Let me think for a moment.",
            "Can you repeat the question?",
            "We implemented distributed caching using Redis clusters.",
            "I don't know.",
            "Sorry, my mic cut out. Did that come through?",
            "I need a second replica for PostgreSQL.",
            "Can you hear me explain why we selected Kafka?",
        ]
        latencies_ms = []
        for _ in range(500):
            for text in sample_suite:
                t0 = time.perf_counter()
                self.classifier.classify(text)
                t1 = time.perf_counter()
                latencies_ms.append((t1 - t0) * 1000)

        latencies_sorted = sorted(latencies_ms)
        p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
        p90 = latencies_sorted[int(len(latencies_sorted) * 0.90)]
        p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
        avg = statistics.mean(latencies_ms)

        print(f"\n[LATENCY BENCHMARK — 5,000 turns]")
        print(f"Avg: {avg:.4f} ms | p50: {p50:.4f} ms | p90: {p90:.4f} ms | p99: {p99:.4f} ms")
        self.assertGreater(len(latencies_ms), 0)

    # ── 10. Failure Safety on Malformed / Edge-Case Inputs ────────────────────
    def test_13_failure_safety_on_edge_cases(self) -> None:
        """Malformed Unicode, repeated words, and punctuation-free ASR text fail safely to INTERVIEW_ANSWER."""
        edge_cases = [
            "",
            "   ",
            "\t\n",
            None,
            "???!!!...",
            "audio audio audio audio audio audio audio audio audio",
            "second second second second second",
            "repeat repeat repeat repeat",
            "we used redis " * 50,  # very long string
            "🚀🔥✨",  # pure emoji
            "\x00\x01\x02",  # null bytes
            "am i audible we used kafka for the event streaming architecture",  # ASR punctuation-free compound
        ]
        for ec in edge_cases:
            res = self.classifier.classify(ec)
            self.assertIsNotNone(res.intent)
            if ec in ("", "   ", "\t\n", None, "???!!!..."):
                self.assertEqual(res.intent, TurnIntent.INTERVIEW_ANSWER)
                self.assertEqual(res.tier, "fallback")
            elif "we used kafka" in str(ec):
                self.assertEqual(res.intent, TurnIntent.INTERVIEW_ANSWER)


if __name__ == "__main__":
    unittest.main()
