# Intra AI voice validation and delivery report

Validation date: 6 September 2026, Asia/Kolkata. This report covers the current voice debugging, context, handoff, and reliability work in the existing working tree. It does not certify every earlier ATS workflow or replace the master implementation specification.

**Latest follow-up:** [Conversation continuity and replacement-key report](INTRA_AI_CONVERSATION_FIX_REPORT.md) documents the later question-loop findings, clarification/unfinished-speech fixes, project continuity, provider pause behavior, and new validation limits. The session results below remain historical evidence for their specific builds.

**Alex and Jordan both produced audible speech in the user's real browser test.** The confirmed session has candidate ASR, live Custom LLM callbacks, Groq processing, and Agora assistant speech timings. The tunnel was not the remaining failure in that session. Jordan's earlier failure was an inherited Agent Studio model configuration: cloud logs showed requests to `gpt-4.1-mini` failing with HTTP 401 instead of reaching the intended Custom LLM. Using the configured Custom LLM base pipeline for both persona mappings restored Jordan callbacks and speech.

**The latest first-name/CV/JD personalization and duplicate-greeting fixes passed regression tests and a live backend Groq check. Both frontend and backend were rebuilt and restarted. A fresh browser conversation on this final build has not yet been verified.** The durable scheduled-interview-to-final-report flow also remains unverified by these voice fixtures. **AWS deployment: PAUSED.**

## Failure diagnosis and evidence

| Question | Finding and evidence |
| --- | --- |
| A. Exact failure point | The original “joined” UI established RTC presence, not audio publication. In the captured failing Jordan generation, processing stopped at the cloud LLM request: `LLM_REQUEST_ERR`, HTTP 401, wrong model/provider inherited from its Studio pipeline. This is distinct from earlier managed-TTS configuration work and from later Groq quota failures. |
| B. Frontend path | `frontend/src/app/(candidate)/interview/[token]/page.tsx` handles `user-joined`, `user-published`, subscription, track lookup, `play()`, media activity, and `user-unpublished` separately. Joining alone no longer constitutes evidence that audio is playing. |
| C. Backend/cloud path | `backend/app/services/agora_agent_service.py` constructs the join payload; `backend/app/custom_llm/router.py` receives the OpenAI-compatible HTTP/SSE callback; `adapter.py` coordinates M1, context, and orchestration. The failing Jordan cloud generation was `A44CV49DP97KL33FK65LK24FE76RR97D` in `intra-voice-optimized-1788644477`. Its cloud turn records contain nine error terminations, including the provider/model 401. |
| D. Did the agent publish audio? | The confirmed replacement session has assistant speech start/end timestamps and successful cloud turns. The user also confirmed hearing both personas. The earlier failed Jordan generation cannot be called a successful Custom LLM conversation merely because it joined or some API-triggered speech succeeded. |
| E. Did the browser subscribe/play? | Audible user confirmation establishes actual playback in the tested browser. The code now separately logs subscription, track creation, playback invocation, and received media statistics. A `play()` call alone is not treated as proof of audible output. A complete exported browser-console trace for every turn is not included in the artifact set. |
| F. Did Custom LLM receive the request? | Yes in the confirmed browser session: the pre-stop snapshot contains 13 Alex and 11 Jordan HTTP 200 callbacks, tied to the same session/channel. The final capture contains 25 callbacks total: 13 Alex and 12 Jordan. These are real tunnel requests, not just a tunnel health check. |
| G. Did Groq respond? | Yes. Successful M1 stages and provider timing records were captured; a separate live Groq benchmark passed. Earlier HTTP 429 fallback responses are explicitly excluded from successful reasoning and latency claims. |
| H. Did TTS generate audio? | Yes for confirmed cloud turns: assistant speech timings, TTS first-byte metrics, playback duration, and audible user confirmation agree. Cloud turn 9 for Alex records 765 ms TTS first-byte latency and 10,605 ms playback duration. |
| I. Root cause | A per-persona Studio pipeline retained a different LLM configuration despite the intended custom override. The observed provider was OpenAI `gpt-4.1-mini`, not Groq GPT-OSS-20B via the Custom LLM endpoint. The browser's generic waiting state obscured this upstream distinction. |
| J. Minimal fix | Prefer `AGORA_CUSTOM_LLM_PIPELINE_ID` for both existing persona mappings, preserving separate RTC identities, voices, personas, and the existing registry. Retain the explicit Custom LLM URL/auth/streaming contract and managed TTS settings. Add stage-specific diagnostics rather than replacing Agora, M1, or the orchestrator. |

Primary artifacts: [failing cloud generation](../tmp/voice-diagnostics/voice-optimized-1788644477-evidence.json), [confirmed pre-stop capture](../tmp/voice-diagnostics/confirm-pre-stop-evidence.json), [final confirmed capture](../tmp/voice-diagnostics/voice-confirm-1788645960-evidence.json), and [confirmed runtime stages](../tmp/voice-diagnostics/confirm-runtime-clean.log). Raw artifacts are local diagnostics; the report omits credentials and provider error bodies that could contain credential fragments.

## Confirmed session identity and lifecycle

| Component | Identity |
| --- | --- |
| Interview | `voice-confirm-1788645960` |
| RTC and Custom LLM channel | `intra-voice-confirm-1788645960` |
| Synthetic candidate scope | `voice-confirm-1788645960-candidate` |
| Alex RTC UID / cloud generation | `468707` / `A44CL48JL84JP86XR84ND64JF27EM49A` |
| Jordan RTC UID / cloud generation | `654509` / `A44CF23HN37AF73LL32KL64MC47FJ23T` |

Backend start logs and captured cloud records agree on the channel and persona mappings. A repeated Alex start was identified as `already_running`, using the same cloud generation, rather than creating a second Alex. After handoff, the in-progress capture lists one running Jordan agent. The final capture reports `status=COMPLETED`, `voice_lifecycle_status=applied`, no pending voice action, and zero running agents. See [final lifecycle summary](../tmp/voice-diagnostics/confirm-final-summary.json).

Handoff and completion now wait for outgoing cloud audio to drain before stopping the agent and applying the next lifecycle action. The browser polls the authoritative session state and follows `current_agent_id`; it redirects to completion only when the server reports `status=COMPLETED`. Logical completion or a handoff-intent event alone cannot cut off the farewell. Unit tests cover stale generation protection, audio-confirmation failures, and returning between agents. The captured live run proves Alex → Jordan; Alex → Jordan → Alex remains a regression-test result, not a live claim.

## Implemented reliability and context changes

- **Voice diagnostics:** distinct joined/published/subscribed/track/playback/media stages; subscription errors are not mislabeled as autoplay failures. Safe logs carry session/channel/agent/UID correlation, received bytes/packets, decoded energy, and timestamps. RTM transcript logs record identities and lengths instead of repeatedly dumping transcript content. Secrets and authorization headers are excluded from Custom LLM request logs.
- **Transcript identity:** RTM final detection recognizes the observed `turn_status=1` schema. Persistence uses a composite source-generation/publisher, role, speaker UID, and turn ID because user and assistant can share a cloud turn number. If RTM omits cloud generation identity, publisher-based fallback has a weaker uniqueness guarantee across agent restarts.
- **Duplicate and empty turns:** the newest empty user ASR message no longer causes the adapter to scan backward and rescore an older answer. Ongoing empty turns produce no speech, no M1/orchestrator call, and no context/KG mutation. The initial empty startup handshake can still produce one greeting. A native-greeting-in-progress guard protects callbacks arriving before cloud join returns; “Hi Alex” during an active interview acknowledges the greeting without restarting the introduction.
- **Conversation controls:** repeat, clarification, pause/resume, and end requests use the intended control paths rather than becoming competency scores. A question such as “One simple example of what?” is treated as clarification even when preceded by an explanation. Substantive statements and quoted/reported control phrases retain answer processing. End handling sends the farewell before the server completes the voice lifecycle.
- **CV and JD grounding:** scheduling supplied `parsed_resume`, while consumers expected `candidate_profile`. Session initialization now normalizes either shape, including list and nested resume forms, before the first callback. It preserves candidate identity and CV collections. Context/M1 can use a bounded raw CV excerpt when structured experience/projects are sparse. The scheduled interview selects the CV attached to its application when a candidate has multiple resumes. Openings use the saved candidate's first name, role/JD, and a supported CV project or skill; later cross-agent prompts use supported conversation subjects. Unsupported fragments and negative experience statements are not promoted to invented project names.
- **M1 evidence integrity:** model-generated finding references are validated against actual evidence IDs. A bounded single repair request to the same GPT-OSS-20B model is allowed for invalid structured output. The repair cannot silently drop references, alter evidence identities/signals, or create an extra model dependency. A second invalid repair raises; quota/network errors are not retried through this repair path.
- **Latency path:** context work overlaps M1, orchestration supports the application's async loop, Groq connections can be reused within the application lifespan, and graph writes leave the response's critical path with shutdown draining. Safe provider logs include latency and usage counts. None of these changes replace Agora ASR/TTS, GPT-OSS-20B, or the N-agent registry.

The live Supabase read confirmed the mismatch mattered for the actual scheduled record: one parsed-resume object, seven extracted skills, 3,463 characters of raw resume text, and zero structured experience, education, or project entries. The related job had an 800-character description, five required skills, and four configured rounds. Normalization and raw-text fallback expose existing source material; they do not establish that missing structured fields have been reparsed successfully. See [scoped context shape audit](../tmp/voice-diagnostics/scheduled-context-shape-summary.json).

## Measured latency

These are individual observations from different runs, not a controlled performance comparison. Cloud end-to-end latency is Agora's metric; adapter TTFT ends at the first yielded HTTP SSE content, before TTS/browser playback. No synchronized browser first-audible-sample timestamp was collected.

| Phase | Earlier baseline answer, cloud turn 5 | Confirmed Redis answer, Alex cloud turn 9 |
| --- | ---: | ---: |
| Agora end-to-end latency | 7,815 ms | 6,636 ms |
| Agora algorithm processing | 200 ms | 200 ms |
| Agora ASR tail latency | 908 ms | 1,080 ms |
| Agora LLM TTFT | 4,856 ms | 4,348 ms |
| Agora LLM first-token-to-first-sentence | 14 ms | 17 ms |
| Agora TTS first byte | 1,609 ms | 765 ms |
| Agora transport | 228 ms | 226 ms |
| Backend M1 | 940.7 ms | 4,090.32 ms |
| Backend context retrieval/build | Not separately timed; 1,013.728 ms between M1 completion and context completion | 429.827 ms, overlapping M1 |
| Backend orchestrator | See baseline stage artifact; not isolated here | 21.607 ms |
| Backend adapter TTFT | 4,610 ms | 4,120.258 ms |
| Orchestrator completion to first response chunk | 2,649.228 ms | 1.210 ms |

The confirmed answer is correlated by cloud turn ID `9` and backend request ID `3c6ba40d-8693-455e-9419-dbd0e7eae6ea`. Its cloud record is `start.type=voice_input`, `end.type=ok`. The context duration is not added to M1 because their intervals overlap. The 21.607 ms orchestrator duration does not imply a full Groq routing call took 21 ms; routing can legitimately use its validated policy/fallback path.

The earlier optimized run had genuine Groq 429 failures on substantive answers. Its roughly 423–434 ms adapter fallback responses cannot be presented as improved successful interview reasoning. Short control requests and greeting timings also cannot substitute for a substantive answer benchmark. Baseline association used available timestamps and has less precise identity linkage than the confirmed turn. Sources: [comparison methodology and baseline](../tmp/voice-diagnostics/latency-comparison.json), [confirmed cloud metrics](../tmp/voice-diagnostics/confirm-pre-stop-evidence.json), and [backend timing stages](../tmp/voice-diagnostics/confirm-runtime-clean.log).

## Knowledge Graph and persistent memory evidence

Read-only Neo4j queries were restricted to the named validation candidate IDs. The artifacts include the exact parameterized Cypher and repository/service relationships used; no unrelated candidate records were queried for this check.

| Candidate scope | Rounds | Questions | Answers | Evidence | Agent provenance |
| --- | ---: | ---: | ---: | ---: | --- |
| `validation-brain-1788644155` | 1 | 2 | 2 | 3 | Alex; earlier synthetic standalone provider test |
| `voice-optimized-1788644477-candidate` | 1 | 5 | 5 | 0 | Alex; do not infer scored evidence from HTTP 200 fallbacks |
| `voice-confirm-1788645960-candidate` | 1 | 12 | 18 | 11 | Questions: Alex 7/Jordan 5. Evidence: Alex 10/Jordan 1. |

The confirmed candidate's evidence IDs are unique, every inspected evidence reference resolves to a scoped answer, and every inspected answer reference resolves to a scoped question. This proves persisted graph data and persona provenance for the inspected run. It does not prove all expected CV entities, all competencies, or every longitudinal memory behavior are complete.

**The confirmed graph counts predate the empty-ASR replay fix.** Some answers were produced by the previous replay bug; 18 persisted answer nodes must not be described as 18 independent substantive candidate answers. Existing artifacts were retained as evidence rather than silently rewritten. The earlier standalone fixture also predates evidence-ID namespacing and retains legacy local IDs. Sources: [first scoped KG audit](../tmp/voice-diagnostics/kg-validation-summary.json) and [both-agent KG audit](../tmp/voice-diagnostics/kg-confirm-summary.json).

## Tests, builds, and live integration status

| Check actually executed | Result / limit |
| --- | --- |
| From `backend`: `GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests --ignore=tests/test_real_groq_integration.py -q` | **584 passed, 13 skipped, 3 dependency warnings in 107.48 s**, exit 0. [Final regression log](../tmp/voice-diagnostics/backend-regression-final.log). Explicitly excludes live Groq tests; not an all-live suite. Skips are 12 legacy Ollama tests and one opt-in Neo4j test. |
| Personalization/context/greeting/lifecycle focused run | **82 passed, 2 warnings in 0.60 s**. [Focused log](../tmp/voice-diagnostics/personalization-focused-tests.log). Includes the new personalization test module; its individual run passed 14 tests. |
| `venv/bin/pytest -q tests/test_groq_evidence_identity.py tests/test_groq_m1_provider.py` | **29 passed** at the schema-repair checkpoint; covered valid repair, repeated-invalid rejection, identity preservation, and quota/error behavior. Included in the later deterministic suite. |
| `venv/bin/pytest -q tests/test_empty_candidate_turn.py tests/test_custom_llm_adapter.py tests/test_fast_path_classifier.py tests/test_voice_intent_latency.py` | **87 passed** at the empty-turn checkpoint. Later tests strengthened the ongoing-empty contract to assert unchanged context and no M1/orchestrator/KG write; those pass in the final deterministic suite. |
| Live Groq five-turn benchmark | **1 passed in 69.96 s**. [Live benchmark log](../tmp/voice-diagnostics/live-groq-final-benchmark.log). The previous full run's unknown-evidence-reference failure was investigated, repaired with bounded validation, and rerun; it was not removed or marked skipped to obtain a pass. |
| Frontend `npx tsc --noEmit` and `node --test tests/agora-audio-lifecycle.test.mjs` | TypeScript passed; **7 audio lifecycle tests passed** (UID filtering, cancellation/ownership, duplicate playback, retry, safe diagnostics). [Audio test log](../tmp/voice-diagnostics/frontend-audio-tests.log). |
| Frontend production Docker build/restart | **Passed**, latest local frontend image rebuilt and restarted. [Build log](../tmp/voice-diagnostics/personalization-frontend-build.log). Fresh room page responds HTTP 200. |
| Final context/personalization tests | **18 passed, 2 warnings in 0.47 s**; covers application-specific CV selection as well as name/initial callback behavior. [Log](../tmp/voice-diagnostics/final-context-tests.log). |
| Backend Docker build and restart | Latest personalization backend image built successfully; the backend was restarted with dependencies left running. [Build log](../tmp/voice-diagnostics/personalization-backend-build.log). Subsequent health and Custom LLM readiness checks returned HTTP 200 / healthy and ready. This is readiness, not fresh personalized voice E2E. |

Historical logs contain earlier failures and smaller passing counts. They are retained as diagnostics, not represented as the final source status. The final deterministic suite above supersedes those checkpoints for backend regression coverage. No test was deleted to hide an observed integration failure.

| Live integration | Verified scope |
| --- | --- |
| Groq M1 GPT-OSS-20B | Live responses, normal browser turn processing, and separate five-turn benchmark verified. Quota failures occurred in an earlier run and remain a real capacity constraint. |
| Groq Meta-Orchestrator GPT-OSS-20B | Latest isolated direct-backend run **accepted the real model question unchanged**, with `nemotron_used=true`; both real M1 and Meta calls returned HTTP 200. Earlier standalone `validation-brain-1788644155` proposed an invalid target and used fallback; that historical record is superseded for accepted model routing by the latest check. [Latest evidence](../tmp/voice-diagnostics/live-brain-latest-single-turn.json). This is backend provider integration, not fresh browser voice. |
| Supabase | Scoped live reads resolved the scheduled interview, application, candidate resume, and job. This audit did not recreate the full recruiter-to-report journey. |
| Neo4j Aura | Live scoped reads verified persisted questions, answers, evidence, and Alex/Jordan provenance with reference checks. |
| Agora | Real browser channel and microphone/ASR activity, cloud agent generations, Custom LLM callbacks, TTS/speech metrics, and user-confirmed audible Alex/Jordan. |
| Browser voice E2E | Prior confirmed browser run handled multiple real candidate turns and audible replies from both personas. Latest personalization/startup/blank-turn fixes still require fresh browser acceptance. A fully exported joined→published→subscribed→decoded→heard trace for each acceptance turn is not yet assembled. |
| Agent handoff | Live Alex → Jordan verified. Bidirectional return and stale/drain lifecycle cases covered by tests; full Alex → Jordan → Alex live cycle remains unverified. |
| Completion/report | Synthetic voice lifecycle completion and agent cleanup verified. Durable Supabase completion and evidence-backed final report generation were not exercised by these synthetic fixtures. |

The report limitation is intentional in `backend/app/sessions/completion.py`: non-UUID synthetic interview IDs return `persistence_status=not_applicable` and `report_status=not_applicable` before Supabase/report work. The final voice snapshot explicitly has `report_status=not_applicable`. Successful fixture completion must not be presented as successful durable report generation.

## Changed areas relevant to this delivery

This list identifies the voice work described above; the working tree also contains earlier ATS changes that were already present and are not newly certified here.

| Group | Paths and purpose |
| --- | --- |
| Backend voice/stream | `backend/app/custom_llm/{adapter,classifier,models,router,timing}.py`: controls, empty/startup guards, safe stream tracing, timings. `backend/app/services/agora_agent_service.py`: managed TTS and Custom LLM join contract. |
| Backend context/intelligence | `backend/app/agent_context/{builder,personalization}.py`, `backend/app/interview_intelligence/{provider,prompts}.py`, `backend/app/orchestrator/{graph,policies,prompts,service}.py`: CV/JD/name normalization and grounding, schema repair, async routing/latency behavior. |
| Backend session/persistence | `backend/app/sessions/{service,models,completion}.py`, `backend/app/schemas/sessions.py`, `backend/app/routes/sessions.py`, `backend/app/interview_context/store.py`, `backend/app/knowledge_graph/{service,neo4j_repository}.py`: lifecycle/status, completion integration, context and graph behavior. |
| Backend runtime/configuration | `backend/app/integrations/groq_client.py`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/agents/{alex,jordan}.py`, `backend/.env.example`: loop-safe HTTP pooling/draining and shared custom-pipeline option. Local credentials remain outside this report. |
| Frontend | `frontend/src/app/(candidate)/interview/[token]/page.tsx` and `frontend/src/lib/agora-audio-lifecycle.ts`: stage diagnostics, authoritative session sync, transcript identity, configured-agent UID filtering, canceled startup cleanup, idempotent playback, and microphone settings/transmission counters. AEC/ANS/AGC and encoder settings remain unchanged. The reported echo’s exact acoustic cause was not established. |
| Tests | Focused modules include `test_custom_llm_observability.py`, `test_groq_evidence_identity.py`, `test_empty_candidate_turn.py`, `test_interview_personalization.py`, `test_question_subject_grounding.py`, `test_session_greeting_revalidation.py`, `test_voice_handoff.py`, `test_voice_clarification.py`, and `test_voice_intent_latency.py`, plus related existing integration/registry regression coverage. |
| Database | No schema migration or manual candidate-data rewrite was required for the read-only validation audits described here. Neo4j graph contents came from the application runtime. |
| Documentation/evidence | This report and the scoped diagnostics under `tmp/voice-diagnostics/`. |
| Deployment | Local Docker frontend and backend rebuilt, restarted and health-checked. AWS infrastructure/deployment was not started. |

## Latest personalized backend check

The final direct-backend test used an explicitly synthetic Sam Lee profile and Payment Ledger CV/JD. It made exactly two real Groq requests without retries: M1 **2,636.3 ms**, Meta-Orchestrator **1,374.4 ms**; adapter first response chunk **4,032.225 ms**. The accepted question began “Sam, you mentioned that the consumer commits its Kafka offset only after the database transaction commits…” and probed the precise ordering and partial-failure mechanism introduced in the answer. The model action was `ASK_QUESTION`, Alex, `system_design`, medium difficulty. Blank input and “Hi Alex” took 0.2/0.3 ms with no model calls and unchanged context.

This verifies the latest prompt, schema, grounding, personalization and provider path. It used an in-memory graph and no browser or Agora agent, so its 4.03-second adapter result excludes ASR, network delivery to Agora, TTS and browser playback. [Evidence](../tmp/voice-diagnostics/live-brain-latest-single-turn.json), [safe provider timing log](../tmp/voice-diagnostics/live-brain-latest-single-turn.log).

A fresh review room is prepared at `http://localhost:3000/interview/voice-personalized-1788647921/prep`, with Alex/Jordan, the saved application’s CV/JD, and an isolated candidate ID. No agent was started during preparation. The saved candidate name is still the demo account’s name; greeting personalization uses that saved value rather than guessing a name. [Room record](../tmp/voice-diagnostics/personalized-room.json), [final runtime HTTP checks](../tmp/voice-diagnostics/final-runtime-readiness.json).

## Remaining acceptance work

1. Run a fresh browser session on the final frontend/backend build: verify one automatic first-name/CV/JD greeting, two substantive answers and audible responses, an explicit repeat/clarification, silent/noise input without replay, and a clean end after the farewell.
2. Capture safe console publication/subscription/playback/media markers alongside cloud turn and callback IDs for the same session; distinguish observed audio energy from a mere `play()` invocation.
3. Validate Alex → Jordan → Alex with a supported earlier answer referenced by the returning persona. Re-query only that fresh candidate's graph after background writes drain, avoiding reliance on pre-fix replay counts.
4. Complete a real scheduled UUID interview through Supabase status updates and the existing evidence-backed report endpoint/UI. Verify report evidence references and agent contributions; synthetic fixture completion cannot cover this step.
5. Record the fresh personalization browser outcome when available. No application or live integration result should be inferred from backend unit tests or health checks alone.

**AWS deployment: PAUSED.** No AWS-specific action is authorized until the application's remaining validation is complete and the user subsequently supplies and authorizes AWS details.
