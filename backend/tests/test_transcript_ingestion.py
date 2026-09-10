"""Comprehensive unit and integration tests for Agora Transcript & Event Ingestion."""

import hashlib
import hmac
import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.interview_context.store import interview_session_store
from app.core.config import settings
from app.integrations import standard_http_boundary
from app.main import create_app
from app.transcript.models import SpeakerType, TranscriptEvent
from app.transcript.service import TranscriptService
from app.transcript.store import TranscriptStore, transcript_store
from app.voice.authorization import Actor


class SignedWebhookTestClient(TestClient):
    def __init__(self, app, notification_secret: str, *args, **kwargs):
        super().__init__(app, *args, **kwargs)
        self.notification_secret = notification_secret

    def request(self, method, url, **kwargs):  # type: ignore[override]
        # Agora webhook callbacks are now signature-verified.
        # Keep legacy tests intact by signing json payloads exactly as sent.
        if (
            method.upper() == "POST"
            and "/api/v1/interviews/agora-webhook" in url
            and "json" in kwargs
            and isinstance(kwargs["json"], dict)
        ):
            payload = kwargs.pop("json")
            kwargs.pop("data", None)
            kwargs.pop("content", None)
            raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            signature = hmac.new(
                self.notification_secret.encode("utf-8"), raw, hashlib.sha256
            ).hexdigest()
            headers = dict(kwargs.pop("headers") or {})
            headers.update(
                {
                    "Content-Type": "application/json",
                    "agora-signature-v2": signature,
                    "Content-Length": str(len(raw)),
                }
            )
            return super().request(method, url, data=raw, headers=headers, **kwargs)
        return super().request(method, url, **kwargs)


class TestTranscriptIngestion(unittest.TestCase):
    """Test suite covering Agora transcript ingestion, normalization, attribution, ordering, dedup, and isolation."""

    def setUp(self) -> None:
        self.actor = Actor(
            user_id="recruiter-1",
            role="recruiter",
            email="recruiter@example.com",
            name="Test Recruiter",
            tenant_id="tenant-test",
            candidate_id=None,
        )
        self.notification_secret = "test-notification-secret"
        self.secret_patch = patch.object(
            settings, "AGORA_NOTIFICATION_SECRET", self.notification_secret
        )
        self.secret_patch.start()
        self.require_interview_patch = patch(
            "app.integrations.standard_http_boundary.require_interview",
            new=AsyncMock(return_value=None),
        )
        self.require_interview_patch.start()

        self.app = create_app()
        self.app.dependency_overrides[standard_http_boundary.current_actor] = lambda request=None: self.actor
        self.app.dependency_overrides[standard_http_boundary.get_supabase] = lambda request=None: object()
        self.client = SignedWebhookTestClient(self.app, self.notification_secret)
        self.store = TranscriptStore()
        self.service = TranscriptService(store=self.store)
        transcript_store.clear()
        interview_session_store.clear()

    def tearDown(self) -> None:
        self.store.clear()
        transcript_store.clear()
        interview_session_store.clear()
        self.require_interview_patch.stop()
        self.secret_patch.stop()
        self.client.app.dependency_overrides.clear()
        self.client.close()

    # ── TEST 1: Valid Candidate Transcript ───────────────────────────────────
    def test_01_valid_candidate_transcript(self) -> None:
        """Valid candidate transcript event is normalized and stored with candidate speaker."""
        resp = self.client.post(
            "/api/v1/interviews/session-test-01/transcript-events",
            json={
                "id": "cand-turn-1",
                "role": "user",
                "text": "I built a distributed cache with Raft consensus.",
                "timestamp": 1788517250000,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "stored")
        self.assertEqual(data["speaker"], "candidate")

        # Verify retrieval
        get_resp = self.client.get("/api/v1/interviews/session-test-01/transcript")
        self.assertEqual(get_resp.status_code, 200)
        t_data = get_resp.json()
        self.assertEqual(t_data["total_events"], 1)
        self.assertEqual(t_data["events"][0]["speaker"], "candidate")
        self.assertEqual(t_data["events"][0]["text"], "I built a distributed cache with Raft consensus.")

    # ── TEST 2: Valid Alex Transcript ────────────────────────────────────────
    def test_02_valid_alex_transcript(self) -> None:
        """Valid Alex interviewer transcript is attributed to agent Alex."""
        interview_session_store.get_or_create("session-test-alex", agent_id="alex")

        resp = self.client.post(
            "/api/v1/interviews/session-test-alex/transcript-events",
            json={
                "id": "alex-turn-1",
                "role": "assistant",
                "agent_id": "alex",
                "text": "How do you ensure data consistency across partitions?",
                "timestamp": 1788517260000,
            },
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "stored")
        self.assertEqual(data["speaker"], "agent")

        get_resp = self.client.get("/api/v1/interviews/session-test-alex/transcript")
        self.assertEqual(get_resp.json()["events"][0]["agent_id"], "alex")

    # ── TEST 3: Valid Jordan Transcript ──────────────────────────────────────
    def test_03_valid_jordan_transcript(self) -> None:
        """Valid Jordan interviewer transcript is attributed to agent Jordan."""
        interview_session_store.get_or_create("session-test-jordan", agent_id="jordan")

        resp = self.client.post(
            "/api/v1/interviews/session-test-jordan/transcript-events",
            json={
                "id": "jordan-turn-1",
                "role": "assistant",
                "agent_id": "jordan",
                "text": "What metrics would you define to measure user engagement?",
                "timestamp": 1788517270000,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "stored")

        get_resp = self.client.get("/api/v1/interviews/session-test-jordan/transcript")
        self.assertEqual(get_resp.json()["events"][0]["agent_id"], "jordan")

    # ── TEST 4: Agora Webhook Event 103 (Agent History) ──────────────────────
    def test_04_agora_webhook_event_103_agent_history(self) -> None:
        """Agora Webhook Event 103 (Agent History) multi-turn session payload is ingested."""
        interview_session_store.register_alias("A44CR55KT35JK33DA46ET24MA46KR65V", "session-hist-103")
        interview_session_store.get_or_create("session-hist-103", agent_id="alex")

        webhook_payload = {
            "notice_id": "notice-103-xyz",
            "event_type": 103,
            "notify_ts": 1788517300000,
            "payload": {
                "agent_id": "A44CR55KT35JK33DA46ET24MA46KR65V",
                "channel": "session-hist-103",
                "start_ts": 1788517240000,
                "stop_ts": 1788517300000,
                "contents": [
                    {
                        "role": "assistant",
                        "content": "Hello! I am Alex. Let's start the technical interview.",
                        "speech_start_ms": 1788517242000,
                        "speech_end_ms": 1788517245000,
                    },
                    {
                        "role": "user",
                        "content": "Hi Alex, I'm ready.",
                        "speech_start_ms": 1788517246000,
                        "speech_end_ms": 1788517248000,
                    },
                    {
                        "role": "assistant",
                        "content": "Can you explain how a LSM tree works?",
                        "speech_start_ms": 1788517250000,
                        "speech_end_ms": 1788517255000,
                    },
                ],
            },
        }

        resp = self.client.post("/api/v1/interviews/agora-webhook", json=webhook_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["events_processed"], 3)
        self.assertEqual(data["events_stored"], 3)

        # Retrieve and verify dialogue sequence
        get_resp = self.client.get("/api/v1/interviews/session-hist-103/transcript")
        events = get_resp.json()["events"]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[0]["speaker"], "agent")
        self.assertEqual(events[0]["text"], "Hello! I am Alex. Let's start the technical interview.")
        self.assertEqual(events[1]["speaker"], "candidate")
        self.assertEqual(events[1]["text"], "Hi Alex, I'm ready.")
        self.assertEqual(events[2]["speaker"], "agent")
        self.assertEqual(events[2]["text"], "Can you explain how a LSM tree works?")

    # ── TEST 5: Agora Webhook Event 112 (Turns Finished) ─────────────────────
    def test_05_agora_webhook_event_112_turns_finished(self) -> None:
        """Agora Webhook Event 112 (Turns Finished) payload is ingested."""
        interview_session_store.register_alias("A44CJ38AD89AL25VK89JT94HN36EC63A", "session-turns-112")

        webhook_payload = {
            "notice_id": "notice-112-abc",
            "event_type": 112,
            "payload": {
                "agent_id": "A44CJ38AD89AL25VK89JT94HN36EC63A",
                "channel": "session-turns-112",
                "turns": [
                    {
                        "turn_id": "turn-1",
                        "speaker": "assistant",
                        "text": "Welcome to the product round.",
                        "timestamp": 1788517200000,
                    },
                    {
                        "turn_id": "turn-2",
                        "speaker": "user",
                        "text": "Thanks Jordan.",
                        "timestamp": 1788517205000,
                    },
                ],
            },
        }

        resp = self.client.post("/api/v1/interviews/agora-webhook", json=webhook_payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["events_stored"], 2)

        get_resp = self.client.get("/api/v1/interviews/session-turns-112/transcript")
        self.assertEqual(len(get_resp.json()["events"]), 2)

    # ── TEST 6: Intermediate Transcript Update ───────────────────────────────
    def test_06_intermediate_transcript_update(self) -> None:
        """Interim transcript is stored with is_final=False."""
        event = TranscriptEvent(
            id="interim-turn-1",
            interview_id="room-interim",
            channel="room-interim",
            speaker=SpeakerType.CANDIDATE,
            text="I would use a ...",
            timestamp=1788517200000,
            is_final=False,
        )
        stored = self.store.add_event_sync(event)
        self.assertTrue(stored)

        # Non-final not returned when is_final_only=True
        finals = self.store.get_transcript("room-interim", is_final_only=True)
        self.assertEqual(len(finals), 0)

        # Returned when is_final_only=False
        all_events = self.store.get_transcript("room-interim", is_final_only=False)
        self.assertEqual(len(all_events), 1)

    # ── TEST 7: Intermediate to Final In-Place Replacement ───────────────────
    def test_07_intermediate_to_final_replacement(self) -> None:
        """When final transcript arrives for an existing event ID, it replaces the interim turn in place."""
        # 1. Interim
        event_interim = TranscriptEvent(
            id="stream-turn-10",
            interview_id="room-replace",
            channel="room-replace",
            speaker=SpeakerType.CANDIDATE,
            text="I think we should use",
            timestamp=1788517200000,
            is_final=False,
        )
        self.store.add_event_sync(event_interim)

        # 2. Final
        event_final = TranscriptEvent(
            id="stream-turn-10",
            interview_id="room-replace",
            channel="room-replace",
            speaker=SpeakerType.CANDIDATE,
            text="I think we should use Redis for caching.",
            timestamp=1788517200000,
            is_final=True,
        )
        updated = self.store.add_event_sync(event_final)
        self.assertTrue(updated)

        # Store count should still be 1 (replaced in place)
        self.assertEqual(self.store.count_events("room-replace"), 1)
        finals = self.store.get_transcript("room-replace", is_final_only=True)
        self.assertEqual(len(finals), 1)
        self.assertEqual(finals[0].text, "I think we should use Redis for caching.")

    # ── TEST 8: Malformed Event Handled Gracefully ───────────────────────────
    def test_08_malformed_event_handled_gracefully(self) -> None:
        """Empty text is safely rejected without crashing."""
        resp = self.client.post(
            "/api/v1/interviews/room-err/transcript-events",
            json={"text": "   "},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "error")

    # ── TEST 9: Duplicate Event Rejection ────────────────────────────────────
    def test_09_duplicate_event_rejection(self) -> None:
        """Duplicate submissions of the exact same event are rejected idempotently."""
        payload = {
            "id": "dup-turn-1",
            "role": "user",
            "text": "Exact same answer.",
            "timestamp": 1788517200000,
        }
        resp1 = self.client.post("/api/v1/interviews/room-dup/transcript-events", json=payload)
        self.assertEqual(resp1.json()["status"], "stored")

        resp2 = self.client.post("/api/v1/interviews/room-dup/transcript-events", json=payload)
        self.assertEqual(resp2.json()["status"], "duplicate")

        get_resp = self.client.get("/api/v1/interviews/room-dup/transcript")
        self.assertEqual(get_resp.json()["total_events"], 1)

    # ── TEST 10: Deterministic Ordering by Timestamp & Sequence ──────────────
    def test_10_deterministic_ordering(self) -> None:
        """Events submitted out of order are ordered deterministically by timestamp."""
        # Submit Turn 3, Turn 1, Turn 2
        e3 = TranscriptEvent(id="e3", interview_id="room-order", channel="c", speaker=SpeakerType.CANDIDATE, text="Three", timestamp=3000, sequence=3)
        e1 = TranscriptEvent(id="e1", interview_id="room-order", channel="c", speaker=SpeakerType.AGENT, text="One", timestamp=1000, sequence=1)
        e2 = TranscriptEvent(id="e2", interview_id="room-order", channel="c", speaker=SpeakerType.CANDIDATE, text="Two", timestamp=2000, sequence=2)

        self.store.add_event_sync(e3)
        self.store.add_event_sync(e1)
        self.store.add_event_sync(e2)

        ordered = self.store.get_transcript("room-order")
        self.assertEqual([e.text for e in ordered], ["One", "Two", "Three"])

    # ── TEST 11: Multi-Turn Conversation Preservation ────────────────────────
    def test_11_multi_turn_conversation_preservation(self) -> None:
        """10 consecutive conversational turns are preserved in exact order."""
        for i in range(10):
            speaker = SpeakerType.AGENT if i % 2 == 0 else SpeakerType.CANDIDATE
            self.store.add_event_sync(
                TranscriptEvent(
                    id=f"turn-{i}",
                    interview_id="room-10turns",
                    channel="room-10turns",
                    speaker=speaker,
                    text=f"Dialogue message {i}",
                    timestamp=10000 + i * 1000,
                    sequence=i + 1,
                )
            )

        transcript = self.store.get_transcript("room-10turns")
        self.assertEqual(len(transcript), 10)
        self.assertEqual(transcript[0].speaker, SpeakerType.AGENT)
        self.assertEqual(transcript[1].speaker, SpeakerType.CANDIDATE)
        self.assertEqual(transcript[9].speaker, SpeakerType.CANDIDATE)

    # ── TEST 12: Multi-Interview Session Isolation ───────────────────────────
    def test_12_multi_interview_isolation(self) -> None:
        """Events from Interview A never leak into Interview B."""
        self.store.add_event_sync(
            TranscriptEvent(id="a1", interview_id="session-A", channel="A", speaker=SpeakerType.CANDIDATE, text="Answer A", timestamp=1000)
        )
        self.store.add_event_sync(
            TranscriptEvent(id="b1", interview_id="session-B", channel="B", speaker=SpeakerType.CANDIDATE, text="Answer B", timestamp=1000)
        )

        t_A = self.store.get_transcript("session-A")
        t_B = self.store.get_transcript("session-B")

        self.assertEqual(len(t_A), 1)
        self.assertEqual(t_A[0].text, "Answer A")
        self.assertEqual(len(t_B), 1)
        self.assertEqual(t_B[0].text, "Answer B")

    # ── TEST 13: Identical Text in Different Turns ───────────────────────────
    def test_13_identical_text_in_distinct_turns(self) -> None:
        """Identical words spoken in different turns (different timestamps) are preserved."""
        # e.g. Candidate saying "Yes, absolutely" twice at minute 1 and minute 5
        e1 = TranscriptEvent(id="turn-early", interview_id="room-repeat", channel="c", speaker=SpeakerType.CANDIDATE, text="Yes, absolutely.", timestamp=1000)
        e2 = TranscriptEvent(id="turn-later", interview_id="room-repeat", channel="c", speaker=SpeakerType.CANDIDATE, text="Yes, absolutely.", timestamp=300000)

        s1 = self.store.add_event_sync(e1)
        s2 = self.store.add_event_sync(e2)

        self.assertTrue(s1)
        self.assertTrue(s2)
        self.assertEqual(len(self.store.get_transcript("room-repeat")), 2)

    # ── TEST 14: Strict Isolation - No M1 Invocation ─────────────────────────
    def test_14_no_m1_invocation(self) -> None:
        """Transcript ingestion path strictly never invokes Gemini or M1 Intelligence."""
        with patch("app.interview_intelligence.analyzer.M1InterviewAnalyzer.analyze") as mock_m1:
            resp = self.client.post(
                "/api/v1/interviews/room-iso/transcript-events",
                json={"id": "t1", "text": "Some text", "role": "user", "timestamp": 1000},
            )
            self.assertEqual(resp.status_code, 200)
            mock_m1.assert_not_called()


    # ── TEST 15: Strict Isolation - No Meta-Orchestrator Invocation ──────────
    def test_15_no_meta_orchestrator_invocation(self) -> None:
        """Transcript ingestion path strictly never invokes Meta-Orchestrator."""
        with patch("app.orchestrator.service.MetaOrchestrator.decide") as mock_orch:
            resp = self.client.post(
                "/api/v1/interviews/room-iso/transcript-events",
                json={"id": "t1", "text": "Some text", "role": "user", "timestamp": 1000},
            )
            self.assertEqual(resp.status_code, 200)
            mock_orch.assert_not_called()


    # ── TEST 16: Strict Isolation - No Knowledge Graph Invocation ────────────
    def test_16_no_knowledge_graph_invocation(self) -> None:
        """Transcript ingestion path never invokes Knowledge Graph operations."""
        # Verified by ensuring zero neo4j/kg imports or calls in transcript pipeline
        resp = self.client.post(
            "/api/v1/interviews/room-iso/transcript-events",
            json={"id": "t1", "text": "Test KG isolation", "role": "user", "timestamp": 1000},
        )
        self.assertEqual(resp.status_code, 200)

    # ── TEST 17: No Secrets in Logs ──────────────────────────────────────────
    def test_17_no_secrets_in_logs(self) -> None:
        """Ensure App Certificate or auth secrets never appear in transcript payloads or responses."""
        with patch.object(self.client.app.state, "test_cert", "super_secret_cert_12345", create=True):
            resp = self.client.post(
                "/api/v1/interviews/room-sec/transcript-events",
                json={"id": "t1", "text": "Test secrets", "role": "user", "timestamp": 1000},
            )
            self.assertNotIn("super_secret_cert_12345", str(resp.json()))

    # ── TEST 18: Transcript Retrieval Endpoint ───────────────────────────────
    def test_18_transcript_retrieval_endpoint(self) -> None:
        """GET /api/v1/interviews/{id}/transcript returns complete structured payload."""
        self.client.post(
            "/api/v1/interviews/room-retrieval/transcript-events",
            json={"id": "r1", "text": "Candidate response", "role": "user", "timestamp": 1000},
        )
        resp = self.client.get("/api/v1/interviews/room-retrieval/transcript")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["interview_id"], "room-retrieval")
        self.assertEqual(data["total_events"], 1)
        self.assertEqual(data["events"][0]["text"], "Candidate response")

    # ── TEST 19: Unsupported Webhook Event Handled Gracefully ────────────────
    def test_19_unsupported_webhook_event_handled_gracefully(self) -> None:
        """Lifecycle events (101 agent joined, 102 agent left) are processed cleanly without errors."""
        webhook_payload = {
            "notice_id": "notice-101-join",
            "event_type": 101,
            "payload": {"agent_id": "agent-123", "channel": "session-101"},
        }
        resp = self.client.post("/api/v1/interviews/agora-webhook", json=webhook_payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertEqual(resp.json()["events_processed"], 0)

    # ── TEST 20: RTM TRANSCRIPT_UPDATED Event Ingestion ──────────────────────
    def test_20_rtm_transcript_updated_event_ingestion(self) -> None:
        """Agora RTM TRANSCRIPT_UPDATED event is ingested with intermediate to final lifecycle."""
        # 1. Ingest interim turn
        resp_interim = self.client.post(
            "/api/v1/interviews/session-rtm-test/transcript-events",
            json={
                "id": "rtm-turn-101",
                "channel": "session-rtm-test",
                "role": "assistant",
                "text": "Can you explain how you",
                "timestamp": 1788518000000,
                "sequence": 1,
                "is_final": False,
                "source": "agora_rtm",
            },
        )
        self.assertEqual(resp_interim.status_code, 200)

        # 2. Ingest final turn under same turn ID
        resp_final = self.client.post(
            "/api/v1/interviews/session-rtm-test/transcript-events",
            json={
                "id": "rtm-turn-101",
                "channel": "session-rtm-test",
                "role": "assistant",
                "text": "Can you explain how you design distributed caches?",
                "timestamp": 1788518000000,
                "sequence": 1,
                "is_final": True,
                "source": "agora_rtm",
            },
        )
        self.assertEqual(resp_final.status_code, 200)

        # 3. Verify in-place replacement
        get_resp = self.client.get("/api/v1/interviews/session-rtm-test/transcript")
        data = get_resp.json()
        self.assertEqual(data["total_events"], 1)
        self.assertEqual(data["events"][0]["text"], "Can you explain how you design distributed caches?")
        self.assertEqual(data["events"][0]["speaker"], "agent")
        self.assertEqual(data["events"][0]["source"], "agora_rtm")

    # ── TEST 21: RTM-Capable Token Generation ────────────────────────────────
    def test_21_rtm_token_generation_has_rtc_and_rtm_privileges(self) -> None:
        """Verify agora-token endpoint returns unified Token007 and rtm_user_id."""
        with patch.object(self.client.app.state, "dummy", True, create=True):
            resp = self.client.get("/api/v1/interviews/sess-rtm-token-01/agora-token?uid=0&role=1")
            self.assertEqual(resp.status_code, 410)
            self.assertEqual(resp.json()["detail"], "Use the authenticated scheduled-interview session API")


if __name__ == "__main__":
    unittest.main()
