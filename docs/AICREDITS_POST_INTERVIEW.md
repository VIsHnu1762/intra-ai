# AICredits provider slots and post-interview outputs

Contract verified against official AICredits documentation on 2026-09-06.
The final user instruction selects **paid AICredits for both realtime layers**,
because the existing Groq connection encountered rate limits. The local backend
and `.env.example` now select `M1_PROVIDER=aicredits` and
`ORCHESTRATOR_PROVIDER=aicredits`, with both realtime model overrides set to
`google/gemini-3.1-flash-lite`. The restarted container's effective settings
were verified on 2026-09-06. There is no automatic fallback to Groq.
AICredits Nano and Gemini 2.5 Flash-Lite retain their independent post-interview
report purposes and credential slots. The variable names retain compatibility;
they do not force the realtime models to use Nano or Gemini 2.5.

The selected configuration passed two grounded fictional text turns with actual
M1 output supplied to Meta: **5.102 seconds and 4.708 seconds** for the two model
stages combined. Both used exactly one request per stage, preserved current
answer quotations and score units, and produced connected follow-up questions.
These times exclude speech recognition, TTS and playback; the requested 3–4
second complete voice cycle is **not verified**. The user elected to conduct
the browser test. Further live benchmarking was stopped; a formatting-only
diagnostic was not adopted into production code.

The original two benign AICredits format requests passed in 5.231 seconds (Nano)
and 1.426 seconds (Flash-Lite). Later fictional and explicitly authorized real
post-interview report generation both passed Nano narrative and Gemini feedback
validation; details are recorded by the report workflow delivery evidence. Model
compatibility and report generation are not proof of an entire browser voice
conversation. The tested alternatives did not meet the requested one-second
complete conversation cycle.

## Verified provider contract

The endpoint is `POST https://api.aicredits.in/v1/chat/completions`, with
`Authorization: Bearer <key>` and a JSON request containing `model` and `messages`.
The response carries `choices[0].message.content` and `finish_reason`.
This compatibility is documented by AICredits, not inferred from its name.
See the [official API reference](https://aicredits.in/docs/api-reference).

The [official model catalog](https://aicredits.in/models) lists
`openai/gpt-5-nano` (400K context) and `google/gemini-2.5-flash-lite` (1M context).
The [Flash-Lite model page](https://aicredits.in/models/google/gemini-2.5-flash-lite)
also demonstrates the Chat Completions endpoint. Published context sizes are
provider catalog information, not limits exercised by this integration.

[JSON mode](https://aicredits.in/docs/structured-outputs) is documented for both
providers; strict schema support is partial for Gemini. The adapter requests
JSON mode and the report service must validate the business schema and evidence.
AICredits documents automatic JSON healing, including truncated output. The
adapter still rejects a non-`stop` finish reason, malformed JSON, duplicate JSON
keys, non-finite numbers, and non-object content; it performs no repair itself.
The provider does not document a separate healing indicator.

[Rate limits](https://aicredits.in/docs/rate-limits) default to 60 requests per
minute per key and five concurrent requests per user; actual account settings
can differ. The [error reference](https://aicredits.in/docs/errors) documents a
10MB request limit, credit/budget errors (402), and retryable 429/500/502/504.
The adapter exposes safe error codes and a retryable flag; it does not retry
automatically or switch keys/models. The report workflow owns persisted retries.

## Configuration and boundaries

All settings are server-side. `backend/.env.example` contains blank credential
placeholders and the selected non-secret realtime model values:

| Variable | Purpose / default when blank |
| --- | --- |
| `AICREDITS_API_KEY_GPT5_NANO` | M1 and recruiter narrative slot |
| `AICREDITS_API_KEY_GEMINI_FLASH_LITE` | Meta-Orchestrator and candidate feedback slot |
| `AICREDITS_GPT5_NANO_MODEL` | `openai/gpt-5-nano` |
| `AICREDITS_GEMINI_FLASH_LITE_MODEL` | `google/gemini-2.5-flash-lite` |
| `AICREDITS_M1_MODEL` | Selected `google/gemini-3.1-flash-lite`; blank uses Nano model slot |
| `AICREDITS_ORCHESTRATOR_MODEL` | Selected `google/gemini-3.1-flash-lite`; blank uses Flash-Lite model slot |
| `AICREDITS_M1_REASONING_EFFORT` | `minimal` for GPT-5 Nano M1 only |
| `AICREDITS_BASE_URL` | `https://api.aicredits.in/v1` |
| `AICREDITS_TIMEOUT_SECONDS` | 60 seconds, allowed range 5–180 |
| `AICREDITS_REALTIME_TIMEOUT_SECONDS` | 30 seconds, allowed range 5–60 |

`generate_intelligence(purpose, *, messages, context_id="unknown")` routes `m1`
to the M1 override/Nano default and `orchestrator` to the routing override/Flash-Lite
default, always using their respective credential slots. It preserves
the exact existing multi-message prompts, including M1's bounded schema-repair
conversation. `M1_PROVIDER=aicredits` selects `AICreditsAnalysisProvider`;
`ORCHESTRATOR_PROVIDER=aicredits` selects the Meta-Orchestrator transport. Existing
Groq configuration remains available as an explicit rollback selection, never an
automatic fallback. M1 retains strict AnswerAnalysis validation, scoped evidence
identities, evidence/finding repair-integrity checks, and source agent/round IDs.

`app.integrations.aicredits_client.generate_report_narrative(assessment)` uses
only the Nano key. It requests an overall summary and strengths/improvements
with actual evidence references. It does not generate a score or hiring decision.

`generate_candidate_feedback(assessment, narrative)` uses only the Flash-Lite
key. It sends numeric overall score/rating, performance band, aggregate coverage,
and supported narrative strength/improvement text. It excludes raw CV/answers,
personal-identity fields, recruiter recommendation/notes, and internal evidence
identifiers. It requests two constructive overall-performance sentences; the
service supplies the deterministic score-band sentence and validates the result.

Missing one key does not disable the other step or substitute its key. HTTP
redirects are rejected, upstream errors/content are not logged, and credentials
are omitted from settings representations. Candidate-facing text still requires
the service's content/privacy validation; an LLM prompt is not a security boundary.

The application caps input at 512,000 bytes and received output at 256,000 bytes,
failing explicitly instead of silently dropping interview evidence. It requests
an 8,192-token completion budget for the M1/Nano report slot and 4,096 output tokens for realtime
routing requests (1,024 for short candidate feedback).
GPT-5 Nano omits sampling overrides and uses `max_completion_tokens`. Realtime
M1 additionally uses `reasoning_effort=minimal`; the separate report purpose does
not inherit that setting. Non-reasoning model overrides use `max_tokens` and
receive no GPT-5 reasoning parameter. The [OpenAI GPT-5 family guide](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5)
explicitly includes Nano and supports minimal reasoning; [AICredits documents
reasoning-effort forwarding](https://aicredits.in/docs/reasoning-tokens).
The exact minimal Nano request passed a realistic synthetic semantic probe.
Realtime HTTP connections can be reused by the explicitly initialized application
event loop; temporary workers and injected test transports close their own clients.

The transport adapter imports no interview/Agora/Groq providers and creates no
database rows. Its realtime callers retain their existing orchestration layers.
The existing report service owns completion,
authorization, evidence validation, persistence, idempotency, and retry behavior.
No AWS changes are part of this integration.

## Isolated verification

Command: `cd backend && PYTHONPATH=. venv/bin/pytest -q tests/test_aicredits_client.py tests/test_aicredits_m1_provider.py tests/test_groq_m1_provider.py tests/test_groq_rate_limit_metadata.py`

Result: **117 passed**. Coverage includes the documented request envelope and
model/key separation, private-field projection, configurable endpoint/models,
missing keys, status/error mapping, no retry/fallback, redirect rejection,
transport failure redaction, malformed/incomplete/oversized output, input bounds,
blank optional configuration defaults, unchanged M1 prompts/repair, evidence
identity, and no cross-provider fallback. These isolated tests make no model calls.
The separate benign live probe is recorded in
`tmp/voice-diagnostics/aicredits-format-live-20260906.json`.


## Controlled live model comparison (synthetic text only)

The first realistic Nano M1 request with default reasoning timed out after
30.002 seconds. The documented minimal-reasoning control completed M1 in 6.539
seconds and Flash-Lite routing in 2.750 seconds, one model request each, with
valid scoped evidence and an actual model-generated routing decision. These are
model completion times, not time to first token or end-to-end speech latency.

An initial exact-contract comparison preserved the fictional source answer,
CV/JD, message hashes, and a fixed validated reference analysis for routing:

| Gateway model | Initial M1 | Initial Meta | Result |
| --- | ---: | ---: | --- |
| `openai/gpt-4.1-nano` | 5.073 s | 3.556 s | Both schemas passed |
| `google/gemini-2.5-flash-lite` | 4.402 s | 2.087 s | Both schemas passed |
| `google/gemini-3.1-flash-lite` | 3.153 s | 2.044 s | Both schemas passed |
| `groq/llama-3.1-8b-instant` | 0.270 s | 0.625 s | Both provider requests returned HTTP 400; deterministic routing fallback is not a model success |

Two additional pooled-connection repetitions gave M1/Meta times of 4.258/1.961
and 5.015/1.575 seconds for 2.5 Flash-Lite, and 2.334/1.566 and 2.748/1.873
seconds for 3.1 Flash-Lite. No successful model pair achieved the requested
one-second complete cycle. ASR, context retrieval, persistence, TTS, and audio
playback are outside those times. The sample is too small to claim production
percentiles.

Quality review exposed an existing M1 prompt ambiguity: evidence scores were
returned on a 0–1 scale despite the domain's 0–10 contract. The prompt was
corrected explicitly; prior records are not rescaled. Some outputs also inferred
exactly-once semantics or exponential backoff beyond the answer. Initial routing
comparisons intentionally used a fixed reference analysis without the hydrated
current-answer context, so they are controlled transport/model comparisons,
not complete production-turn acceptance. A subsequent hydrated two-turn probe
uses each actual M1 result and full candidate/job/current-answer/history context.

Ignored evidence artifacts: `aicredits-semantic-live-20260906.json`,
`aicredits-semantic-minimal-live-20260906.json`,
`aicredits-fast-models-initial-20260906.json`, and
`aicredits-fast-models-warm-20260906.json` under `tmp/voice-diagnostics/`.
All contain fictional inputs only. No provider configuration was enabled or
hosted hiring records changed by these comparisons. AWS remains paused.


The corrected-score, fully hydrated 3.1 Flash-Lite probe completed two sequential
synthetic turns at 5.015 and 4.824 seconds for M1 plus Meta. Each stage used one
actual model request, and the second decision selected Jordan via SWITCH_AGENT.
The first M1 response still inserted "exponential" before the answer's plain
"backoff"; its schema passing does not establish faithful evidence extraction.
The second response reflected the supplied crash-test answer. This proves typed
text-flow compatibility and an actual routing decision, not an Agora voice
handoff or live graph persistence. The artifact is
`tmp/voice-diagnostics/aicredits-hydrated-3.1-live-20260906.json`.


The final bounded alternatives were also tested through AICredits with hydrated
fictional context and the corrected score prompt: `qwen/qwen3-30b-a3b-instruct-2507`
completed M1 in 11.592 seconds and Meta in 10.741 seconds, with valid schemas but
an overly broad generated follow-up; `meta-llama/llama-3.1-8b-instruct` timed out
during M1 after 30.006 seconds, and its Meta step was not run. The catalog's
`groq/llama-3.1-8b-instant` route advertises an 8,192-token context, whereas the
alternative Llama route advertises 131,072. The earlier HTTP 400 cause was not
captured and must not be asserted to be a context limit based on metadata alone.
No further model retries were performed. A safe summary is saved in
`tmp/voice-diagnostics/aicredits-model-benchmark-summary-20260906.json`.


## Latest GPT-OSS-20B availability and stopped comparison

The documented authenticated [`GET /v1/models` endpoint](https://aicredits.in/docs/community/openclaw)
returned HTTP 200 and 464 model IDs for each configured AICredits key on
2026-09-06. Neither key's list contained GPT-OSS-20B or its checked provider
aliases. The only OSS-family entries were `openai/gpt-oss-120b` and
`openai/gpt-oss-safeguard-20b`; the safeguard model is a different model and was
not substituted. No guessed 20B request was sent. Evidence is saved in
`tmp/voice-diagnostics/aicredits-authenticated-oss20-catalog-20260906.json`.
Catalog listings can change; this is the observed result, not a permanent claim
about AICredits capabilities.

After an AICredits-only exact-current-answer excerpt guard was added, a final
3.1 Flash-Lite first turn passed grounded signal validation: M1 3.165 seconds and
Meta 2.050 seconds, **5.215 seconds total**. The user then prioritized GPT-OSS-20B,
so the comparison stopped before a second model request. Its local diagnostic
stdin was closed; that EOF is an intentional test stop, not a provider error.
There is no completed two-turn acceptance claim for the new grounding guard.
The first-turn artifact is
`tmp/voice-diagnostics/aicredits-hydrated-3.1-grounded-live-20260906.json`.
