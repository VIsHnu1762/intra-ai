"""Shared asynchronous HTTP client for Groq API integration."""

import asyncio
import json
import math
import re
import time
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import AppError

logger = structlog.stdlib.get_logger("intra_ai.integrations.groq")

# Only application lifespan loops retain a connection pool. Synchronous
# compatibility providers use asyncio.run(); their temporary loops must never
# reuse a socket owned by another loop or leave a cached pool behind.
_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}


async def initialize_groq_client() -> httpx.AsyncClient:
    """Initialize the Groq HTTP pool for this application's running loop."""
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None or client.is_closed:
        client = httpx.AsyncClient(limits=httpx.Limits(keepalive_expiry=30.0))
        _clients[loop] = client
    return client


async def close_groq_client() -> None:
    """Close this loop's pool after all in-flight interview work is drained."""
    client = _clients.pop(asyncio.get_running_loop(), None)
    if client is not None:
        await client.aclose()


def _log_http_success(response: httpx.Response, data: Any, *, model: str, context_id: str, elapsed_ms: float, reused: bool) -> None:
    """Record provider timing and token counts without prompt or credential data."""
    if not isinstance(response.status_code, int) or not 200 <= response.status_code < 300:
        return
    data = data if isinstance(data, dict) else {}
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    safe_usage = {
        key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens", "queue_time", "prompt_time", "completion_time", "total_time")
        if isinstance((value := usage.get(key)), (int, float)) and not isinstance(value, bool)
    }
    response_id = data.get("id")
    logger.info(
        "[GROQ_HTTP_COMPLETE]", status_code=response.status_code,
        model=model, context_id=context_id, duration_ms=round(elapsed_ms, 1),
        provider_response_id=response_id[:128] if isinstance(response_id, str) else None,
        shared_http_client=reused, **safe_usage,
    )


class GroqAPIError(AppError):
    """Safe provider failure metadata, without retaining its response/body/key.

    status_code remains the application's 502 mapping; provider_status_code is
    the actual upstream HTTP status. M1ProviderError preserves this as __cause__.
    """
    status_code = 502
    code = "GROQ_API_ERROR"
    message = "Groq API request failed"

    def __init__(self, message: str | None = None, details: Any = None, *,
                 category: str = "GROQ_API_ERROR", provider_status_code: int | None = None,
                 retry_after_seconds: float | None = None, rate_limit_types: tuple[str, ...] = ()) -> None:
        super().__init__(message, details)
        self.category = category
        self.provider_status_code = provider_status_code
        self.retry_after_seconds = retry_after_seconds
        self.rate_limit_types = rate_limit_types
        self.rate_limit_type = rate_limit_types[0] if len(rate_limit_types) == 1 else "multiple" if rate_limit_types else None


def _nonnegative_number(value: str | None) -> float | None:
    if value is None or not isinstance(value, str) or len(value) > 128:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _reset_duration(value: str | None) -> float | None:
    """Groq reset headers contain durations such as 2m59.56s, not epochs."""
    if not value or len(value) > 128:
        return None
    value = value.strip().lower()
    numeric = _nonnegative_number(value)
    if numeric is not None:
        return numeric
    parts = re.findall(r"(\d+(?:\.\d+)?)(ms|s|m|h|d)", value)
    if not parts or "".join(number + unit for number, unit in parts) != value:
        return None
    units = {"ms": .001, "s": 1, "m": 60, "h": 3600, "d": 86400}
    total = sum(float(number) * units[unit] for number, unit in parts)
    return total if math.isfinite(total) else None


def _retry_after(value: str | None) -> float | None:
    numeric = _nonnegative_number(value)
    if numeric is not None:
        return numeric
    if not value or len(value) > 128:
        return None
    try:
        # Groq documents seconds; also accept the standard HTTP-date form.
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return None
        return max(0., date.timestamp() - time.time())
    except (TypeError, ValueError, OverflowError):
        return None


def _quota_metadata(response: httpx.Response) -> tuple[float | None, tuple[str, ...]]:
    """Extract allowlisted limit kinds; never return/log provider error prose.

    https://console.groq.com/docs/rate-limits: requests headers always describe
    requests/day, tokens headers always describe tokens/minute. Both can occur
    even on unrelated limits, so a reset header alone does not identify a limit.
    """
    try:
        payload = response.json()
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        message = error.get("message", "") if isinstance(error, dict) else ""
        message = message[:8192] if isinstance(message, str) else ""
    except (ValueError, TypeError):
        message = ""
    limit_patterns = (
        ("input_tokens_per_minute", r"\b(?:input tokens per minute|ITPM)\b"),
        ("output_tokens_per_minute", r"\b(?:output tokens per minute|OTPM)\b"),
        ("tokens_per_minute", r"\b(?:tokens per minute|TPM)\b"),
        ("tokens_per_day", r"\b(?:tokens per day|TPD)\b"),
        ("requests_per_minute", r"\b(?:requests per minute|RPM)\b"),
        ("requests_per_day", r"\b(?:requests per day|RPD)\b"),
    )
    explicit = next((kind for kind, pattern in limit_patterns if re.search(pattern, message, re.I)), None)
    if explicit:
        kinds = (explicit,)
    else:
        kinds = tuple(kind for header, kind in (
            ("x-ratelimit-remaining-tokens", "tokens_per_minute"),
            ("x-ratelimit-remaining-requests", "requests_per_day"),
        ) if _nonnegative_number(response.headers.get(header)) == 0)
    retry = _retry_after(response.headers.get("retry-after"))
    if retry is None:
        # Do not mistake TPM/RPD resets for separate RPM/TPD/ITPM/OTPM buckets.
        headers = {"tokens_per_minute": "x-ratelimit-reset-tokens", "requests_per_day": "x-ratelimit-reset-requests"}
        resets = [_reset_duration(response.headers.get(headers[kind])) for kind in kinds if kind in headers]
        known = [reset for reset in resets if reset is not None]
        retry = max(known) if known else None
    return retry, kinds


async def call_groq(
    model: str,
    messages: list[dict[str, Any]],
    response_format: Optional[dict[str, Any]] = None,
    temperature: float = 0.2,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    context_id: str = "unknown",
) -> dict[str, Any]:
    """Execute an asynchronous chat completion request to the Groq Cloud API.

    Handles connection, timeouts, error status mapping, raw text extraction,
    markdown code fence removal, and JSON parsing.
    """
    api_key_val = (api_key or getattr(settings, "GROQ_API_KEY", "")).strip()
    base_url_val = (base_url or getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")).strip().rstrip("/")
    timeout_val = timeout_seconds if timeout_seconds is not None else getattr(settings, "GROQ_TIMEOUT_SECONDS", 20.0)

    if not api_key_val:
        raise GroqAPIError("GROQ_API_KEY is missing or empty.", category="CONFIGURATION_ERROR")

    endpoint_url = f"{base_url_val}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key_val}",
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    if response_format:
        payload["response_format"] = response_format

    started = time.perf_counter()
    try:
        client = _clients.get(asyncio.get_running_loop())
        reused = client is not None and not client.is_closed
        if reused:
            response = await client.post(endpoint_url, headers=headers, json=payload, timeout=timeout_val)
        else:
            # Offline callers and short-lived asyncio.run loops own their
            # client locally. They must close it before that loop is destroyed.
            async with httpx.AsyncClient(timeout=timeout_val) as temporary_client:
                response = await temporary_client.post(endpoint_url, headers=headers, json=payload, timeout=timeout_val)
        response.raise_for_status()
        response_json = response.json()
        _log_http_success(
            response, response_json, model=model, context_id=context_id,
            elapsed_ms=(time.perf_counter() - started) * 1000, reused=reused,
        )

    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        if status_code in (401, 403):
            category = "PERMISSION_DENIED"
        elif status_code == 429:
            category = "RESOURCE_EXHAUSTED"
        elif status_code in (500, 502, 503, 504):
            category = "SERVICE_UNAVAILABLE"
        elif status_code == 400:
            category = "INVALID_ARGUMENT"
        else:
            category = f"HTTP_{status_code}"
        retry, kinds = _quota_metadata(exc.response) if status_code == 429 else (None, ())
        failure = GroqAPIError(f"Groq API error [{category}] status {status_code}",
            category=category, provider_status_code=status_code, retry_after_seconds=retry, rate_limit_types=kinds)
        logger.error("groq_http_error", category=category, status_code=status_code, context_id=context_id,
                     rate_limit_type=failure.rate_limit_type, rate_limit_types=list(kinds), retry_after_seconds=retry)
        raise failure from None

    except httpx.TimeoutException:
        logger.error("groq_timeout", context_id=context_id)
        raise GroqAPIError("NETWORK_TIMEOUT: Groq API request timed out", category="NETWORK_TIMEOUT") from None

    except httpx.RequestError as exc:
        logger.error("groq_network_error", error_type=type(exc).__name__, context_id=context_id)
        raise GroqAPIError(f"NETWORK_ERROR: Failed to connect to Groq API: {type(exc).__name__}", category="NETWORK_ERROR") from None

    except Exception as exc:
        logger.error("groq_call_failed", error_type=type(exc).__name__, context_id=context_id)
        raise GroqAPIError(f"Groq API call failed: {type(exc).__name__}") from None

    # Parse text from OpenAI-compatible choices format
    try:
        choices = response_json.get("choices") or []
        if not choices:
            raise GroqAPIError("INVALID_RESPONSE: No choices returned from Groq.")

        first_choice = choices[0]
        message = first_choice.get("message") or {}
        raw_text = (message.get("content") or "").strip()
        if not raw_text:
            raise GroqAPIError("INVALID_RESPONSE: Empty content in Groq message.")

        # Clean possible markdown code fences
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

        # If expected JSON
        if response_format and response_format.get("type") == "json_object":
            try:
                parsed_dict = json.loads(raw_text)
            except Exception as exc:
                logger.error("groq_invalid_json", error=str(exc), context_id=context_id)
                raise GroqAPIError(f"INVALID_RESPONSE: Malformed JSON from Groq: {exc}") from exc
            if not isinstance(parsed_dict, dict):
                raise GroqAPIError("INVALID_RESPONSE: Groq JSON output is not a JSON object")
            return parsed_dict

        return {"content": raw_text}

    except GroqAPIError:
        raise
    except Exception as exc:
        logger.error("groq_response_parse_failed", error=str(exc), context_id=context_id)
        raise GroqAPIError(f"INVALID_RESPONSE: Failed to parse Groq response: {exc}") from exc
