# Intra AI current production-state audit

**Audit date:** 6 September 2026
**Repository:** `VIsHnu1762/intra-ai`
**Branch:** `v2`
**Audited source:** the pre-cleanup `v2` working tree, preserved in the external recovery bundle
**Working tree at audit time:** `LICENSE` was deleted and follow-up scheduling edits were present in `scheduling_service.py`, `voice/bulk.py`, `voice/context.py`, and `voice/tools.py`
**AWS status:** **PAUSED. No AWS commands, resources, configuration, or deployment changes were made.**

## Executive finding

The application is a working, substantial single-node prototype. Its current live interview intelligence does **not** use Groq GPT-OSS-20B. The effective local runtime selects AICredits for both live intelligence layers and overrides both to `google/gemini-3.1-flash-lite`. Post-interview narrative and candidate feedback use separate AICredits model slots: `openai/gpt-5-nano` for the recruiter narrative and `google/gemini-2.5-flash-lite` for candidate feedback. The overall score, recommendation, and star rating are deterministic application calculations, not separate AI judgments.

External Supabase and Neo4j Aura connectivity passed during this audit. The local Docker Compose stack is running, the backend container reports healthy, the frontend returns HTTP 200, a network-enabled production frontend build passes, 1,725 backend tests pass, and all 62 frontend behavior tests pass. The repository is not ready for public production deployment because several unauthenticated live-control endpoints exist, the Custom LLM callback does not enforce its configured bearer secret, the Docker frontend cannot receive production `NEXT_PUBLIC_*` values at build time, Compose hardcodes a temporary ngrok callback and development secrets, live interview state is process-local, and the repository's complete test/lint gates are red.

One EC2 instance with Docker Compose is sufficient for the intended first deployment after the blockers in this report are fixed. Supabase, Neo4j Aura, Agora, AICredits, and Composio can remain external. Redis must run on the instance or be replaced with an external Redis service. A single backend process is currently required because official interview session, context, and transcript state are process-local.

## 1. Current architecture

```text
Recruiter / Candidate browser
        |
        +-- Next.js 16 frontend :3000
        |       +-- Agora RTC/RTM browser SDK
        |       +-- REST calls to FastAPI
        |
        +-- FastAPI / Uvicorn backend :8000
                +-- custom JWT auth + workspace authorization
                +-- Supabase SDK using service-role key
                |       +-- ATS records, interview/report records
                |       +-- private resume objects in Supabase Storage
                +-- Redis
                |       +-- Morgan/Taylor sessions, locks, confirmations
                +-- process-local official interview state
                |       +-- meeting sessions
                |       +-- InterviewAIContext
                |       +-- normalized transcript events
                +-- Neo4j AuraDB
                |       +-- candidate memory and interview evidence
                +-- Agora Conversational AI
                |       +-- official Alex/Jordan project and pipelines
                |       +-- separate Morgan/Taylor project and pipelines
                +-- AICredits OpenAI-compatible API
                |       +-- live M1 and Meta-Orchestrator
                |       +-- post-interview narrative and feedback
                +-- Composio MCP for Morgan messaging/calendar/Slack tools
```

The Compose file also starts local PostgreSQL, PostgREST, and an nginx gateway on port 8081. That path is development infrastructure. The backend itself uses the configured remote Supabase URL and service-role client for application data; it does not use `DATABASE_URL` for repository operations.

## 2. Current AI model matrix

| Component | Effective provider | Effective model | Credential/model variables | Runtime path | Live critical path |
|---|---|---|---|---|---|
| M1 Interview Intelligence | AICredits | `google/gemini-3.1-flash-lite` | `AICREDITS_API_KEY_GPT5_NANO`; `AICREDITS_M1_MODEL` falling back to `AICREDITS_GPT5_NANO_MODEL` | `CustomLLMAdapter` -> `AICreditsAnalysisProvider` | Yes, for substantive candidate answers |
| Meta-Orchestrator | AICredits | `google/gemini-3.1-flash-lite` | `AICREDITS_API_KEY_GEMINI_FLASH_LITE`; `AICREDITS_ORCHESTRATOR_MODEL` falling back to `AICREDITS_GEMINI_FLASH_LITE_MODEL` | LangGraph `query_nemotron` historical node -> `generate_intelligence("orchestrator")` | Usually yes; deterministic guardrails can skip it |
| Recruiter report narrative | AICredits | `openai/gpt-5-nano` | `AICREDITS_API_KEY_GPT5_NANO`; `AICREDITS_GPT5_NANO_MODEL` | Background post-interview report worker | No |
| Candidate feedback text | AICredits | `google/gemini-2.5-flash-lite` | `AICREDITS_API_KEY_GEMINI_FLASH_LITE`; `AICREDITS_GEMINI_FLASH_LITE_MODEL` | Background post-interview report worker | No |
| Overall score | Deterministic Python | No model | None | Aggregates saved per-answer evidence | No |
| Recommendation | Deterministic Python thresholds | No model | None | `>=80 strong_hire`, `>=65 hire`, `>=50 maybe`, else `no_hire` | No |
| Candidate star rating | Deterministic Python | No model | None | `round(1 + overall_score / 25, 1)` with half-up rounding | No |
| Taylor practice coach | Agora Studio native LLM | Configured in retained Taylor Studio pipeline; exact model not stored in repository | `AGORA_TAYLOR_AGENT_ID` identifies the pipeline | Separate training/HR Agora project | Practice path only |
| Morgan HR assistant | Agora managed OpenAI | `gpt-4.1-mini` | `AGORA_MORGAN_LLM_MODE=managed`; `AGORA_MORGAN_MANAGED_MODEL` | Separate training/HR Agora project with backend MCP tools | HR assistant path only |

### M1 details

- Effective provider selection is `M1_PROVIDER=aicredits`.
- AICredits base URL is `https://api.aicredits.in/v1`; requests use `Authorization: Bearer <slot key>` and `POST /chat/completions`.
- Effective model override is `AICREDITS_M1_MODEL=google/gemini-3.1-flash-lite`.
- Realtime timeout is `AICREDITS_REALTIME_TIMEOUT_SECONDS=30` seconds.
- Provider requests are non-streaming (`stream: false`) and demand a JSON object. The adapter streams the final text to Agora as OpenAI-style SSE after analysis/routing.
- One normal substantive turn makes one M1 request. Bounded structural repair can add another provider request when the first JSON does not satisfy the M1 contract.
- M1 is on the live critical path after candidate ASR and before context mutation and orchestration. Openings, repeat/simplify, audio checks, pauses, and some control turns use deterministic fast paths instead.
- Exact-answer evidence grounding is enforced for the AICredits M1 implementation.

### Meta-Orchestrator details

- Effective provider selection is `ORCHESTRATOR_PROVIDER=aicredits`.
- Effective model override is `AICREDITS_ORCHESTRATOR_MODEL=google/gemini-3.1-flash-lite`.
- It uses the Flash-Lite credential slot even when the model override names another model.
- Base URL and realtime timeout are the same AICredits values as above.
- The provider call is non-streaming structured JSON. Deterministic policy executes before and after it and can skip, reject, repair, or replace the model decision.
- It normally makes one model call after M1. Forced completion/handoff and other deterministic branches can make zero calls.
- Historical symbol names (`query_nemotron`, `build_nemotron_routing_messages`, `nemotron_used`) and GPT-OSS/Groq comments remain, but these names do not describe the effective runtime provider.

### AICredits implementation status

- Integration is implemented in `backend/app/integrations/aicredits_client.py` and its loop-owned transport.
- Separate keys are used: `AICREDITS_API_KEY_GPT5_NANO` for M1/report and `AICREDITS_API_KEY_GEMINI_FLASH_LITE` for orchestrator/candidate feedback.
- The client validates HTTPS base URLs, request/response size, status codes, final JSON shape, and avoids logging request/response contents.
- Current repository defaults retain `openai/gpt-5-nano` and `google/gemini-2.5-flash-lite` for post-interview output. Only realtime M1/orchestrator have 3.1 model overrides.
- Recorded live evidence shows a synthetic narrative/feedback pair succeeded and one actual completed report was persisted with one request to each post-interview slot. The actual report completed in about 39.6 seconds after recovering two scored answers from Neo4j.
- Recorded live realtime evidence shows AICredits 3.1 calls and valid routing output. A two-stage synthetic probe measured approximately 5 seconds for M1 plus Meta; another grounded first-turn probe measured 5.215 seconds. These are text-path measurements, not fresh browser audio measurements from this audit.
- This audit made no fresh AICredits generation request. The local containers were restarted earlier and prior diagnostics are repository artifacts.

### Groq status

- Groq support remains implemented for M1 and Meta-Orchestrator and is covered by provider-specific tests.
- Legacy/default model references are `openai/gpt-oss-20b` through `https://api.groq.com/openai/v1`.
- Credentials are isolatable with `GROQ_M1_API_KEY`/`GROQ_API_KEY` and `GROQ_ORCHESTRATOR_API_KEY`.
- Groq is **not selected** by the effective local runtime.
- There is no cross-provider fallback from AICredits to Groq. AICredits failures use deterministic interview fallbacks or persisted report failure state.

### Ollama status

- Ollama is **present but unused by the effective runtime**.
- `OllamaAnalysisProvider`, `call_ollama`, `OLLAMA_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, an old real-provider test, and Compose defaults remain.
- The code can still select Ollama for M1 if `M1_PROVIDER=ollama`; the typed `ORCHESTRATOR_PROVIDER` does not allow Ollama.
- No automatic Ollama fallback exists.
- Default Ollama model text remains `gpt-oss:20b`; this is legacy selectable configuration, not current execution.

## 3. Current live interview flow

```text
Candidate microphone
  -> Agora RTC channel
  -> Agora-managed Deepgram Nova-3 ASR
  -> HTTPS OpenAI-compatible Custom LLM callback
  -> deterministic intent/control classifier
  -> M1 through AICredits (substantive answers)
  -> InterviewAIContext mutation
  -> Agent Context builder (CV, JD, current answer, history, KG memory)
  -> LangGraph Meta-Orchestrator through AICredits or deterministic policy
  -> validated NextAction
  -> OpenAI-style SSE text response to Agora
  -> Agora-managed OpenAI TTS
  -> Agora publishes remote audio
  -> browser subscribes and calls remoteAudioTrack.play()
```

The Agent Context builder starts concurrently with M1 because it is read-only; orchestration waits for M1 and the context result. M1 and Meta therefore remain sequential for a normal answer. The adapter persists KG evidence in a background task after the turn response path. It drains tracked persistence tasks at graceful backend shutdown.

Alex and Jordan are registered through an N-agent registry. Scheduling snapshots gather every configured agent across enabled rounds, rather than hardcoding an Alex-to-Jordan pair. Only the active physical agent is started. A handoff stops the old Agora agent, confirms the stop, starts the target in the same channel, and commits the logical switch only after ownership checks. Their official project is separate from the auxiliary Morgan/Taylor project.

The official mappings use Agora-managed Deepgram STT and Agora-managed OpenAI TTS. The backend supplies persona prompts, contextual greetings, the Custom LLM URL, and scoped Agora RTC/RTM tokens. The candidate browser tracks joined, published, subscribed, playing, subscription failure, playback failure, remote levels, and autoplay blocking as distinct states.

Prior user-confirmed evidence established audible Alex/Jordan speech and handoff on an earlier build. Later context/question fixes have text-path and source-load evidence, but a new browser voice acceptance was not performed during this audit. Do not treat container health as voice E2E proof.

## 4. Current report flow

```text
Interview completes
  -> scheduled_interviews/application marked completed
  -> report source snapshot claimed atomically in Supabase
  -> use saved evaluation, or rebuild deterministic assessment from
     exact interview context + Supabase answers/evaluations + exact Neo4j recovery
  -> require at least two distinct scored answer IDs
  -> compute score, recommendation, coverage and star rating deterministically
  -> AICredits GPT-5 Nano writes evidence-cited recruiter narrative
  -> AICredits Gemini 2.5 Flash-Lite writes candidate-safe feedback
  -> validate IDs, citations, score consistency and output shape
  -> atomically publish one report row and mark generation ready
  -> recruiter report UI + candidate rating/feedback UI
```

- Report generation is implemented and has live persisted evidence.
- Normal completion calls `request_report`; recruiters can explicitly generate/retry from completed interviews.
- Generation is asynchronous in an `asyncio.create_task` thread worker. Claim, progress, source, draft, final report, and failure status are persisted in Supabase with attempt ownership fences.
- A process restart can kill the worker. After five minutes the status endpoint describes it as interrupted and retryable, but there is no durable queue or automatic recovery worker.
- Candidate output is separated from recruiter-only analysis and recommendations. Candidate feedback appears on `/interview/{token}/done`, `/interview/{token}/report`, and the candidate portal.
- Recruiter reports appear under `/admin/reports`, on report detail pages, and from completed interview rows.
- PDF download plumbing exists only for a previously populated `pdf_url`. Current report generation does not create a PDF or upload one. A missing PDF link is therefore expected.

## 5. Current database architecture

### Supabase

- The backend uses the synchronous Supabase Python client with `SUPABASE_SERVICE_ROLE_KEY`.
- Browser code does not directly query Supabase; application authorization is enforced in backend actor/workspace checks.
- Authentication is a custom `users` table plus bcrypt passwords and backend-signed JWTs. It is not Supabase Auth.
- ATS jobs, candidates, applications, parsed resumes, eligibility, slots, scheduled interviews, answers/evaluations, templates, and reports are persisted externally in Supabase/Postgres.
- Private resume objects use Supabase Storage when AWS S3 is not configured.
- Read-only audit checks passed for `scheduled_interviews`, `reports`, and `interview_templates`.
- The post-interview migration artifact records that report columns/RPCs and RLS were applied, with report RPC execution restricted to `service_role`.
- `DATABASE_URL` is mandatory in Pydantic settings but no application repository opens a direct SQL connection. Compose overrides it for the local development database, which is not the active Supabase persistence route.

### Neo4j AuraDB

- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` configure the sync Neo4j driver.
- The configured URI is Aura (`neo4j+s://...`); no Neo4j container is defined and none is required on EC2.
- Connectivity passed during this audit.
- KG persistence stores interview/round/answer/evidence relationships with provenance. Writes are offloaded to a worker thread after live response generation.
- Candidate memory retrieves evidence, competencies, projects, technologies, skills, and round history with deterministic filters and bounded result counts.
- Missing Neo4j configuration disables memory/persistence initialization instead of stopping the API. Runtime Neo4j failures are logged and should not fail the spoken turn.

## 6. Current Agora architecture

### Alex and Jordan

- Official browser/agent project credentials: `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`.
- REST agent lifecycle authentication prefers `AGORA_CUSTOMER_ID` + `AGORA_CUSTOMER_SECRET`; otherwise it uses an Agora token. Separate REST key variables are configured but not used by the inspected official lifecycle service.
- Alex/Jordan project and pipeline identifiers are configurable separately. `AGORA_CUSTOM_LLM_PIPELINE_ID`, when set, overrides both persona pipeline IDs.
- The backend builds Token007 RTC/RTM tokens and starts agents through Agora Conversational AI v2 `/join`.
- The callback URL receives only `session_id` and `agent_id` query identifiers; the callback secret is passed as an Authorization bearer value.
- Agora handles ASR, VAD, filler speech, TTS, RTC publication, and RTM events. The backend handles intelligence and agent lifecycle.

### Morgan and Taylor

- Morgan and Taylor use `AGORA_TRAINING_HR_APP_ID` and its separate certificate/token. They do not fall back to the official Alex/Jordan project.
- Taylor retains its saved Studio LLM, receives bounded CV/JD/practice context once at startup, has no MCP tools, and generates practice feedback through the retained native agent flow.
- Morgan is currently overridden to Agora-managed OpenAI `gpt-4.1-mini`. Its backend MCP catalog provides recruiter-scoped reads, reviewed database writes, templates, scheduling, Gmail/calendar/Slack actions, and result polling.
- Morgan's external Composio connection is backend-only and restricted to `MORGAN_COMPOSIO_OWNER_USER_ID`.
- Auxiliary session, locking, and confirmation state is in Redis and is safer across backend worker/restart boundaries than the official interview in-memory state.
- Local source-of-truth agent IDs match the retained pipelines described in `Morgan and Taylor.md`; actual secrets and tokens are intentionally omitted here.
- Recorded tests prove native text-input Morgan candidate lookup, confirmation-gated bulk shortlist, and template scheduling. They do not prove a new browser microphone/audibility run after the latest changes.

## 7. Current application and Docker architecture

| Service | Image/start command | Port | Persistence | Current role |
|---|---|---:|---|---|
| `frontend` | multi-stage Node 20 image; `node server.js` | 3000 | none | Next.js standalone UI |
| `backend` | Python 3.11; `uvicorn app.main:app --host 0.0.0.0 --port 8000` | 8000 | external Supabase/Neo4j plus process memory | API, Custom LLM, agent control |
| `redis` | `redis:7-alpine` | 6379 | `redis_data` volume | auxiliary assistant state/locks |
| `postgres` | `postgres:16-alpine` | 5432 | `postgres_data` volume | development database only |
| `postgrest` | PostgREST 12.2 | internal 3000 | local Postgres | development compatibility API |
| `gateway` | nginx Alpine | 8081 | bind-mounted config | proxies only to local PostgREST |

Compose syntax validation passes and every local service was running at audit time. Backend/Postgres/Redis were healthy; frontend returned HTTP 200. Restart policies are `unless-stopped`. Only Postgres and Redis have volumes. Backend and frontend have no production ingress proxy or TLS service.

The Docker setup is not production-ready:

- backend Compose forces `APP_ENV=development`, `DEBUG=true`, a development JWT secret, and localhost public URLs;
- it hardcodes a temporary ngrok Custom LLM callback;
- frontend `NEXT_PUBLIC_*` variables are supplied only at container runtime, but Next.js embeds them during `npm run build`; the Dockerfile defines no build args, and `.env*` is excluded from its build context;
- `NEXT_PUBLIC_AGORA_APP_ID` is absent from the Compose frontend service;
- gateway routes only PostgREST and provides no frontend/backend routing, SSE tuning for the Custom LLM path, certificates, HTTP-to-HTTPS redirect, or public hostname;
- PostgreSQL, Redis, backend, frontend, and gateway ports are bound to all host interfaces in local Compose;
- local PostgreSQL/PostgREST are redundant for the intended external Supabase deployment;
- the local PostgREST development roles receive broad grants and must never be exposed publicly;
- health checks verify process liveness only, not external readiness.

## 8. Environment variable inventory

No values or secrets are included below.

### Frontend browser/build variables

| Variable | Requirement | Exposure | Used by |
|---|---|---|---|
| `NEXT_PUBLIC_API_URL` | Required in production build | Public | REST base URL; otherwise localhost fallback |
| `NEXT_PUBLIC_AGORA_APP_ID` | Required for voice build | Public | Browser Agora project identity |
| `NEXT_PUBLIC_APP_ENV` | Required for correct production behavior/diagnostics | Public | environment mode |
| `NEXT_PUBLIC_WS_URL` | Optional/unused by current inspected runtime | Public | reserved WebSocket URL |

### Backend core, authentication, and persistence

| Variable | Requirement | Exposure | Used by |
|---|---|---|---|
| `APP_ENV` | Production-required | Server config | logging/docs behavior |
| `DEBUG` | Production-required (`false`) | Server config | logging and API docs |
| `API_BASE_URL` | Production-required | Server config | callback fallbacks and self URLs |
| `FRONTEND_URL` | Production-required | Server config | CORS and public links |
| `JWT_SECRET` | Required | Secret | custom access tokens and assistant-scoped tokens |
| `JWT_ALGORITHM` | Optional default `HS256` | Server config | JWT signing/verification |
| `JWT_EXPIRY_MINUTES` | Optional default 60 | Server config | browser access token TTL |
| `SUPABASE_URL` | Required | Server endpoint | Supabase client |
| `SUPABASE_ANON_KEY` | Required by Settings; not used by inspected backend repositories | Treat as public project key | configuration compatibility |
| `SUPABASE_SERVICE_ROLE_KEY` | Required | Secret | all backend Supabase reads/writes |
| `SUPABASE_STORAGE_BUCKET` | Optional default `resumes` | Server config | private resume storage |
| `DATABASE_URL` | Required by Settings, operationally unused by app repositories | Secret if real | local/development compatibility |
| `REDIS_URL` | Required for Morgan/Taylor; default only valid locally | Secret endpoint | auxiliary sessions, locks, confirmations |
| `NEO4J_URI` | Required for KG/memory | Server endpoint | Aura driver |
| `NEO4J_USERNAME` | Required for KG/memory | Secret | Aura authentication |
| `NEO4J_PASSWORD` | Required for KG/memory | Secret | Aura authentication |
| `NEO4J_DATABASE` | Optional default `neo4j` | Server config | Aura database selection |

### Current AI provider variables

| Variable | Requirement | Exposure | Used by |
|---|---|---|---|
| `M1_PROVIDER` | Required operational selection | Server config | M1 factory; currently `aicredits` |
| `ORCHESTRATOR_PROVIDER` | Required operational selection | Server config | Meta routing; currently `aicredits` |
| `AICREDITS_API_KEY_GPT5_NANO` | Required for current M1 and reports | Secret | M1/report slot |
| `AICREDITS_API_KEY_GEMINI_FLASH_LITE` | Required for current Meta and candidate feedback | Secret | orchestrator/feedback slot |
| `AICREDITS_GPT5_NANO_MODEL` | Optional default | Server config | report and M1 fallback model |
| `AICREDITS_GEMINI_FLASH_LITE_MODEL` | Optional default | Server config | feedback and Meta fallback model |
| `AICREDITS_M1_MODEL` | Optional override, currently set | Server config | current live M1 model |
| `AICREDITS_ORCHESTRATOR_MODEL` | Optional override, currently set | Server config | current live Meta model |
| `AICREDITS_BASE_URL` | Optional default | Server endpoint | all AICredits calls |
| `AICREDITS_TIMEOUT_SECONDS` | Optional default 60 | Server config | report/feedback timeout |
| `AICREDITS_REALTIME_TIMEOUT_SECONDS` | Optional default 30 | Server config | M1/Meta timeout |
| `AICREDITS_M1_REASONING_EFFORT` | Optional default `minimal` | Server config | GPT-5 Nano M1 only when that exact model is selected |
| `GROQ_API_KEY` | Optional legacy | Secret | legacy M1 fallback key |
| `GROQ_M1_API_KEY` | Optional legacy | Secret | isolated legacy M1 key |
| `GROQ_MODEL`, `GROQ_BASE_URL`, `GROQ_TIMEOUT_SECONDS` | Optional legacy | Server config | selectable Groq M1 |
| `GROQ_ORCHESTRATOR_API_KEY` | Optional legacy | Secret | selectable Groq Meta |
| `GROQ_ORCHESTRATOR_MODEL`, `GROQ_ORCHESTRATOR_BASE_URL`, `GROQ_ORCHESTRATOR_TIMEOUT_SECONDS` | Optional legacy | Server config | selectable Groq Meta |
| `OLLAMA_API_KEY` | Optional legacy | Secret | selectable Ollama M1 |
| `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_SECONDS` | Optional legacy | Server config | selectable Ollama M1 |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Optional legacy | Secret/config | selectable direct Gemini M1 |
| `OPENAI_API_KEY` | Mandatory in Settings, not used by current AICredits live/report paths | Secret | selectable direct OpenAI M1 and legacy question/resume services |

### Official Agora interview variables

| Variable | Requirement | Exposure | Used by |
|---|---|---|---|
| `AGORA_APP_ID` | Required | Server config; app ID also public in browser response | official RTC/RTM and agent API |
| `AGORA_APP_CERTIFICATE` | Required | Secret | Token007 minting |
| `AGORA_ALEX_PROJECT_ID`, `AGORA_ALEX_PIPELINE_ID` | Required unless safe code defaults intentionally retained | Server config | Alex lifecycle |
| `AGORA_JORDAN_PROJECT_ID`, `AGORA_JORDAN_PIPELINE_ID` | Required unless safe code defaults intentionally retained | Server config | Jordan lifecycle |
| `AGORA_CUSTOM_LLM_PIPELINE_ID` | Optional common override | Server config | shared Custom LLM pipeline |
| `AGORA_CUSTOMER_ID`, `AGORA_CUSTOMER_SECRET` | Production-required for Basic REST auth in current deployment | Secret | official agent join/query/leave |
| `AGORA_REST_API_KEY`, `AGORA_REST_API_SECRET` | Configured but unused by inspected official service | Secret | legacy/reserved |
| `CUSTOM_LLM_URL` | Required; stable public HTTPS URL | Server config | Agora callback destination |
| `CUSTOM_LLM_API_KEY` | Required and secret | Secret | forwarded by Agora; currently not validated by callback route |

### Morgan/Taylor and external communication variables

| Variable | Requirement | Exposure | Used by |
|---|---|---|---|
| `AGORA_TRAINING_HR_APP_ID` | Required for auxiliary voice | Server config; returned to browser session | separate Agora project |
| `AGORA_TRAINING_HR_APP_CERTIFICATE` | Required | Secret | auxiliary tokens |
| `AGORA_TRAINING_HR_API_TOKEN` | Required | Secret | auxiliary Agora REST auth |
| `AGORA_TAYLOR_AGENT_ID`, `AGORA_TAYLOR_AGENT_RTC_UID` | Required for Taylor | Server config | retained Studio pipeline |
| `AGORA_MORGAN_AGENT_ID`, `AGORA_MORGAN_AGENT_RTC_UID` | Required for Morgan | Server config | retained Studio pipeline |
| `AGORA_MORGAN_LLM_MODE` | Optional default `studio`; currently `managed` | Server config | Morgan LLM override |
| `AGORA_MORGAN_MANAGED_MODEL` | Required when managed mode selected | Server config | Morgan model |
| `VOICE_ASSISTANT_PUBLIC_URL` | Required; stable public HTTPS origin | Server config | MCP URL/origin validation |
| `VOICE_ASSISTANT_SESSION_SECONDS`, `VOICE_ASSISTANT_IDLE_SECONDS` | Optional defaults | Server config | assistant lifecycle |
| `MORGAN_COMPOSIO_MCP_URL` | Required for connected tools | Secret-like endpoint | Composio bridge |
| `MORGAN_COMPOSIO_API_KEY` | Required for connected tools | Secret | Composio authentication |
| `MORGAN_COMPOSIO_OWNER_USER_ID` | Required for connected writes | Server authorization config | recruiter ownership fence |
| `RESEND_API_KEY`, `RESEND_FROM_EMAIL` | Optional alternative email route | Secret/config | direct email delivery |
| `DEEPGRAM_API_KEY` | Optional and not used for official managed STT | Secret | legacy/direct integration |

### Dormant AWS variables

`AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `AWS_CLOUDFRONT_DOMAIN` support the old optional S3 helper. Current resume storage falls back to Supabase Storage, and current report generation does not produce a PDF. They are not required for the intended compute-only EC2 deployment.

## 9. Current UI state

### Interviews

- `/admin/interviews` is a list/card view with candidate, job, local date/time, duration, status, Open Room, Candidate, and completed-report links.
- There is no calendar view or list/calendar toggle in the current page.
- Reusable N-agent interview templates have a separate `/admin/interviews/templates` screen.
- Scheduling, rescheduling, instant invitations, ten-minute candidate acceptance, and template snapshots exist in backend/frontend flows, primarily through job/candidate surfaces and Morgan tools.

### Interview room

- The room uses the same design tokens as the portal (`bg-bg`, `bg-surface`, `text-*`, `brand`, success/warning/error states) in a full-screen meeting layout.
- It contains a top connection/status bar, candidate camera stage, AI avatar/status overlays, microphone/camera/audio controls, participants sidebar, autoplay recovery, microphone diagnostics, and explicit agent audio lifecycle states.
- It is visually more meeting-focused than recruiter pages but no longer uses a separate hardcoded visual theme.

### Reports and training

- Recruiter report discovery includes completed interviews even when a report has not yet been generated and exposes progress/retry state.
- Candidate pages display only candidate-safe rating and feedback when report status is ready.
- Taylor's training page returns indicative practice scoring, criteria, strengths, improvements, and grounded/template better-answer examples. It is explicitly separate from official application scoring.

## 10. Deployment blockers and warnings

### BLOCKER

1. **Custom LLM callback authentication is not enforced.** `CUSTOM_LLM_API_KEY` is sent by Agora, but `custom_llm/router.py` only logs whether Authorization exists. Any caller that can reach `/v1/chat/completions` or `/api/v1/chat/completions` can invoke the interview intelligence path and potentially inject session/channel identifiers.
2. **Public live-control and transcript endpoints are overexposed.** Current routes allow unauthenticated session creation/start/stop, Agora token minting, agent config/token retrieval, agent start/stop, webhook ingestion, transcript event ingestion, and transcript reads. Opaque interview UUIDs are not an adequate authorization boundary for agent control or transcript access. Agora webhooks also lack signature/secret verification.
3. **The Docker frontend cannot receive production public variables correctly.** Next public values are compile-time values. Compose provides only runtime `NEXT_PUBLIC_API_URL`, provides no `NEXT_PUBLIC_AGORA_APP_ID`, the Dockerfile has no build args, and `.env*` is excluded. A production image will otherwise embed localhost/empty values.
4. **No stable HTTPS ingress exists.** The included nginx only proxies local PostgREST. It does not route the frontend/backend, terminate TLS, preserve the Custom LLM SSE route, or provide the stable public URLs required by Agora and Morgan MCP. `CUSTOM_LLM_URL` is hardcoded to a temporary ngrok hostname in Compose.
5. **Compose forces unsafe development configuration.** It sets development/debug, a committed development JWT secret, localhost public URLs, and binds database/Redis/API ports to all interfaces. This must be replaced with production configuration and restricted host exposure before an EC2 security group is opened.
6. **Official interview critical state is process-local.** Meeting lifecycle, InterviewAIContext, and transcript stores are Python singletons. Multiple Uvicorn workers will diverge, and a restart loses active question history/context/transcripts. Durable session rehydration recreates metadata but cannot reconstruct the complete active conversation. Deploying with automatic container restarts does not preserve an in-progress interview.
7. **Post-interview execution is not a durable worker.** Report claims are durable, but execution uses a process-local task. A restart interrupts it; the user must wait for the five-minute stale threshold and retry. A single-node production release needs startup recovery or an explicit durable worker/queue strategy.
8. **Complete CI gates are red.** Full backend: 19 failed, 1,725 passed, 35 skipped. The failures are primarily older Groq-specific orchestrator tests inheriting the active AICredits environment, plus one partial turn-context fixture failure. Frontend lint: 41 errors and 47 warnings. A passing production build does not make these clean.
9. **Direct slot booking can accept a past slot.** Morgan's tool validates future timestamps, but `SchedulingService.book_slot` and the repository's available-slot query do not exclude past dates. The recruiter REST/UI path can still expose or book stale unbooked slots.
10. **Readiness does not test dependencies.** `/api/v1/ready` always returns ready. It does not verify Supabase, Redis, selected AICredits credentials/provider, Neo4j, stable callback configuration, or required Agora settings. Compose can route traffic to a backend that cannot run interviews.

### WARNING

1. Local Postgres/PostgREST/gateway are redundant in the planned external-Supabase architecture and increase attack surface and operational load.
2. The official backend must run one Uvicorn worker until interview state is externalized. This limits safe horizontal scaling and zero-downtime deployment.
3. The frontend build fetches Inter from Google Fonts. The build passes with network access but fails in an offline/restricted builder.
4. `OPENAI_API_KEY` and `DATABASE_URL` are mandatory settings even when their active paths do not need them. Production must still provide values unless configuration validation is narrowed.
5. The backend service-role client bypasses Supabase RLS by design. Tenant/privacy boundaries therefore depend on every backend route applying actor/workspace authorization correctly.
6. Browser auth state is cached in localStorage in addition to the cookie used by route middleware. XSS would expose that bearer token.
7. No report PDF is generated. The UI correctly hides download when `pdf_url` is absent, but any product promise of downloadable report PDFs is incomplete.
8. Old GPT-OSS/Groq/Nemotron names and comments make runtime diagnosis easy to misread and should be cleaned after deployment-critical work.
9. Frontend middleware convention is deprecated in Next.js 16; build warns that it should migrate to `proxy`.
10. Current worktree is not a reproducible release: it includes four uncommitted application edits and a deleted `LICENSE`.

### INFORMATION

1. External Supabase and Neo4j Aura connectivity passed on 6 September 2026.
2. The running local Compose stack includes six services and was healthy/reachable during the audit.
3. A network-enabled `npm run build` passed. All 62 frontend behavior tests passed.
4. Focused backend suites for AICredits, reports, completion, memory, sessions, and voice tools passed 366/366.
5. The post-interview report migration is recorded as applied to the configured Supabase project.
6. STT and TTS remain Agora-managed; AWS does not need speech infrastructure.
7. Groq/Ollama support remaining in source does not mean either is currently active.

## 11. Verification performed

| Check | Result |
|---|---|
| `docker compose config --quiet` | PASS |
| Current Compose status | PASS: six services running; backend/Postgres/Redis healthy |
| Backend `/api/v1/health` | HTTP 200 |
| Backend `/api/v1/ready` | HTTP 200, but shallow by implementation |
| Frontend root | HTTP 200 |
| Network-enabled frontend production build | PASS; 20 static/dynamic routes compiled |
| Frontend behavior tests | PASS: 62/62 |
| Frontend lint | FAIL: 41 errors, 47 warnings |
| Focused backend integration/unit suites | PASS: 366/366 |
| Full backend suite | FAIL: 19 failed, 1,725 passed, 35 skipped |
| Supabase scheduled interviews/reports/templates read | PASS |
| Neo4j Aura connectivity | PASS |
| Fresh AICredits live call | NOT PERFORMED in this audit; prior live artifacts inspected |
| Fresh Agora browser voice E2E | NOT PERFORMED in this audit; prior user-confirmed evidence inspected |
| Docker image rebuild | NOT PERFORMED; existing running images inspected; host frontend build passed |
| AWS commands/deployment | NOT PERFORMED; AWS remains paused |

## 12. EC2 deployment recommendation

**EC2 + Docker Compose is sufficient for the first production deployment after the blockers are fixed.**

The intended traffic and service graph does not require RDS, ECS, EKS, Lambda, API Gateway, ALB, CloudFront, ElastiCache, DynamoDB, Bedrock, CodeBuild, CodeDeploy, CodePipeline, Secrets Manager, Parameter Store, or S3. Supabase supplies durable SQL/object persistence, Neo4j Aura supplies the graph, Agora supplies realtime media/STT/TTS/agents, AICredits supplies interview/report inference, and Composio supplies connected HR tools.

The first release should run one backend process, one frontend process, one private Redis instance, and one public reverse proxy on one EC2 host. Local PostgreSQL, PostgREST, and the current PostgREST-only gateway should be removed from the production Compose profile. Because official interview state is process-local, this recommendation accepts a documented single-process availability limitation until that state moves to Redis/Supabase.

### Minimum eventual AWS resources

- one EC2 instance sized after a short concurrency/load test;
- its root EBS volume, with enough space for images/logs and no candidate-file dependency;
- one security group exposing only 80/443 publicly and restricted SSH or SSM access;
- an Elastic IP so Agora callback/DNS targets remain stable;
- the default VPC/subnet/route/Internet Gateway or an equivalent simple public subnet;
- optional Route 53 hosted zone/records only if DNS is managed in AWS. Existing external DNS is equally valid;
- no instance role is required for application storage when Supabase remains the object store. Use an instance role only if choosing SSM or another explicitly approved AWS integration later.

TLS can be terminated by Caddy/nginx on the instance with Let's Encrypt. That avoids ALB and ACM for this first deployment.

## 13. Proposed next step — do not execute yet

1. Make a clean release commit on `v2`: resolve the deleted `LICENSE`, review/commit the four scheduling edits, and tag an audit baseline.
2. Add mandatory authentication/authorization to official session/agent/token/transcript routes and constant-time bearer validation to the Custom LLM callback. Add verified webhook authentication.
3. Create a production Compose profile with frontend, backend, Redis, and one TLS reverse proxy only. Bind backend/Redis to the private Compose network.
4. Pass `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_AGORA_APP_ID`, and `NEXT_PUBLIC_APP_ENV` as frontend build args and build the final image for the real public origin.
5. Replace the ngrok callback and localhost values with stable HTTPS URLs; make CORS accept only the production frontend origin.
6. Add dependency-aware readiness checks without sending model generations on every probe.
7. Make report recovery durable across backend restart and either persist official live session/context/transcript state or explicitly enforce one worker plus maintenance windows that never interrupt active interviews.
8. Reject/filter past slots in the service/repository path, including direct recruiter booking, and validate follow-up/instant scheduling for completed applications consistently.
9. Isolate tests from local `.env`, update stale Groq-only expectations to explicit provider fixtures, fix the remaining context fixture, and clear frontend lint. Re-run full backend, frontend behavior, lint, production builds, and container smoke tests.
10. Run one final real acceptance session: recruiter creates/schedules, candidate joins, Alex greeting, two candidate/agent turns, Jordan handoff, completion, Neo4j evidence, persisted recruiter report, candidate feedback, Morgan read/action confirmation, and Taylor feedback. Capture stage IDs and timings without secrets.
11. Only after all gates pass, request the AWS host/domain/access details and execute the separately reviewed EC2 deployment plan.

**AWS remains PAUSED.**
