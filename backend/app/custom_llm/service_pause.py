"""A provider outage pauses assessment instead of inventing another question."""
from __future__ import annotations

import time

from app.interview_context.models import InterviewAIContext


def pause_for_service(context: InterviewAIContext, error: Exception, *, stage: str,
                      answer: str, question: str | None) -> str:
    cause = error
    for _ in range(8):
        if getattr(cause, 'provider_status_code', None) is not None or cause.__cause__ is None:
            break
        cause = cause.__cause__
    retry = getattr(cause, 'retry_after_seconds', None)
    # An application cooldown for errors without a provider retry hint. This
    # is not a promise that service will recover within this period.
    cooldown = max(1.0, float(retry)) if isinstance(retry, (int, float)) else 60.0
    context.metadata['service_pause'] = {
        'stage': stage, 'retry_at': time.time() + cooldown,
        'provider_status': getattr(cause, 'provider_status_code', None),
        'rate_limit_type': getattr(cause, 'rate_limit_type', None),
        'answer': answer, 'question': question,
    }
    context.metadata['paused'] = True
    return ("Sorry, the interview service is temporarily unavailable. Your answer has not been evaluated. "
            "Please wait, then say continue to retry.")
