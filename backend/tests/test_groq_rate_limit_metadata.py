"""Mocked Groq quota responses preserve safe retry facts for the voice adapter."""

from datetime import datetime, timezone
from email.utils import format_datetime
from unittest.mock import MagicMock

import httpx
import pytest

from app.integrations import groq_client
from app.interview_intelligence.provider import GroqAnalysisProvider, M1ProviderError
from tests.test_groq_evidence_identity import turn


def install_response(monkeypatch, *, status=429, headers=None, message="Rate limit reached", content=None):
    original = httpx.AsyncClient
    requests = []
    logger = MagicMock()
    monkeypatch.setattr(groq_client, "logger", logger)

    def handler(request):
        requests.append(request)
        if content is not None:
            return httpx.Response(status, headers=headers, content=content)
        return httpx.Response(status, headers=headers, json={"error": {"message": message}})

    monkeypatch.setattr(groq_client.httpx, "AsyncClient", lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    return requests, logger


async def error_from_call():
    with pytest.raises(groq_client.GroqAPIError) as caught:
        await groq_client.call_groq("openai/gpt-oss-20b", [{"role": "user", "content": "PRIVATE_ANSWER"}],
                                    api_key="PRIVATE_KEY", context_id="synthetic-quota-turn")
    return caught.value


@pytest.mark.asyncio
async def test_retry_after_overrides_reset_and_logs_only_safe_quota_metadata(monkeypatch):
    requests, logger = install_response(monkeypatch, headers={
        "Retry-After": "2.5", "x-ratelimit-reset-tokens": "7.66s",
        "x-ratelimit-reset-requests": "2m59.56s",
    }, message="Rate limit reached for PRIVATE_MODEL in organization PRIVATE_ORG on tokens per minute (TPM). PRIVATE_ANSWER")
    error = await error_from_call()
    assert error.category == "RESOURCE_EXHAUSTED"
    assert error.provider_status_code == 429 and error.status_code == 502
    assert error.retry_after_seconds == 2.5
    assert error.rate_limit_type == "tokens_per_minute"
    assert error.rate_limit_types == ("tokens_per_minute",)
    assert len(requests) == 1  # Voice policy owns retry; no hidden transport loop.
    logger.info.assert_not_called()
    assert logger.error.call_args.kwargs["retry_after_seconds"] == 2.5
    assert logger.error.call_args.kwargs["rate_limit_type"] == "tokens_per_minute"
    assert "PRIVATE" not in str(logger.mock_calls) + str(error) + str(error.details)


@pytest.mark.asyncio
@pytest.mark.parametrize("header,reset,kind,seconds", [
    ("tokens", "7.66s", "tokens_per_minute", 7.66),
    ("requests", "2m59.56s", "requests_per_day", 179.56),
    ("requests", "1h2m3s", "requests_per_day", 3723),
    ("tokens", "250ms", "tokens_per_minute", .25),
])
async def test_exhausted_header_uses_its_documented_bucket_and_duration(monkeypatch, header, reset, kind, seconds):
    install_response(monkeypatch, headers={f"x-ratelimit-remaining-{header}": "0", f"x-ratelimit-reset-{header}": reset})
    error = await error_from_call()
    assert error.rate_limit_type == kind
    assert error.retry_after_seconds == pytest.approx(seconds)


@pytest.mark.asyncio
async def test_header_presence_alone_does_not_invent_limit_or_retry(monkeypatch):
    install_response(monkeypatch, headers={"x-ratelimit-remaining-tokens": "123",
        "x-ratelimit-remaining-requests": "77", "x-ratelimit-reset-tokens": "5s",
        "x-ratelimit-reset-requests": "1h"})
    error = await error_from_call()
    assert error.rate_limit_type is None
    assert error.retry_after_seconds is None


@pytest.mark.asyncio
@pytest.mark.parametrize("description,kind", [
    ("requests per minute (RPM)", "requests_per_minute"),
    ("tokens per day (TPD)", "tokens_per_day"),
    ("input tokens per minute (ITPM)", "input_tokens_per_minute"),
    ("output tokens per minute (OTPM)", "output_tokens_per_minute"),
])
async def test_other_buckets_never_borrow_unrelated_tpm_or_rpd_resets(monkeypatch, description, kind):
    install_response(monkeypatch, message=f"Rate limit reached on {description}",
        headers={"x-ratelimit-remaining-tokens": "0", "x-ratelimit-remaining-requests": "0",
                 "x-ratelimit-reset-tokens": "5s", "x-ratelimit-reset-requests": "1h"})
    error = await error_from_call()
    assert error.rate_limit_type == kind
    assert error.retry_after_seconds is None


@pytest.mark.asyncio
async def test_both_depleted_buckets_wait_for_longer_known_reset(monkeypatch):
    install_response(monkeypatch, headers={"x-ratelimit-remaining-tokens": "0", "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-tokens": "5s", "x-ratelimit-reset-requests": "2m"})
    error = await error_from_call()
    assert error.rate_limit_type == "multiple"
    assert error.rate_limit_types == ("tokens_per_minute", "requests_per_day")
    assert error.retry_after_seconds == 120


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["NaN", "inf", "-4", "PRIVATE_HEADER", "5s garbage", "999999999999999999999999" + "0" * 150])
async def test_malformed_retry_values_remain_unknown_and_are_never_logged(monkeypatch, invalid):
    _, logger = install_response(monkeypatch, headers={"retry-after": invalid,
        "x-ratelimit-remaining-tokens": "0", "x-ratelimit-reset-tokens": invalid}, content="PRIVATE_NON_JSON_ERROR")
    error = await error_from_call()
    assert error.retry_after_seconds is None
    assert "PRIVATE" not in str(logger.mock_calls) + str(error)


@pytest.mark.asyncio
async def test_standard_http_date_retry_after(monkeypatch):
    now = 1700000000
    monkeypatch.setattr(groq_client.time, "time", lambda: now)
    install_response(monkeypatch, headers={"retry-after": format_datetime(datetime.fromtimestamp(now + 91, timezone.utc))})
    error = await error_from_call()
    assert error.retry_after_seconds == 91


@pytest.mark.asyncio
@pytest.mark.parametrize("status,category", [(401, "PERMISSION_DENIED"), (403, "PERMISSION_DENIED"), (400, "INVALID_ARGUMENT"), (503, "SERVICE_UNAVAILABLE")])
async def test_nonquota_http_failure_keeps_status_without_quota_guess(monkeypatch, status, category):
    install_response(monkeypatch, status=status, headers={"retry-after": "3", "x-ratelimit-remaining-tokens": "0"})
    error = await error_from_call()
    assert error.provider_status_code == status and error.category == category
    assert error.retry_after_seconds is None and error.rate_limit_type is None


@pytest.mark.asyncio
async def test_m1_wrapper_preserves_typed_quota_cause_and_does_not_retry(monkeypatch):
    requests, _ = install_response(monkeypatch, headers={"retry-after": "12"},
        message="Rate limit reached on tokens per day (TPD) in PRIVATE_ORG")
    with pytest.raises(M1ProviderError) as caught:
        await GroqAnalysisProvider(api_key="PRIVATE_KEY").analyze_answer_async(turn("quota-cause"))
    cause = caught.value.__cause__
    assert isinstance(cause, groq_client.GroqAPIError)
    assert cause.category == "RESOURCE_EXHAUSTED" and cause.provider_status_code == 429
    assert cause.rate_limit_type == "tokens_per_day" and cause.retry_after_seconds == 12
    assert len(requests) == 1
    assert "PRIVATE" not in str(caught.value)
