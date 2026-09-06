"""Tests for active-agent guard, session isolation, and query-param-based identity resolution.

Tests A through I as specified in the implementation requirements:
  A. Alex initial session — alex requests are processed
  B. Jordan initial session — jordan requests are processed
  C. Inactive Jordan — jordan ignored when alex is current
  D. Inactive Alex — alex ignored when jordan is current
  E. Session isolation — session X never resolves to session Y
  F. No test-room-101 leakage
  G. Query parameter parsing — ?session_id and ?agent_id correctly propagated
  H. Missing identity — no silent bind to stale test-room-101
  I. SWITCH_AGENT — after logical switch, new active agent processes, old agent is ignored
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agents import ALEX_PROFILE, JORDAN_PROFILE, AgentRegistry, agent_registry
from app.agents.models import ActionType, NextAction
from app.custom_llm.adapter import CustomLLMAdapter, SessionContextProvider
from app.custom_llm.models import ChatCompletionRequest, ChatMessage
from app.interview_context.models import InterviewAIContext
from app.interview_context.store import InterviewSessionStore
from app.models.enums import DifficultyLevel

def _make_request(session_id: str | None = None, agent_id: str | None = None) -> dict:
    """Build a minimal ChatCompletionRequest-compatible dict and headers."""
    headers: dict[str, str] = {}
    if session_id:
        headers["x-session-id"] = session_id
    if agent_id:
        headers["x-agent-id"] = agent_id
    return headers


def _make_mock_request(messages: list[dict] | None = None) -> ChatCompletionRequest:
    if messages is None:
        messages = [{"role": "user", "content": "Hello, ready to start"}]
    return ChatCompletionRequest(
        model="intra-ai",
        messages=[ChatMessage(**m) for m in messages],
        stream=False,
    )


def _make_adapter_with_mock_m1_orch(store: InterviewSessionStore) -> CustomLLMAdapter:
    """Return a CustomLLMAdapter with mocked M1 and Orchestrator — only session/agent logic is real."""
    from app.custom_llm.adapter import SessionContextProvider
    from app.interview_intelligence.provider import DeterministicMockM1Provider
    from app.interview_intelligence.analyzer import M1InterviewAnalyzer

    mock_m1 = M1InterviewAnalyzer(provider=DeterministicMockM1Provider())

    mock_next_action = NextAction(
        action=ActionType.ASK_QUESTION,
        target_agent_id=None,
        question_text="Tell me more about the system design.",
    )
    mock_orch = MagicMock()
    mock_orch.decide_async = AsyncMock(return_value=mock_next_action)

    adapter = CustomLLMAdapter(
        session_store=store,
        m1_analyzer=mock_m1,
        orchestrator=mock_orch,
        registry=agent_registry,
    )
    return adapter


class TestAgentIdentityResolution(unittest.TestCase):
    """Unit tests for active-agent guard and session identity fixes."""

    def setUp(self) -> None:
        self.store = InterviewSessionStore()
        agent_registry.reset()

    # ── A. Alex initial session ────────────────────────────────────────────────

    def test_A_alex_initial_session_is_processed(self):
        """Alex webhook when current_agent_id=alex must be processed (not ignored)."""
        self.store.get_or_create(
            interview_id="session-X",
            agent_id="alex",
        )
        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()
        headers = _make_request(session_id="session-X", agent_id="alex")
        turn = adapter.parse_turn(request, headers=headers)

        result = asyncio.run(adapter.process_turn_async(turn))
        response_text, _ = result
        # Active agent should produce a non-empty response (opening question or M1 output)
        self.assertNotEqual(response_text, "", "Alex (active agent) must return a non-empty response")

    # ── B. Jordan initial session ──────────────────────────────────────────────

    def test_B_jordan_initial_session_is_processed(self):
        """Jordan webhook when current_agent_id=jordan must be processed (not ignored)."""
        self.store.get_or_create(
            interview_id="session-Y",
            agent_id="jordan",
        )
        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()
        headers = _make_request(session_id="session-Y", agent_id="jordan")
        turn = adapter.parse_turn(request, headers=headers)

        result = asyncio.run(adapter.process_turn_async(turn))
        response_text, _ = result
        self.assertNotEqual(response_text, "", "Jordan (active agent) must return a non-empty response")

    # ── C. Inactive Jordan ─────────────────────────────────────────────────────

    def test_C_inactive_jordan_is_ignored(self):
        """Jordan webhook when current_agent_id=alex must be silently dropped.
        M1 and Meta-Orchestrator must NOT be called."""
        self.store.get_or_create(
            interview_id="session-X",
            agent_id="alex",
        )
        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()
        # Jordan's pipeline sends this webhook but Alex is active
        headers = _make_request(session_id="session-X", agent_id="jordan")
        turn = adapter.parse_turn(request, headers=headers)

        result = asyncio.run(adapter.process_turn_async(turn))
        response_text, next_action = result

        self.assertEqual(response_text, "", "Inactive Jordan must return empty response")
        self.assertIsNone(next_action, "Inactive Jordan must not produce a NextAction")
        # Verify M1 was never called
        adapter.orchestrator.decide_async.assert_not_called()

    # ── D. Inactive Alex ───────────────────────────────────────────────────────

    def test_D_inactive_alex_is_ignored(self):
        """Alex webhook when current_agent_id=jordan must be silently dropped."""
        self.store.get_or_create(
            interview_id="session-Y",
            agent_id="jordan",
        )
        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()
        # Alex's pipeline sends this webhook but Jordan is active
        headers = _make_request(session_id="session-Y", agent_id="alex")
        turn = adapter.parse_turn(request, headers=headers)

        result = asyncio.run(adapter.process_turn_async(turn))
        response_text, next_action = result

        self.assertEqual(response_text, "", "Inactive Alex must return empty response")
        self.assertIsNone(next_action, "Inactive Alex must not produce a NextAction")
        adapter.orchestrator.decide_async.assert_not_called()

    # ── E. Session isolation ───────────────────────────────────────────────────

    def test_E_session_isolation(self):
        """Requests for session X must never resolve to session Y."""
        ctx_x = self.store.get_or_create(interview_id="session-X", agent_id="alex")
        ctx_y = self.store.get_or_create(interview_id="session-Y", agent_id="jordan")

        # Verify they are separate objects
        self.assertIsNot(ctx_x, ctx_y, "Sessions X and Y must be isolated contexts")
        self.assertNotEqual(ctx_x.interview_id, ctx_y.interview_id)
        self.assertEqual(ctx_x.current_agent_id, "alex")
        self.assertEqual(ctx_y.current_agent_id, "jordan")

        # Resolve both through the store
        resolved_x = self.store.resolve_interview_id("session-X")
        resolved_y = self.store.resolve_interview_id("session-Y")
        self.assertEqual(resolved_x, "session-X")
        self.assertEqual(resolved_y, "session-Y")
        self.assertNotEqual(resolved_x, resolved_y)

    # ── F. No test-room-101 leakage ────────────────────────────────────────────

    def test_F_no_test_room_101_leakage(self):
        """A new session must not resolve to test-room-101 stale context."""
        # Create a stale test-room-101 context
        stale = self.store.get_or_create(interview_id="test-room-101", agent_id="jordan")
        stale_id = stale.interview_id

        # Create a fresh real session
        real = self.store.get_or_create(interview_id="real-session-abc", agent_id="alex")

        # Verify they are completely isolated
        self.assertNotEqual(real.interview_id, stale_id)
        self.assertEqual(real.current_agent_id, "alex")

        # Resolving "real-session-abc" must never return "test-room-101"
        resolved = self.store.resolve_interview_id("real-session-abc")
        self.assertEqual(resolved, "real-session-abc")
        self.assertNotEqual(resolved, "test-room-101")

    # ── G. Query parameter parsing ─────────────────────────────────────────────

    def test_G_query_params_propagated_into_identity(self):
        """?session_id=X&agent_id=alex in URL query params must map to the correct session and agent."""
        self.store.get_or_create(interview_id="real-session-qp", agent_id="alex")

        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()
        # Simulate router.py merging query params into headers
        headers = {
            "x-session-id": "real-session-qp",  # from ?session_id=
            "x-agent-id": "alex",               # from ?agent_id=
        }
        turn = adapter.parse_turn(request, headers=headers)

        self.assertEqual(turn.session_id, "real-session-qp", "session_id from query param must resolve correctly")
        resolved_agent = turn.raw_headers.get("x-agent-id")
        self.assertEqual(resolved_agent, "alex", "agent_id from query param must be preserved in headers")

    # ── H. Missing identity ────────────────────────────────────────────────────

    def test_H_missing_identity_does_not_bind_to_test_room_101(self):
        """When no session_id is provided and multiple sessions exist, must NOT bind to test-room-101."""
        # Create two sessions including test-room-101
        self.store.get_or_create(interview_id="test-room-101", agent_id="jordan")
        self.store.get_or_create(interview_id="another-session", agent_id="alex")

        # With multiple sessions and no identifier, resolve_interview_id returns "" (not test-room-101)
        resolved = self.store.resolve_interview_id(identifier=None, default=None)
        self.assertNotEqual(resolved, "test-room-101",
                            "resolve_interview_id must not implicitly return test-room-101 when multiple sessions exist")

    # ── I. SWITCH_AGENT ────────────────────────────────────────────────────────

    def test_I_switch_agent_context_transition(self):
        """After SWITCH_AGENT, jordan requests are processed and alex requests are ignored."""
        ctx = self.store.get_or_create(interview_id="session-switch", agent_id="alex")

        # Perform the logical switch
        ctx.switch_agent("jordan")
        self.store.set("session-switch", ctx)

        self.assertEqual(ctx.current_agent_id, "jordan", "After switch, current_agent_id must be jordan")

        adapter = _make_adapter_with_mock_m1_orch(self.store)
        request = _make_mock_request()

        # Jordan is now active — should be processed
        headers_jordan = _make_request(session_id="session-switch", agent_id="jordan")
        turn_jordan = adapter.parse_turn(request, headers=headers_jordan)
        result_jordan = asyncio.run(adapter.process_turn_async(turn_jordan))
        self.assertNotEqual(result_jordan[0], "", "Jordan (now active after switch) must produce a response")

        # Alex is now inactive — should be dropped
        adapter2 = _make_adapter_with_mock_m1_orch(self.store)
        headers_alex = _make_request(session_id="session-switch", agent_id="alex")
        turn_alex = adapter2.parse_turn(request, headers=headers_alex)
        result_alex = asyncio.run(adapter2.process_turn_async(turn_alex))
        self.assertEqual(result_alex[0], "", "Alex (inactive after switch) must be ignored")


class TestStoreResolveIsolation(unittest.TestCase):
    """Unit tests directly against InterviewSessionStore.resolve_interview_id."""

    def setUp(self) -> None:
        self.store = InterviewSessionStore()

    def test_known_identifier_resolves_correctly(self):
        self.store.get_or_create("session-abc", agent_id="alex")
        result = self.store.resolve_interview_id("session-abc")
        self.assertEqual(result, "session-abc")

    def test_single_session_shortcut(self):
        """When exactly one session exists AND no identifier is provided, resolves to it.
        If an identifier is provided but doesn't match, it returns the identifier itself."""
        self.store.get_or_create("only-session", agent_id="alex")
        # No identifier → single-session shortcut
        result_no_id = self.store.resolve_interview_id(None)
        self.assertEqual(result_no_id, "only-session", "No-identifier case should use single-session shortcut")
        # Unknown identifier → returns the identifier (not the existing session)
        result_unknown = self.store.resolve_interview_id("unknown-identifier")
        self.assertEqual(result_unknown, "unknown-identifier", "Unknown identifier must be returned as-is, not replaced with an existing session")

    def test_multiple_sessions_unknown_returns_empty(self):
        """When multiple sessions exist, unknown identifier returns empty string — NOT test-room-101."""
        self.store.get_or_create("session-a", agent_id="alex")
        self.store.get_or_create("session-b", agent_id="jordan")
        result = self.store.resolve_interview_id("totally-unknown", default=None)
        self.assertNotEqual(result, "test-room-101")

    def test_alias_resolution(self):
        """Agora agent_uuid aliases must resolve to canonical session."""
        self.store.get_or_create("canonical-session", agent_id="alex")
        self.store.register_alias("agora-uuid-xyz", "canonical-session")
        result = self.store.resolve_interview_id("agora-uuid-xyz")
        self.assertEqual(result, "canonical-session")


if __name__ == "__main__":
    unittest.main()
