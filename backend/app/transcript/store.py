"""In-memory transcript store for ordered, deduplicated dialogue events."""

from __future__ import annotations

import asyncio
import hashlib
from typing import Optional
import structlog

from app.transcript.models import TranscriptEvent

logger = structlog.stdlib.get_logger("intra_ai.transcript.store")


class TranscriptStore:
    """Async-safe, session-isolated transcript store.

    Guarantees:
    - Zero cross-session leakage (isolated per canonical interview_id).
    - Idempotency & deduplication by event_id and content fingerprint.
    - Intermediate-to-final turn replacement in place.
    - Deterministic ordering by (timestamp, sequence, id).
    """

    def __init__(self) -> None:
        self._events_by_interview: dict[str, list[TranscriptEvent]] = {}
        self._event_index_by_id: dict[str, dict[str, int]] = {}  # interview_id -> {event_id -> list_index}
        self._dedup_fingerprints: set[str] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def _compute_fingerprint(interview_id: str, speaker: str, timestamp: float, text: str) -> str:
        """Create a stable content fingerprint with timestamp bucketing to prevent identical duplicate deliveries."""
        # 2-second timestamp window to collapse rapid repeated re-transmissions
        time_bucket = int(timestamp // 2000)
        norm_text = " ".join(text.lower().strip().split())
        content_hash = hashlib.sha256(norm_text.encode("utf-8")).hexdigest()[:16]
        return f"{interview_id}:{speaker}:{time_bucket}:{content_hash}"

    async def add_event(self, event: TranscriptEvent) -> bool:
        """Add or update a transcript event. Returns True if inserted or updated, False if duplicate ignored."""
        async with self._lock:
            return self.add_event_sync(event)

    def add_event_sync(self, event: TranscriptEvent) -> bool:
        """Synchronous version for lightweight execution."""
        interview_id = event.interview_id

        if interview_id not in self._events_by_interview:
            self._events_by_interview[interview_id] = []
            self._event_index_by_id[interview_id] = {}

        event_indices = self._event_index_by_id[interview_id]
        event_list = self._events_by_interview[interview_id]

        # 1. Check for existing event by exact event ID (Intermediate -> Final replacement)
        if event.id in event_indices:
            idx = event_indices[event.id]
            existing = event_list[idx]
            # If incoming is final or text changed, update in-place
            if existing.text != event.text or (not existing.is_final and event.is_final):
                event_list[idx] = event
                logger.info(
                    "[TRANSCRIPT_UPDATED]",
                    interview_id=interview_id,
                    event_id=event.id,
                    speaker=event.speaker.value,
                    is_final=event.is_final,
                )
                return True
            # Otherwise duplicate
            logger.info(
                "[TRANSCRIPT_DUPLICATE]",
                interview_id=interview_id,
                event_id=event.id,
                reason="id_matched",
            )
            return False

        # 2. Check fingerprint deduplication (only if is_final to avoid dropping progressive streaming)
        fingerprint = self._compute_fingerprint(
            interview_id=interview_id,
            speaker=event.speaker.value,
            timestamp=event.timestamp,
            text=event.text,
        )

        if event.is_final and fingerprint in self._dedup_fingerprints:
            logger.info(
                "[TRANSCRIPT_DUPLICATE]",
                interview_id=interview_id,
                event_id=event.id,
                reason="fingerprint_matched",
            )
            return False

        # 3. Assign sequence if missing
        if event.sequence is None:
            event.sequence = len(event_list) + 1

        # 4. Insert event and register indices
        new_idx = len(event_list)
        event_list.append(event)
        event_indices[event.id] = new_idx
        if event.is_final:
            self._dedup_fingerprints.add(fingerprint)

        # 5. Maintain deterministic ordering
        event_list.sort(key=lambda e: (e.timestamp, e.sequence or 0, e.id))
        # Re-index after sorting
        self._event_index_by_id[interview_id] = {e.id: i for i, e in enumerate(event_list)}

        logger.info(
            "[TRANSCRIPT_STORED]",
            interview_id=interview_id,
            event_id=event.id,
            speaker=event.speaker.value,
            timestamp=event.timestamp,
            sequence=event.sequence,
            is_final=event.is_final,
        )
        return True

    def get_transcript(
        self,
        interview_id: str,
        is_final_only: bool = True,
    ) -> list[TranscriptEvent]:
        """Retrieve ordered transcript events for a canonical interview_id."""
        events = self._events_by_interview.get(interview_id, [])
        if is_final_only:
            return [e for e in events if e.is_final]
        return list(events)

    def count_events(self, interview_id: str) -> int:
        """Return count of stored events for an interview."""
        return len(self._events_by_interview.get(interview_id, []))

    def clear(self, interview_id: Optional[str] = None) -> None:
        """Clear store for a specific interview or completely."""
        if interview_id:
            self._events_by_interview.pop(interview_id, None)
            self._event_index_by_id.pop(interview_id, None)
            # Remove matching fingerprints
            prefix = f"{interview_id}:"
            self._dedup_fingerprints = {fp for fp in self._dedup_fingerprints if not fp.startswith(prefix)}
        else:
            self._events_by_interview.clear( )
            self._event_index_by_id.clear()
            self._dedup_fingerprints.clear()


# Global singleton instance
transcript_store = TranscriptStore()
