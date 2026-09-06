"""Per-turn clocks; external clock deltas are observations, not server durations."""
import time

import structlog

from app.custom_llm.models import InterviewTurn

logger = structlog.stdlib.get_logger("intra_ai.voice_timing")


def mark(turn: InterviewTurn, stage: str) -> None:
    turn.metadata.setdefault("timings", {})[stage] = {
        "timestamp_ms": round(time.time() * 1000, 3),
        "elapsed_ms": round((time.perf_counter() - turn.metadata["t0"]) * 1000, 3),
    }


def report(turn: InterviewTurn) -> None:
    stages = turn.metadata.get("timings", {})
    durations = {}
    for label, start, end in (
        ("lock_wait_ms", "lock_wait_start", "lock_acquired"),
        ("context_ms", "context_start", "context_complete"),
        ("m1_ms", "m1_start", "m1_complete"),
        ("orchestrator_ms", "orchestrator_start", "orchestrator_complete"),
        ("adapter_ttft_ms", "custom_llm_received", "first_response_chunk_sent"),
        ("orchestrator_to_first_chunk_ms", "orchestrator_complete", "first_response_chunk_sent"),
    ):
        if start in stages and end in stages:
            durations[label] = round(stages[end]["elapsed_ms"] - stages[start]["elapsed_ms"], 3)
    received = stages.get("custom_llm_received", {}).get("timestamp_ms")
    stt = turn.metadata.get("stt_final_timestamp_ms")
    speech_end = turn.metadata.get("candidate_speech_end_ms")
    if stt and received:
        durations["stt_to_adapter_ms_external_clocks"] = round(received - stt, 3)
    if stt and speech_end:
        durations["speech_end_to_stt_ms_external_clock"] = stt - speech_end
    logger.info("[VOICE_TURN_TIMING]", request_id=turn.turn_id,
                agora_turn_id=turn.metadata.get("agora_turn_id"),
                session_id=turn.session_id, channel=turn.channel_name,
                stt_final_timestamp_ms=stt, stages=stages, durations=durations,
                note="first chunk yielded to HTTP; Agora receipt/TTS require cloud or browser evidence")
