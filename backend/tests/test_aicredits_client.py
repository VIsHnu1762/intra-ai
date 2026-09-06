"""Contract tests use synthetic assessments and HTTP MockTransport, never keys/network."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.integrations.aicredits_client import AICreditsClient, AICreditsError, MAX_RESPONSE_BYTES


def config(**changes):
    values = dict(AICREDITS_API_KEY_GPT5_NANO="nano-test-secret",
                  AICREDITS_API_KEY_GEMINI_FLASH_LITE="gemini-test-secret",
                  AICREDITS_GPT5_NANO_MODEL="openai/gpt-5-nano",
                  AICREDITS_GEMINI_FLASH_LITE_MODEL="google/gemini-2.5-flash-lite",
                  AICREDITS_BASE_URL="https://api.aicredits.in/v1",
                  AICREDITS_TIMEOUT_SECONDS=60,
                  GROQ_API_KEY="never-use-groq", OPENAI_API_KEY="never-use-openai")
    return SimpleNamespace(**(values | changes))


ASSESSMENT = {"overall_score": 72, "score_band": "solid", "star_rating": 4,
              "coverage": {"round_count": 2, "agent_count": 2, "evidence_count": 2},
              "evidence": [{"id": "e-one", "score": 7, "agent_id": "alex"},
                           {"id": "e-two", "score": 7.4, "agent_id": "jordan"}]}
NARRATIVE = {"overall_summary": "Demonstrated solid overall performance.",
             "strengths": [{"text": "You explained your choices clearly.", "evidence_ids": ["e-one"]}],
             "improvements": [{"text": "Support your choices with measured results.", "evidence_ids": ["e-two"]}]}


def envelope(value=NARRATIVE, **choice_changes):
    return {"choices": [{"message": {"role": "assistant", "content": json.dumps(value)},
                         "finish_reason": "stop", **choice_changes}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}}


@pytest.mark.asyncio
async def test_exact_endpoint_models_and_separate_keys_for_each_persisted_step():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=envelope())
    client = AICreditsClient(config(), transport=httpx.MockTransport(handler))
    assert await client.generate_report_narrative(ASSESSMENT) == NARRATIVE
    assert await client.generate_candidate_feedback(ASSESSMENT, NARRATIVE) == NARRATIVE
    assert len(seen) == 2
    assert all(str(request.url) == "https://api.aicredits.in/v1/chat/completions" for request in seen)
    assert [request.headers["authorization"] for request in seen] == ["Bearer nano-test-secret", "Bearer gemini-test-secret"]
    report, feedback = [json.loads(request.content) for request in seen]
    assert report["model"] == "openai/gpt-5-nano"
    assert feedback["model"] == "google/gemini-2.5-flash-lite"
    assert report["max_completion_tokens"] == 8192 and "max_tokens" not in report
    assert report["reasoning_effort"] == "minimal"
    assert feedback["max_tokens"] == 1024 and "max_completion_tokens" not in feedback
    assert "temperature" not in report
    assert all(body["response_format"] == {"type": "json_object"} and body["stream"] is False and body["no_cache"] is True
               for body in [report, feedback])
    assert json.loads(report["messages"][1]["content"]) == ASSESSMENT
    assert "ALL" in report["messages"][0]["content"]
    assert "Do not rescore" in report["messages"][0]["content"]


@pytest.mark.asyncio
async def test_candidate_projection_omits_private_assessment_and_report_fields():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=envelope({"strength": "Clear reasoning.", "improvement": "Add specific outcomes."}))
    assessment = ASSESSMENT | {"candidate_name": "Private Name", "email": "private@example.test",
        "cv": "private CV", "answers": "private answer", "recommendation": "hire",
        "private_reasoning": "private reasoning", "coverage": ASSESSMENT["coverage"] | {"internal_notes": "private note"}}
    narrative = NARRATIVE | {"overall_summary": "PRIVATE SUMMARY", "hiring_risk_notes": "PRIVATE RISK"}
    await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_candidate_feedback(assessment, narrative)
    payload = json.loads(seen[0]["messages"][1]["content"])
    assert payload == {"overall_score": 72, "score_band": "solid", "star_rating": 4,
                       "coverage": ASSESSMENT["coverage"],
                       "strengths": [NARRATIVE["strengths"][0]["text"]],
                       "improvements": [NARRATIVE["improvements"][0]["text"]]}
    assert "private" not in json.dumps(payload).lower()
    assert "evidence_ids" not in json.dumps(payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["AICREDITS_API_KEY_GPT5_NANO", "AICREDITS_API_KEY_GEMINI_FLASH_LITE"])
async def test_missing_own_key_never_uses_other_provider_key(missing):
    def handler(_):
        pytest.fail("No HTTP call is allowed with the required key missing")
    client = AICreditsClient(config(**{missing: " "}), transport=httpx.MockTransport(handler))
    with pytest.raises(AICreditsError) as caught:
        if missing.endswith("GPT5_NANO"):
            await client.generate_report_narrative(ASSESSMENT)
        else:
            await client.generate_candidate_feedback(ASSESSMENT, NARRATIVE)
    assert caught.value.code == "configuration_missing"
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_one_missing_key_does_not_disable_other_stage():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=envelope()))
    assert await AICreditsClient(config(AICREDITS_API_KEY_GEMINI_FLASH_LITE=""), transport=transport).generate_report_narrative(ASSESSMENT) == NARRATIVE
    assert await AICreditsClient(config(AICREDITS_API_KEY_GPT5_NANO=""), transport=transport).generate_candidate_feedback(ASSESSMENT, NARRATIVE) == NARRATIVE


@pytest.mark.asyncio
async def test_configurable_models_and_base_preserve_slot_key():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=envelope())
    await AICreditsClient(config(AICREDITS_BASE_URL="https://api.aicredits.in/custom/v1/", AICREDITS_GPT5_NANO_MODEL="openai/configured-nano"),
                          transport=httpx.MockTransport(handler)).generate_report_narrative(ASSESSMENT)
    assert str(seen[0].url) == "https://api.aicredits.in/custom/v1/chat/completions"
    assert json.loads(seen[0].content)["model"] == "openai/configured-nano"
    assert seen[0].headers["authorization"] == "Bearer nano-test-secret"


@pytest.mark.asyncio
@pytest.mark.parametrize("status,code,retryable", [(400, "provider_error", False), (401, "authentication_failed", False),
    (402, "credits_exhausted", False), (403, "access_denied", False), (413, "input_too_large", False),
    (429, "rate_limited", True), (500, "provider_error", True), (502, "provider_error", True),
    (503, "model_unavailable", False), (504, "timeout", True)])
async def test_safe_http_errors_no_automatic_retries_or_fallback(status, code, retryable, caplog):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(status, json={"error": {"message": "nano-test-secret private answer"}})
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_report_narrative(ASSESSMENT)
    assert (caught.value.code, caught.value.retryable, caught.value.status_code) == (code, retryable, status)
    assert len(seen) == 1
    assert "nano-test-secret" not in str(caught.value) + repr(caught.value) + caplog.text
    assert "private answer" not in str(caught.value) + caplog.text


@pytest.mark.asyncio
async def test_redirect_does_not_forward_credentials_to_another_host():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(307, headers={"Location": "https://other.example.test/steal"})
    with pytest.raises(AICreditsError):
        await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_report_narrative(ASSESSMENT)
    assert len(seen) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault,code", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "transport_error")])
async def test_transport_failure_redacts_exception(fault, code):
    def handler(request):
        raise fault("nano-test-secret private answer", request=request)
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_report_narrative(ASSESSMENT)
    assert caught.value.code == code and caught.value.retryable
    assert "nano-test-secret" not in str(caught.value)
    assert caught.value.__suppress_context__


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b"<html>error</html>", b'{"choices":[]}', b'{"choices":{}}',
    json.dumps(envelope([],)).encode(), json.dumps(envelope({}, message={"content": ""})).encode(),
    json.dumps(envelope({}, message={"content": '{}', "refusal": "refused"})).encode(),
    json.dumps(envelope({}, message={"content": '{"score":NaN}'})).encode(),
    json.dumps(envelope({}, message={"content": '{"a":1,"a":2}'})).encode(),
    json.dumps(envelope({}, message={"content": '```json\n{}\n```'})).encode(),
    json.dumps(envelope({}, message={"content": '{"summary":"unfinished'})).encode()])
async def test_invalid_responses_are_not_repaired_or_fabricated(raw):
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw))).generate_report_narrative(ASSESSMENT)
    assert caught.value.code == "response_invalid"


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["length", "content_filter", "tool_calls", None])
async def test_reject_incomplete_even_if_provider_healed_json(reason):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=envelope(finish_reason=reason)))
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=transport).generate_report_narrative(ASSESSMENT)
    assert caught.value.code == "response_incomplete"


@pytest.mark.asyncio
async def test_output_bound_rejects_large_provider_body():
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * (MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=transport).generate_report_narrative(ASSESSMENT)
    assert caught.value.code == "response_too_large"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,code", [({}, "input_invalid"), ({"value": float("nan")}, "input_invalid"),
    ({"value": object()}, "input_invalid"), ({"text": "x" * 512000}, "input_too_large")])
async def test_input_bounds_reject_before_any_request(payload, code):
    def handler(_):
        pytest.fail("Invalid input must not reach the provider")
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_report_narrative(payload)
    assert caught.value.code == code


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [{"AICREDITS_BASE_URL": "http://api.aicredits.in/v1"},
    {"AICREDITS_BASE_URL": "https://user:password@api.aicredits.in/v1"},
    {"AICREDITS_BASE_URL": "https://api.aicredits.in/v1?token=private"},
    {"AICREDITS_BASE_URL": "https://api.aicredits.in/v1#private"},
    {"AICREDITS_BASE_URL": "https://api.aicredits.in:bad/v1"},
    {"AICREDITS_GPT5_NANO_MODEL": " "}, {"AICREDITS_TIMEOUT_SECONDS": float("nan")},
    {"AICREDITS_API_KEY_GPT5_NANO": "secret\r\nInjected: value"}])
async def test_invalid_configuration_fails_closed(changes):
    def handler(_):
        pytest.fail("Invalid config must not reach the provider")
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(**changes), transport=httpx.MockTransport(handler)).generate_report_narrative(ASSESSMENT)
    assert caught.value.code == "configuration_invalid"


def test_settings_empty_placeholders_use_defaults_and_hide_key_repr():
    from app.core.config import Settings
    settings = Settings(_env_file=None, SUPABASE_URL="https://example.test", SUPABASE_ANON_KEY="test",
                        SUPABASE_SERVICE_ROLE_KEY="test", DATABASE_URL="test", OPENAI_API_KEY="test", JWT_SECRET="test",
                        AICREDITS_API_KEY_GPT5_NANO="unique-nano-secret", AICREDITS_API_KEY_GEMINI_FLASH_LITE="unique-gemini-secret",
                        AICREDITS_GPT5_NANO_MODEL="", AICREDITS_GEMINI_FLASH_LITE_MODEL="",
                        AICREDITS_BASE_URL="", AICREDITS_TIMEOUT_SECONDS="")
    assert settings.AICREDITS_GPT5_NANO_MODEL == "openai/gpt-5-nano"
    assert settings.AICREDITS_GEMINI_FLASH_LITE_MODEL == "google/gemini-2.5-flash-lite"
    assert settings.AICREDITS_BASE_URL == "https://api.aicredits.in/v1" and settings.AICREDITS_TIMEOUT_SECONDS == 60
    assert "unique-nano-secret" not in repr(settings) and "unique-gemini-secret" not in repr(settings)


@pytest.mark.asyncio
async def test_intelligence_preserves_multimessage_repairs_and_routes_distinct_slots():
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=envelope({"ok": True}))
    messages = [{"role": "system", "content": "Exact system instructions."},
                {"role": "user", "content": "Original prose input."},
                {"role": "assistant", "content": '{"invalid":true}'},
                {"role": "user", "content": "Correct the existing schema only."}]
    client = AICreditsClient(config(AICREDITS_REALTIME_TIMEOUT_SECONDS=21), transport=httpx.MockTransport(handler))
    for purpose in ["m1", "orchestrator"]:
        assert await client.generate_intelligence(purpose, messages=messages, context_id="private-trace-id") == {"ok": True}
    first, second = [json.loads(request.content) for request in seen]
    assert first["messages"] == second["messages"] == messages
    assert first["model"] == "openai/gpt-5-nano" and second["model"] == "google/gemini-2.5-flash-lite"
    assert [request.headers["authorization"] for request in seen] == ["Bearer nano-test-secret", "Bearer gemini-test-secret"]
    assert "private-trace-id" not in seen[0].content.decode()
    assert first["max_completion_tokens"] == 8192 and second["max_tokens"] == 4096
    assert first["reasoning_effort"] == "minimal" and "reasoning_effort" not in second
    assert all(request.extensions["timeout"]["read"] == 21 for request in seen)


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose,messages,code", [("unknown", [{"role":"user","content":"hi"}], "configuration_invalid"),
    ("m1", [], "input_invalid"), ("m1", [{"role": [], "content": "hi"}], "input_invalid"),
    ("m1", [{"role": "tool", "content": "hi"}], "input_invalid")])
async def test_intelligence_rejects_unknown_slot_or_malformed_messages_before_request(purpose, messages, code):
    def handler(_): pytest.fail("Invalid request must not reach provider")
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_intelligence(purpose, messages=messages)
    assert caught.value.code == code


@pytest.mark.asyncio
async def test_reasoning_setting_is_m1_only_and_invalid_values_never_reach_provider():
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=envelope({"ok": True}))
    client = AICreditsClient(config(AICREDITS_M1_REASONING_EFFORT="low"), transport=httpx.MockTransport(handler))
    await client.generate_intelligence("m1", messages=[{"role": "user", "content": "JSON please"}])
    await client.generate_report_narrative(ASSESSMENT)
    assert seen[0]["reasoning_effort"] == "low"
    assert seen[1]["reasoning_effort"] == "minimal"  # Independent report formatting budget, not M1's override.
    with pytest.raises(AICreditsError) as caught:
        await AICreditsClient(config(AICREDITS_M1_REASONING_EFFORT="unknown"), transport=httpx.MockTransport(handler)).generate_intelligence(
            "m1", messages=[{"role": "user", "content": "JSON please"}])
    assert caught.value.code == "configuration_invalid" and len(seen) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["openai/gpt-4.1-nano", "google/gemini-2.5-flash-lite", "google/gemini-3.1-flash-lite", "groq/llama-3.1-8b-instant"])
async def test_fast_model_overrides_do_not_inherit_gpt5_reasoning_parameters(model):
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=envelope({"ok": True}))
    await AICreditsClient(config(AICREDITS_M1_MODEL=model), transport=httpx.MockTransport(handler)).generate_intelligence(
        "m1", messages=[{"role": "user", "content": "Return JSON"}])
    assert seen[0]["model"] == model and seen[0]["max_tokens"] == 8192
    assert "max_completion_tokens" not in seen[0] and "reasoning_effort" not in seen[0]


@pytest.mark.asyncio
async def test_realtime_model_selection_keeps_report_models_and_credential_slots_independent():
    seen = []
    def handler(request):
        seen.append((json.loads(request.content), request.headers["authorization"]))
        return httpx.Response(200, json=envelope({"ok": True}))
    client = AICreditsClient(config(AICREDITS_M1_MODEL="groq/llama-3.1-8b-instant", AICREDITS_ORCHESTRATOR_MODEL="openai/gpt-4.1-nano"), transport=httpx.MockTransport(handler))
    for purpose in ("m1", "orchestrator"):
        await client.generate_intelligence(purpose, messages=[{"role": "user", "content": "Return JSON"}])
    await client.generate_report_narrative(ASSESSMENT)
    await client.generate_candidate_feedback(ASSESSMENT, NARRATIVE)
    assert [body["model"] for body, _ in seen] == ["groq/llama-3.1-8b-instant", "openai/gpt-4.1-nano", "openai/gpt-5-nano", "google/gemini-2.5-flash-lite"]
    assert [key for _, key in seen] == ["Bearer nano-test-secret", "Bearer gemini-test-secret", "Bearer nano-test-secret", "Bearer gemini-test-secret"]


@pytest.mark.asyncio
async def test_candidate_coverage_projects_canonical_report_counts_without_identifiers():
    from app.services.report_evaluation import build_evaluation
    rounds = [{"id": "private-round-a", "type": "technical", "agent_ids": ["alex", "jordan"], "enabled": True}]
    interview = {"id": "private-interview", "candidate_id": "private-candidate", "status": "completed", "template_snapshot": {"rounds": rounds}}
    answers = [{"id": f"private-answer-{n}", "interview_id": "private-interview", "round_id": "private-round-a", "agent_id": "alex",
                "transcript": "I used database transactions.", "question_text": "How did you handle writes?"} for n in (1, 2)]
    context = {"interview_id": "private-interview", "candidate_id": "private-candidate", "accumulated_evidence": [
        {"id": f"private-evidence-{n}", "signal": "I used database transactions.", "competency": "system_design", "score": 7,
         "round_id": "private-round-a", "source_agent_id": "alex", "metadata": {"answer_id": f"private-answer-{n}"}} for n in (1, 2)]}
    assessment = build_evaluation(interview, context, [], answers)
    seen = []
    def handler(request):
        seen.append(json.loads(json.loads(request.content)["messages"][1]["content"]))
        return httpx.Response(200, json=envelope({"strength": "Clear explanations.", "improvement": "Add outcomes."}))
    await AICreditsClient(config(), transport=httpx.MockTransport(handler)).generate_candidate_feedback(assessment, NARRATIVE)
    assert seen[0]["coverage"] == {"evaluated_answer_count": 2, "scored_answer_count": 2,
        "evaluated_rounds": 1, "evaluated_agents": 1, "total_rounds": 1, "total_agents": 2}
    assert "private-" not in json.dumps(seen[0]) and "alex" not in json.dumps(seen[0])
