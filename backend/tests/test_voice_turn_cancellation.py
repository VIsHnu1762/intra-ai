"""Canceled candidate turns cannot commit staged M1/orchestrator assessment."""

import asyncio

import pytest

from app.agents.models import NextAction
from app.interview_context.models import EvidenceItem, QuestionHistoryItem
from app.interview_intelligence.models import AnswerAnalysis, CompetencyFinding
from app.models.enums import ActionType, DifficultyLevel
from tests.test_voice_intent_latency import make_turn, setup_adapter


def prepared_adapter():
    adapter, context, m1, orchestrator, kg = setup_adapter()
    context.metadata["paused"] = False
    context.add_question_history(QuestionHistoryItem(
        agent_id="alex", competency="system_design", difficulty=DifficultyLevel.MEDIUM,
        question_text=context.metadata["active_interviewer_question"],
        metadata={"objective_id": "system_design:apply"},
    ))
    m1.analyze_async.return_value = AnswerAnalysis(
        answer_id="staged-answer", overall_performance=.6, confidence=.9,
        vague=False, contradiction_detected=False, missing_information=["recovery behavior"],
        evidence=[EvidenceItem(id="staged-evidence", competency="system_design",
            signal="Candidate described replaying committed Kafka offsets")],
        competency_findings=[CompetencyFinding(competency_id="system_design",
            assessment="Partial explanation", confidence=.9, evidence_ids=["staged-evidence"])],
    )
    return adapter, context, m1, orchestrator, kg


@pytest.mark.parametrize("boundary", ["context_after_m1", "orchestrator"])
def test_cancel_after_m1_preserves_canonical_context_and_emits_no_audio_or_kg(boundary):
    async def run():
        adapter, canonical, m1, orchestrator, kg = prepared_adapter()
        before = canonical.model_dump()
        waiting, release = asyncio.Event(), asyncio.Event()
        if boundary == "context_after_m1":
            async def build(**kwargs):
                # The M1 mock returns immediately; its result is ready while
                # the independent context read still has to finish.
                m1.analyze_async.assert_awaited_once()
                waiting.set()
                await release.wait()
            adapter.context_builder.build_turn_context_async = build
        else:
            async def decide(**kwargs):
                staged = kwargs["context"]
                assert staged is not canonical
                assert staged.accumulated_evidence[-1].id == "staged-evidence"
                # Verify deep isolation, including mutable historical metadata.
                staged.question_history[0].metadata["tentative"] = True
                waiting.set()
                await release.wait()
            orchestrator.decide_async.side_effect = decide

        turn = make_turn(adapter, "Kafka consumers replay committed offsets using PostgreSQL idempotency keys.")
        chunks = []
        async def consume():
            async for chunk in adapter.generate_stream(turn):
                chunks.append(chunk)
        pending = asyncio.create_task(consume())
        await asyncio.wait_for(waiting.wait(), timeout=2)
        assert canonical.model_dump() == before
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        await adapter.drain_background_tasks()
        assert canonical.model_dump() == before
        assert adapter.session_store.get(canonical.interview_id) is canonical
        assert turn.context is canonical
        assert chunks == []
        kg.persist_turn_evaluation_async.assert_not_awaited()
        if boundary == "context_after_m1":
            orchestrator.decide_async.assert_not_awaited()
        # Cancellation also releases the interview's request lock.
        assert not adapter.session_store.get_lock(canonical.interview_id).locked()

    asyncio.run(run())


def test_success_commits_once_and_preserves_canonical_model_identity():
    async def run():
        adapter, canonical, _, orchestrator, kg = prepared_adapter()
        next_question = "What should happen if the database becomes unavailable?"
        async def decide(**kwargs):
            assert kwargs["context"] is not canonical
            assert canonical.accumulated_evidence == []
            return NextAction(action=ActionType.ASK_QUESTION, target_agent_id="alex",
                competency="system_design", difficulty=DifficultyLevel.MEDIUM,
                question_text=next_question, rationale="Probe recovery",
                metadata={"objective_id": "system_design:limits", "coverage_policy": {
                    "competencies": ["system_design"], "sufficient": False, "answer_id": "staged-answer"}})
        orchestrator.decide_async.side_effect = decide
        turn = make_turn(adapter, "Kafka consumers replay committed offsets using PostgreSQL idempotency keys.")
        text, action = await adapter.process_turn_async(turn)
        await adapter.drain_background_tasks()
        assert text == next_question and action.action == ActionType.ASK_QUESTION
        assert adapter.session_store.get(canonical.interview_id) is canonical
        assert turn.context is canonical
        assert [e.id for e in canonical.accumulated_evidence] == ["staged-evidence"]
        assert canonical.metadata["active_interviewer_question"] == next_question
        assert len(canonical.question_history) == 2
        assert canonical.question_history[0].exploration_status == "PARTIAL"
        assert canonical.question_history[1].metadata["objective_id"] == "system_design:limits"
        kg.persist_turn_evaluation_async.assert_awaited_once()

    asyncio.run(run())


def test_orchestrator_failure_does_not_commit_staged_evidence_or_question():
    async def run():
        adapter, canonical, _, orchestrator, kg = prepared_adapter()
        before = canonical.model_dump()
        orchestrator.decide_async.side_effect = RuntimeError("synthetic unavailable orchestrator")
        turn = make_turn(adapter, "Kafka consumers replay committed offsets using PostgreSQL idempotency keys.")
        _, action = await adapter.process_turn_async(turn)
        await adapter.drain_background_tasks()
        assert action is None
        # Only outage state may change. The interrupted assessment is absent.
        assert canonical.metadata['service_pause']['stage'] == 'routing'
        assert canonical.metadata['paused'] is True
        after = canonical.model_dump()
        after['metadata'].pop('service_pause')
        after['metadata']['paused'] = before['metadata']['paused']
        assert after == before
        assert turn.context is canonical
        kg.persist_turn_evaluation_async.assert_not_awaited()

    asyncio.run(run())
