"""Shared asynchronous HTTP client for Ollama API integration."""

import json
from typing import Any, Optional

import httpx
import structlog

from app.core.config import settings
from app.core.exceptions import AppError

logger = structlog.stdlib.get_logger("intra_ai.integrations.ollama")

class OllamaAPIError(AppError):
    """Exception raised when an Ollama API request fails."""
    status_code = 502
    code = "OLLAMA_API_ERROR"
    message = "Ollama API request failed"


async def call_ollama(
    model: str,
    messages: list[dict[str, Any]],
    response_format: Optional[dict[str, Any]] = None,
    temperature: float = 0.2,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
    context_id: str = "unknown",
) -> dict[str, Any]:
    """Execute an asynchronous chat completion request to the Ollama Cloud API.

    Handles connection, timeouts, error mapping, and raw text extraction/JSON parsing.
    Requires `response_format={"type": "json_object"}` to guarantee JSON parsing.
    """
    api_key_val = (api_key or getattr(settings, "OLLAMA_API_KEY", "")).strip()
    base_url_val = (base_url or getattr(settings, "OLLAMA_BASE_URL", "https://ollama.com/v1")).strip().rstrip("/")
    timeout_val = timeout_seconds if timeout_seconds is not None else getattr(settings, "OLLAMA_TIMEOUT_SECONDS", 45.0)

    if not api_key_val:
        raise OllamaAPIError("OLLAMA_API_KEY is missing or empty.")

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

    try:
        async with httpx.AsyncClient(timeout=timeout_val) as client:
            response = await client.post(endpoint_url, headers=headers, json=payload)
            response.raise_for_status()
            response_json = response.json()

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
        logger.error("ollama_http_error", category=category, status_code=status_code, context_id=context_id)
        raise OllamaAPIError(f"Ollama API error [{category}] status {status_code}") from None

    except httpx.TimeoutException:
        logger.error("ollama_timeout", context_id=context_id)
        raise OllamaAPIError("NETWORK_TIMEOUT: Ollama API request timed out") from None

    except httpx.RequestError as exc:
        logger.error("ollama_network_error", error_type=type(exc).__name__, context_id=context_id)
        raise OllamaAPIError(f"NETWORK_ERROR: Failed to connect to Ollama API: {type(exc).__name__}") from None

    except Exception as exc:
        logger.error("ollama_call_failed", error_type=type(exc).__name__, context_id=context_id)
        raise OllamaAPIError(f"Ollama API call failed: {type(exc).__name__}") from None

    # Parse text from OpenAI-compatible choices format
    try:
        choices = response_json.get("choices") or []
        if not choices:
            raise OllamaAPIError("INVALID_RESPONSE: No choices returned from Ollama.")

        first_choice = choices[0]
        message = first_choice.get("message") or {}
        raw_text = (message.get("content") or "").strip()
        if not raw_text:
            raise OllamaAPIError("INVALID_RESPONSE: Empty content in Ollama message.")

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
            parsed_dict = json.loads(raw_text)
            if not isinstance(parsed_dict, dict):
                raise ValueError("Ollama JSON output is not a JSON object")
            return parsed_dict
            
        return {"content": raw_text}

    except Exception as exc:
        logger.error("ollama_invalid_response", error=str(exc), context_id=context_id)
        raise OllamaAPIError(f"INVALID_RESPONSE: Malformed response from Ollama: {exc}") from exc
