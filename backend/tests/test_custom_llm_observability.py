"""Callback evidence must be correlated, secret-free, and truthful."""
import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.agents.models import ActionType, NextAction
from app.custom_llm.adapter import CustomLLMAdapter
from app.custom_llm.models import ChatMessage, InterviewTurn
from app.custom_llm.router import router
from app.interview_context import InterviewSessionStore
from app.interview_intelligence.models import AnswerAnalysis


def make_turn():
    return InterviewTurn(
        session_id="interview-observability", channel_name="intra-interview-observability",
        messages=[ChatMessage(role="user", content="Hello")],
        raw_headers={"x-agent-id": "alex", "authorization": "Bearer private-key"},
    )


def assert_correlation(log, turn):
    assert log["request_id"] == turn.turn_id
    assert log["session_id"] == turn.session_id
    assert log["channel"] == turn.channel_name
    assert log["requesting_agent_id"] == "alex"


def test_callback_logs_identity_without_credential_values():
    app = FastAPI()
    app.include_router(router)
    turn = make_turn()
    adapter = CustomLLMAdapter()
    adapter.process_turn_async = AsyncMock(return_value=("Hello there", None))
    with (patch("app.custom_llm.router.custom_llm_adapter", adapter),
          patch.object(adapter, "parse_turn", return_value=turn), capture_logs() as logs):
        response = TestClient(app).post(
            "/chat/completions?session_id=interview-observability&agent_id=alex&token=query-secret",
            headers={"Authorization": "Bearer authorization-secret", "X-Api-Key": "header-secret",
                     "X-Arbitrary-Secret": "arbitrary-secret"},
            json={"messages": [{"role": "user", "content": "Hello"}], "stream": True},
        )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == turn.turn_id
    assert response.text.endswith("data: [DONE]\n\n")
    for secret in ("query-secret", "authorization-secret", "header-secret", "arbitrary-secret", "private-key"):
        assert secret not in json.dumps(logs)
    incoming = next(log for log in logs if log["event"] == "[AGORA_INCOMING_REQUEST]")
    assert incoming["bearer_credential_present"] is True
    assert incoming["api_key_present"] is True
    assert_correlation(incoming, turn)
    stages = [log for log in logs if log["event"].startswith("[RESPONSE_STREAM")]
    for stage in stages:
        assert_correlation(stage, turn)
    complete = next(log for log in stages if log["event"] == "[RESPONSE_STREAM_COMPLETE]")
    assert complete["content_characters"] == len("Hello there")
    assert complete["boundary"] == "http_response_iterator"


def test_empty_stream_is_distinguishable_from_spoken_content():
    adapter = CustomLLMAdapter()
    adapter.process_turn_async = AsyncMock(return_value=("", None))
    async def consume():
        return [chunk async for chunk in adapter.generate_stream(make_turn())]
    with capture_logs() as logs:
        chunks = asyncio.run(consume())
    assert chunks[-1] == "data: [DONE]\n\n"
    complete = next(log for log in logs if log["event"] == "[RESPONSE_STREAM_COMPLETE]")
    assert complete["content_characters"] == 0
    assert complete["content_chunks"] == 0


@pytest.mark.parametrize("failure", [RuntimeError("provider-secret"), asyncio.CancelledError()])
def test_failed_or_cancelled_processing_never_logs_stream_complete(failure):
    turn = make_turn()
    adapter = CustomLLMAdapter()
    adapter.process_turn_async = AsyncMock(side_effect=failure)
    async def consume():
        return [chunk async for chunk in adapter.generate_stream(turn)]
    with capture_logs() as logs, pytest.raises(type(failure)):
        asyncio.run(consume())
    expected = "[RESPONSE_STREAM_FAILED]" if isinstance(failure, RuntimeError) else "[RESPONSE_STREAM_CANCELLED]"
    event = next(log for log in logs if log["event"] == expected)
    assert_correlation(event, turn)
    assert not any(log["event"] == "[RESPONSE_STREAM_COMPLETE]" for log in logs)
    assert "provider-secret" not in json.dumps(logs)


def test_closed_response_iterator_logs_cancellation_after_partial_output():
    adapter = CustomLLMAdapter()
    adapter.process_turn_async = AsyncMock(return_value=("First second", None))
    async def close_early():
        stream = adapter.generate_stream(make_turn())
        await anext(stream)
        await anext(stream)
        await stream.aclose()
    with capture_logs() as logs:
        asyncio.run(close_early())
    cancelled = next(log for log in logs if log["event"] == "[RESPONSE_STREAM_CANCELLED]")
    assert cancelled["content_chunks"] == 1
    assert not any(log["event"] == "[RESPONSE_STREAM_COMPLETE]" for log in logs)


def test_cognitive_stages_keep_callback_correlation():
    turn = make_turn()
    turn.messages = [
        ChatMessage(role="assistant", content="How did you scale Redis?"),
        ChatMessage(role="user", content="We partitioned Redis into 16 shards using consistent hashing and write-through caching."),
    ]
    store = InterviewSessionStore()
    turn.context = store.get_or_create(turn.session_id, agent_id="alex")
    analysis = AnswerAnalysis(answer_id="answer-correlated", overall_performance=0.8,
                              confidence=0.9, vague=False, contradiction_detected=False)
    adapter = CustomLLMAdapter(
        session_store=store,
        m1_analyzer=AsyncMock(analyze_async=AsyncMock(return_value=analysis)),
        orchestrator=AsyncMock(decide_async=AsyncMock(return_value=NextAction(
            action=ActionType.ASK_QUESTION, question_text="How did you handle failures?"))),
        context_builder=AsyncMock(build_turn_context_async=AsyncMock(return_value=None)),
        kg_service=AsyncMock(),
    )
    with capture_logs() as logs:
        response, _ = asyncio.run(adapter.process_turn_async(turn))
    assert response == "How did you handle failures?"
    for expected in ("[M1_START]", "[M1_COMPLETE]", "[ORCHESTRATOR_START]", "[ORCHESTRATOR]"):
        event = next(log for log in logs if log["event"] == expected)
        assert_correlation(event, turn)
        assert event["agent_id"] == "alex"
