# Intra AI current codebase status

Historical baseline: this audit describes the revision and date below. For later implementation and live voice validation, see [the conversation fix report](INTRA_AI_CONVERSATION_FIX_REPORT.md). Diagnostic files referenced by these reports are local artifacts and are not committed.

Audit date: 2026-09-05
Scope: the checked-out working tree at `HEAD` (`final`, `af588baf1caecfc88ed1c53567ee751a2327c795`)
Method: source inspection, route/client comparison, offline smoke checks, automated tests, TypeScript check, frontend build, lint, and Docker Compose validation. No migrations, external-service calls, or source changes were performed.

## 1. Executive summary

Intra AI is a substantial prototype with two largely separate products in one repository. The ATS surface has real FastAPI services, Supabase/Postgres repositories, a Next.js recruiter/candidate UI, seeded local data, and a coherent application-to-scheduling-to-report data model. The adaptive voice surface has typed short-term interview state, an OpenAI-compatible Agora Custom LLM endpoint, deterministic turn classification, M1 analysis, a LangGraph meta-orchestrator, Alex and Jordan profiles, transcript normalization, and a Neo4j repository abstraction.

The implementation is not yet a verified end-to-end product. The live voice path depends on external Agora configuration and credentials, and the current `backend/.env` selects Groq for M1 but has no separate orchestrator key or Neo4j configuration. The live session stores and transcript store are process-local memory. The current session start path starts only the first logical agent; a `SWITCH_AGENT` changes logical context and sends frontend RTM state, but does not start the incoming Agora agent or stop the outgoing one. The candidate-facing report and completion pages still contain mock/static behavior. Reports are produced from the legacy Postgres `evaluations` pipeline and OpenAI narrative generation, rather than from M1/Knowledge Graph/orchestrator outputs.

| Classification | Current evidence |
|---|---|
| **IMPLEMENTED** | FastAPI application and health routes; JWT/bcrypt auth; ATS CRUD, application upload, slots, booking, evaluations and reports; Next.js routes and typed API client; deterministic in-memory interview context and transcript stores; M1 schemas/providers; LangGraph orchestration; Agent Registry with Alex/Jordan; Neo4j and in-memory graph repositories; SSE/OpenAI-compatible Custom LLM adapter; unit/component test coverage. |
| **PARTIAL** | Agora RTC/RTM and Conversational AI REST integration; candidate interview UI; transcript ingestion; adaptive difficulty; cross-agent logical handoff; candidate/JD context providers; resume parsing; eligibility; notifications; PDF/report delivery; Docker local stack. |
| **MISSING** | `GET /api/v1/auth/me`; JD parse endpoints used by the UI; application invite endpoint; candidate self-service applications endpoint; report list/detail endpoints used by the UI; durable session/transcript state; live Neo4j/M1/orchestrator validation in this audit; physical Agora agent handoff; production authorization/tenant isolation. |
| **UNVERIFIED** | Any real Agora RTC/ASR/TTS conversation; Custom LLM requests from Agora Cloud; live Groq calls; live Neo4j connectivity; S3, Resend, Postgres/PostgREST and Docker runtime behavior; report PDF generation. |

The largest blockers to a complete demo are external voice validation, missing UI/backend contracts, synthetic/in-memory session identity, and the lack of a physical agent handoff. The architecture boundaries are generally sound, especially the separation of M1 analysis from routing, but several compatibility and persistence seams are still prototype-grade.

## 2. Repository and Git state

- Branch: `final`, tracking `intra-ai/final`.
- HEAD: `af588ba` (`feat: integrate recruiter and candidate product UI`), authored 2026-09-05.
- Working tree: clean; no staged changes, unstaged changes, or untracked files at audit time.
- Recent ancestry: `f7d090c` initial release → `9713107` adaptive interview/Agora adapter → `6f5c487` orchestration/session fixes → `0986f54` core stores/router/frontend launcher → `22f6499` KG/context/persona work → `2106126` Groq orchestrator migration → `af588ba` product UI.
- Remote branches visible: `intra-ai/main` (`0986f54`), `intra-ai/update` (`2106126`), `intra-ai/final` (`af588ba`), and `intra-ai/vishnu` (`4d4b871`). `final` is five commits ahead and seven behind `intra-ai/vishnu`; `intra-ai/vishnu` is not an ancestor of `HEAD`. The tree therefore contains no evidence of a merged vishnu branch. The commit graph shows selectively developed/integrated work from the main/update line, but cannot prove that individual vishnu changes were selectively cherry-picked.
- `git ls-files -u` returned no entries: no merge conflicts.

## 3. Actual high-level architecture

```text
Browser (Next.js App Router)
  ├─ AuthContext + cookie/localStorage token storage + Next middleware RBAC
  ├─ TanStack Query + typed fetch client
  ├─ ATS pages: public jobs/apply, recruiter jobs/candidates/interviews/reports
  └─ candidate prep/interview pages
       ├─ POST /api/v1/sessions/{id}/start
       ├─ Agora RTC SDK (mic, remote audio, volume events)
       └─ Agora RTM SDK (messages, transcript capture, logical handoff state)
                               │
FastAPI app (`backend/app/main.py`, `/api/v1`)
  ├─ Auth/JWT, ATS routes, scheduling/evaluation/report routes
  ├─ Session boundary (`routes/sessions.py`) + process-local SessionStore
  ├─ Agora token/agent service (`agora_token2.py`, `agora_agent_service.py`)
  ├─ transcript service/store (process-local normalized events)
  └─ Custom LLM (`/v1/chat/completions` and `/api/v1/chat/completions`)
       ├─ parse OpenAI-compatible request and resolve session/agent
       ├─ fast-path classifier (audio check/pause/repeat)
       ├─ M1 Interview Intelligence (Groq/Gemini/Ollama/OpenAI/mock)
       ├─ AgentTurnContextBuilder (CV/JD/KG memory/live snapshot)
       ├─ LangGraph Meta-Orchestrator → NextAction
       └─ optional Knowledge Graph persistence

Persistence and providers
  ├─ Supabase-compatible PostgREST/Postgres (ATS tables, repositories)
  ├─ Neo4j AuraDB (optional KG system of record; not configured in audit env)
  ├─ Redis client and Docker Redis (wrapper exists; core session/transcript stores do not use it)
  ├─ S3/CloudFront (resume/report storage; optional and unconfigured here)
  ├─ OpenAI (legacy resume/questions/evaluation/report narrative)
  ├─ Groq M1 and Groq orchestrator endpoints (separate settings, external)
  ├─ Agora Conversational AI v2 REST + RTC/RTM SDK
  ├─ Deepgram ASR/OpenAI TTS configured in Agora mappings
  └─ Resend email client (service exists; no route/service orchestration invokes it)
```

### Component responsibilities and status

| Component | Key files | Inputs/outputs and status | Limitations/dependencies |
|---|---|---|---|
| Frontend | `frontend/src/app/**`, `context/AuthContext.tsx`, `lib/api/**` | Next 16 App Router pages, browser API calls and Agora SDK; **IMPLEMENTED UI / PARTIAL integration**. | Several clients call absent routes; two interview report pages are static/mock. |
| API/auth | `backend/app/main.py`, `routes/auth.py`, `core/security.py`, `services/auth_service.py` | Signup/login/refresh return JWT and user; **IMPLEMENTED**. | No `/auth/me`; bearer JWT is accepted without a DB lookup on ordinary protected dependencies; roles are token claims. |
| ATS data | `routes/jobs.py`, `applications.py`, `candidates.py`, `scheduling.py`; repositories and `docker/init-db/01-init.sql` | Supabase client/repository CRUD; **IMPLEMENTED in code, UNVERIFIED against running DB**. | No Alembic/Supabase migration history; init SQL is a one-shot Docker seed. |
| Live session | `sessions/models.py`, `sessions/store.py`, `sessions/service.py` | Creates in-memory `InterviewSession`, generates token, starts initial agent; **PARTIAL**. | Process restart loses sessions; start response can contain no candidate credentials on an already-running session; candidate ID can be synthetic. |
| Agora | `services/agora_agent_service.py`, `routes/interviews.py`, `core/agora_token2.py`, frontend interview page | Token generation, v2 join/leave payload, RTC/RTM listeners; **PARTIAL/UNVERIFIED**. | Requires App ID/certificate/customer credentials and valid Agent Studio pipelines; only initial agent is physically started. |
| Custom LLM | `custom_llm/router.py`, `models.py`, `adapter.py` | OpenAI-compatible JSON/SSE; resolves context, runs M1→orchestrator→response; **IMPLEMENTED contract, UNVERIFIED live**. | `process_turn_async` completes M1 and orchestration before word-by-word SSE; direct no-session requests create ephemeral sessions. |
| M1 | `interview_intelligence/{models,provider,analyzer,prompts}.py` | Produces `AnswerAnalysis` (scores, evidence, findings, vagueness/contradictions/follow-up); **IMPLEMENTED with mock and providers**. | Default setting is mock; real providers need keys; no live Groq call was performed. |
| Orchestrator | `orchestrator/{graph,service,models,policies,prompts}.py` | LangGraph state machine returns validated `NextAction`; **IMPLEMENTED and unit-tested**. | Groq orchestrator key absent in `backend/.env`, so deterministic fallback is normally used. |
| Agent registry/context | `agents/**`, `agent_context/**`, `interview_context/**` | Alex/Jordan profiles, mappings, bounded prompt snapshots and handoff context; **IMPLEMENTED/PARTIAL**. | New profiles can register generically, but Agora mapping/configuration still needs to be supplied; default providers are fallback-only and not wired to repositories. |
| Transcript | `transcript/{models,service,store}.py`, interview routes, frontend RTM | Webhook/RTM normalized, deduplicated and retrievable; **IMPLEMENTED in memory**. | No durable transcript table or Redis use; one resolver fallback still uses `test-room-101` for absent identifiers. |
| Knowledge Graph/memory | `knowledge_graph/{models,repository,neo4j_repository,service,memory_service,schema}.py` | Typed Candidate/Round/Question/Answer/Evidence/Competency plus project/skill/technology models; **IMPLEMENTED abstraction, live status UNVERIFIED**. | Neo4j is optional; no configured URI; synchronous persistence mode adds a graph write after orchestration. |
| Database | `docker/init-db/01-init.sql`, `repositories/**` | Postgres schema for ATS/interviews/reporting and indexes; **IMPLEMENTED as init SQL**. | No applied migration evidence; schema drift risk; `parsed_resumes.candidate_id` is required but application code’s upsert omits it. |
| Redis | `integrations/redis_client.py`, `main.py`, compose | Client wrapper with TTL/cache-aside and app lifespan ping; **PARTIAL**. | Session, context and transcript state use Python dictionaries; no pub/sub or durable Redis state path. |
| External providers | `integrations/{groq,openai,ollama,s3,email}_client.py`, Agora service | Provider wrappers exist; **mostly UNVERIFIED**. | Missing credentials/configuration and no live validation in this audit. |

## 4. Frontend status

Framework: Next.js `16.1.6`, React `19.2.3`, TypeScript, Tailwind v4, Radix UI, Framer Motion, TanStack Query, `agora-rtc-sdk-ng` and `agora-rtm-sdk`. Routing is the App Router under `frontend/src/app`.

| Area | Pages/files | Status and evidence |
|---|---|---|
| Landing/public navigation | `src/app/page.tsx`, `(public)/layout.tsx`, `components/landing/**`, `public-nav.tsx` | **IMPLEMENTED UI**; landing page is mostly presentation. |
| Auth UI | `(auth)/login/page.tsx`, `(auth)/signup/page.tsx`, `AuthContext.tsx`, `middleware.ts` | **IMPLEMENTED UI and token flow**. Login/signup call real routes; refresh calls `/auth/refresh`; middleware decodes JWT and protects `/admin` and `/portal`. |
| Recruiter/admin | `admin/dashboard`, `jobs`, `jobs/new`, `jobs/[id]`, `candidates`, `candidates/[id]`, `interviews`, `reports`, `settings` | **IMPLEMENTED UI / PARTIAL API integration**. Pages use query hooks and real clients for jobs, candidates, applications, slots/interviews and reports. Settings is predominantly local state and has no corresponding settings API. |
| Public job/application | `(public)/jobs`, `[id]`, `[id]/apply`, success | **IMPLEMENTED UI and apply client**. Public job calls map to real public routes; multipart apply maps to real `POST /jobs/{job_id}/apply`. Resume parsing/eligibility are backend services but not invoked by the apply route. |
| Candidate portal | `(candidate)/portal`, `candidate-nav.tsx` | **PARTIAL**. It calls `getMyApplications()` (`GET /api/v1/candidates/me/applications`), which does not exist. |
| Scheduling | `(candidate)/schedule/[token]`, admin job detail, `useScheduling.ts` | **PARTIAL**. Slot listing/creation and booking clients map to existing routes; booking route is unauthenticated and service validates application status. The candidate token flow is not authenticated or bound to a candidate. |
| Interview prep/room | `(candidate)/interview/[token]/prep`, `[token]`, `[token]/done`, `[token]/report` | **PARTIAL**. Prep and room call `/sessions/{id}` and `/start`; room uses RTC/RTM and transcript events. Done simulates report readiness with a 120-second timer. Report page renders a hard-coded `REPORT` object and does not call report APIs. |
| Shared state/data | `context/QueryProvider.tsx`, `lib/query-client.ts`, `hooks/queries/**` | **IMPLEMENTED** TanStack Query singleton with 5-minute stale time and one retry; no global interview state store beyond component/sessionStorage state. |
| API client | `lib/api/client.ts`, `lib/api/*.ts`, `types/api.ts` | **IMPLEMENTED typed fetch layer** with bearer injection, FormData handling, 401 cleanup and error normalization. Some comments correctly mark missing contracts, but clients still expose/use missing endpoints. |
| Environment | `lib/env.ts`, `frontend/.env.example` | **IMPLEMENTED** public `NEXT_PUBLIC_API_URL`, Agora app ID, app env and WS URL. Current `.env.local` only contains API URL; no evidence of a live Agora frontend app ID. |
| RTM | interview room page | **PARTIAL/UNVERIFIED**. Creates RTM client using the RTC token, logs in/subscribes, handles handoff/transcript payloads. Agora RTM token semantics and live event shape are not validated. |

### Frontend/backend contract mismatches

| Frontend call | Backend reality | Result |
|---|---|---|
| `getMyApplications()` → `GET /api/v1/candidates/me/applications` | No route in `routes/candidates.py` | Candidate portal query fails. |
| `inviteApplication()` → `POST /api/v1/applications/{id}/invite` | No route | Recruiter invite action fails. |
| `parseJdFile/parseJdText()` → `POST /api/v1/jobs/parse-jd` | No route in `routes/jobs.py`; no JD parsing service route | New-job JD parsing fails. |
| `getReports()` → `GET /api/v1/reports` | Reports router is prefixed `/interviews` and only exposes interview-scoped report routes | Admin reports list fails. |
| `getReport(id)` → `GET /api/v1/reports/{id}` | No route | Report detail client path fails unless using interview-scoped hook. |
| `GET /api/v1/auth/me` expected by the stated architecture | No route; frontend currently uses refresh instead | Any caller expecting `/me` receives 404. |
| Candidate report page | Does not call an API | Appears populated but is not current interview data. |

## 5. Backend API inventory

All listed API routes are mounted under `/api/v1` except the duplicate Custom LLM router under `/v1` and `/api/v1`. Authentication below is route dependency behavior, not a claim that identity is loaded from the database.

| Route | Method | Implementation/service | Auth | Status |
|---|---|---|---|---|
| `/auth/signup` | POST | `routes/auth.py` → `AuthService.signup` → `UserRepo` | Public | Implemented. |
| `/auth/login` | POST | `AuthService.login` | Public | Implemented. |
| `/auth/refresh` | POST | `AuthService.refresh` | Bearer | Implemented. |
| `/auth/me` | GET | None | — | Missing; smoke check returned 404. |
| `/health` | GET | `routes/health.py` | Public | Implemented; smoke 200. |
| `/jobs/public`, `/jobs/public/{id}` | GET | `JobService.get_public_jobs/get_job` → `JobRepo` | Public | Implemented in code. |
| `/jobs` | GET/POST | `JobService.get_jobs/create_job` | admin/recruiter | Implemented. |
| `/jobs/{id}` | PATCH | `JobService.update_job` | admin/recruiter | Implemented. There is no GET admin detail route; frontend `getJob()` calls it and receives method/path mismatch. |
| `/jobs/{id}/publish`, `/archive` | POST | `JobService` | admin/recruiter | Implemented. |
| `/jobs/{id}/apply` | POST multipart | `ApplicationService.apply` → candidate/job/application repos, S3 | Public | Implemented in code; requires S3 config at runtime. |
| `/jobs/{id}/applications` | GET | `ApplicationService.get_applications` | admin/recruiter | Implemented. |
| `/applications/{id}` | GET | `ApplicationService.get_application` | admin/recruiter | Implemented. |
| `/applications/{id}/parsed-resume` | GET | `ApplicationService.get_parsed_resume` | admin/recruiter | Implemented. |
| `/applications/{id}/shortlist`, `/reject` | POST | `ApplicationService` | admin/recruiter | Implemented. |
| `/applications/{id}/invite` | POST | None | — | Missing. |
| `/candidates` | GET | `CandidateRepo.list` | admin/recruiter | Implemented, but response does not populate applications despite frontend deriving latest application. |
| `/candidates/{id}` | GET | `CandidateRepo.get_by_id` | admin/recruiter | Implemented. |
| `/candidates/{id}/applications` | GET | `CandidateRepo.list_applications` | admin/recruiter | Implemented. |
| `/candidates/me/applications` | GET | None | — | Missing. |
| `/jobs/{id}/slots` | GET/POST | `SchedulingService`/`InterviewRepo` | GET public; POST admin/recruiter | Implemented. |
| `/applications/{id}/schedule` | POST | `SchedulingService.book_slot` | Public | Implemented, but no candidate token/identity authorization. |
| `/interviews` | GET | `InterviewService.list_interviews` | admin/recruiter | Implemented via `routes/scheduling.py`. |
| `/interviews/{id}` | GET | `InterviewService.get_interview` | admin/recruiter | Implemented. |
| `/interviews/{id}/start`, `/end` | POST | `InterviewService` | Bearer any role | Legacy Postgres interview lifecycle, separate from `/sessions`. |
| `/interviews/{id}/questions`, `/questions/generate` | GET/POST | `QuestionService` → legacy OpenAI | Bearer any role | Implemented but separate from Custom LLM voice loop. |
| `/interviews/{id}/answers` | POST | `InterviewRepo.create_answer` | Bearer any role | Implemented legacy transcript answer persistence. |
| `/interviews/{id}/evaluate`, `/evaluation` | POST/GET | `EvaluationService` → OpenAI | admin/recruiter | Implemented legacy evaluation path. |
| `/interviews/{id}/agora-token` | GET | `RtcTokenBuilder2` | Public | Implemented in code; requires Agora credentials; token validity not live-tested. |
| `/interviews/{id}/agora-agent-config` | GET | registry mapping + token builder | Public | Implemented payload generation; not a REST start call. |
| `/interviews/{id}/start-agent`, `/stop-agent` | POST | `AgoraAgentService` | Public | REST dispatch/leave code exists; external behavior unverified. |
| `/interviews/agora-webhook`, `/{id}/agora-webhook` | POST | `TranscriptService.ingest_agora_webhook` | Public | Implemented parser; no webhook signature verification. |
| `/interviews/{id}/transcript-events` | POST | `TranscriptService.ingest_event` | Public | Implemented in-memory event ingestion. |
| `/interviews/{id}/transcript` | GET | `TranscriptService.get_interview_transcript` | Public | Implemented in-memory retrieval. |
| `/sessions` | POST | `InterviewSessionService.create_session` | Public | Implemented process-local integration boundary. |
| `/sessions/{id}` | GET | session store | Public | Implemented process-local lobby lookup. |
| `/sessions/{id}/start`, `/stop` | POST | session service + Agora agent service | Public | Implemented orchestration path, external behavior unverified. |
| `/agents` | GET | `AgentRegistry` | Public | Implemented Alex/Jordan listing. |
| `/interviews/{id}/report/generate`, `/report` | POST/GET | `ReportService` → legacy evaluations + OpenAI | admin/recruiter | Implemented interview-scoped routes. |
| `/interviews/{id}/report/pdf` | GET | `ReportService`, redirect to stored `pdf_url` | admin/recruiter | Route exists; PDF generation/storage does not. |
| `/chat/completions` at `/v1` and `/api/v1` | POST | `CustomLLMAdapter` | Public | OpenAI JSON/SSE contract implemented; live Agora call unverified. |
| `/custom-llm/readiness` at both prefixes | GET | adapter `is_ready()` | Public | Always returns ready; does not test provider credentials. |

## 6. Authentication and authorization

Authentication is bcrypt password hashing plus signed JWTs from `python-jose` (`HS256`, configurable expiry). `AuthService` puts `sub`, `email` and `role` in the token. `core/security.py:get_current_user` verifies the bearer token and only checks that `sub` exists. `require_role()` checks the role claim against `admin`, `recruiter` or `candidate`.

The browser stores the token in `localStorage` and also writes an `intra_auth_token` cookie plus `intra_user_role` cookie in `lib/auth/token-storage.ts`. `AuthContext` restores cached user data, calls `/auth/refresh`, and globally logs out after a 401. `middleware.ts` decodes the unsigned JWT payload to guard `/admin` and `/portal`; the backend still verifies the signature.

There is no `GET /api/v1/auth/me`. A direct smoke request returned 404. The frontend currently relies on the user object returned from login/signup/refresh, so it works around the missing endpoint, but any external client using the stated `/me` contract will fail. Protected ATS routes use role checks, but most candidate-facing scheduling/session/transcript/Agora routes are public and use opaque IDs. There is no tenant authorization check in repositories or routes even though `tenant_id` exists in the SQL schema. Token claims are not rechecked against a live user record on every request, and signup accepts a caller-selected role, including `admin` or `recruiter`.

## 7. ATS and recruiter product

Job creation is real: `JobService.create_job` writes a draft job. `jobs/new` includes JD upload/text parsing calls, details, skill selection, round sequencing, agent mapping and publish validation UI. The parse calls are currently broken because `/jobs/parse-jd` is absent. Job creation sends `interview_rounds`, but `JobService.create_job` writes no `job_rounds` rows; the database schema and read queries expect that related table. This is a persistence gap even when the job row succeeds.

Public listings and details use published-job routes. Public application submits multipart fields and a resume to `ApplicationService.apply`, which creates or reuses a candidate, uploads to S3, updates the candidate row, and inserts an application. The service does not invoke `ResumeService`, `EligibilityService`, or `NotificationService`; parsing, eligibility and email are standalone services without a wired application workflow. The SQL `parsed_resumes` table requires `candidate_id`, while `ResumeService.parse_resume` upserts a row without that field, so the current schema can reject the operation.

Recruiter candidate pages use candidate and application routes. The list route only constructs `CandidateResponse` with `parsed_resume=None` and does not include applications, despite the UI trying to derive status/job from `c.applications`; the detail route and separate applications route provide more data. Shortlist/reject are real. Invite is UI/client-only with no backend route.

Scheduling has real slot creation, public availability lookup, and application booking. `book_slot` validates that an application is shortlisted/invited, marks the slot booked, inserts a `scheduled_interviews` row, and updates application status. It creates a UUID `room_token` as a placeholder, not an Agora/session credential, and does not send a notification. Recruiter interview listing/detail is real. There is no candidate-owned authorization on booking or interview lookup.

Reports are generated from `evaluations` rows (legacy 0–10 dimensions), averaged into 0–100 round scores, narrated through `openai_client.generate_report_summary`, and stored in `reports`. No M1 `AnswerAnalysis`, KG evidence, `NextAction`, transcript events, or persistent memory are consumed. `pdf_url` is always initialized `None`; there is no PDF rendering/upload implementation in `ReportService`, so the PDF route normally returns not found. The candidate report page is mock data, while admin report pages call mismatched list/detail clients.

## 8. Interview session lifecycle

1. The platform/test launcher posts an `InterviewConfiguration` to `POST /api/v1/sessions`. `routes/sessions.py` validates agent IDs and `SessionStore.create()` builds an in-memory `InterviewSession` with channel `intra-{interview_id}` and first agent as `current_agent_id`.
2. Candidate prep calls `GET /sessions/{id}`, checks lobby data, then calls `POST /sessions/{id}/start`. `InterviewSessionService.start_session()` validates the time window, builds a candidate RTC/RTM token, marks `STARTING`, and calls `AgoraAgentService.start_interview_agent()` for the initial agent only.
3. The service marks the session `IN_PROGRESS`, stores started agent IDs, creates a separate `InterviewAIContext` using `ctx_store.get_or_create()`, and registers the original interview ID as an alias for the channel. The context call in this path does not pass `candidate_id` in the audit smoke setup, so it can create a synthetic `cand-{channel}` candidate ID even though `InterviewSession` has a real candidate ID.
4. The room page joins Agora RTC with the returned candidate credentials, creates/publishes the microphone track, subscribes to remote audio, and logs volume/connection events. It also creates an RTM client and subscribes to the channel. This path is code-complete enough for a local browser integration, but no live RTC/ASR/TTS run was performed.
5. Agora sends an OpenAI-compatible request to the Custom LLM URL configured by `AgoraAgentService`. Query parameters `session_id` and `agent_id` are appended. `custom_llm.router.chat_completions()` merges query values into `x-session-id`/`x-agent-id`, parses the request, and selects JSON or SSE output.
6. `CustomLLMAdapter.parse_turn()` extracts the latest user message, resolves an interview ID from Agora/session/channel headers, and creates or loads `InterviewAIContext`. A missing identifier creates `sess-<uuid>`; `TranscriptService` has a separate legacy `test-room-101` fallback when no event identifier exists.
7. `process_turn_async()` serializes turns per interview lock, enforces that only the logical active agent processes a turn, classifies audio-check/pause/repeat controls, emits an opening question when appropriate, or calls M1. M1 returns `AnswerAnalysis`; `apply_analysis_to_context()` mutates live context with evidence/findings/contradictions.
8. The adapter builds an immutable deep-copied `AgentTurnContext` snapshot, invokes LangGraph, receives `NextAction`, changes difficulty, switches logical agent or marks completion, saves context, and then persists the turn to KG. KG persistence is awaited by default (`background_kg_persistence=False`); a task mode exists but has no durable queue.
9. The response is rendered as OpenAI-compatible SSE chunks (or JSON). The stream is word-split and terminated with `[DONE]`. M1 and orchestration happen before the first content chunk, so streaming reduces delivery buffering but does not overlap reasoning latency.
10. RTM transcript messages are normalized in the browser and posted to `/interviews/{token}/transcript-events`. The server deduplicates in memory and returns the active logical agent. RTM `SWITCH_AGENT` updates browser labels, but no route starts the target physical Agora agent or stops the source. `AgentTurnContextBuilder.build_handoff_context()` prepares a handoff snapshot only.
11. Candidate leave calls `/sessions/{token}/stop`; the session service stops IDs recorded in the initial `started_agents` map and marks the process-local session completed. It does not update the Postgres `scheduled_interviews` status, trigger evaluation, persist a report, or close transcript/KG state.

## 9. Agora integration

Backend packages include `agora-token-builder`. `core/agora_token2.py` creates RTC and RTM AccessToken2 tokens. `routes/interviews.py` exposes candidate token and agent-config payloads. `AgoraAgentService` calls the official v2 join endpoint with pipeline ID, channel, agent UID/token, RTM enablement, optional custom LLM URL, and TTS overrides; it calls the v2 leave endpoint when an Agora agent ID is known.

Alex and Jordan mappings include Deepgram Nova-3 ASR, OpenAI TTS, VAD/filler settings, project/pipeline IDs, and the Custom LLM URL. The service appends `session_id` and `agent_id` query parameters without embedding API keys. Frontend RTC handles microphone publication, remote audio subscription/autoplay, volume indicators, and connection state. RTM handles messages/transcripts and browser-side fallback SpeechSynthesis when no remote audio exists.

What is actually verified: payload construction, token code paths, service mocks (8 Agora agent tests and token tests), and frontend build. What is not verified: Agora project/pipeline validity, customer authorization, token acceptance, Agent Studio’s exact request headers/query behavior, Deepgram/OpenAI TTS behavior, RTM token semantics, webhook signatures, and a real candidate voice turn. The current `.env` has Agora App ID/certificate/customer fields configured, but those values are not reported here and no live call was made.

## 10. Custom LLM adapter

Endpoint: `POST /v1/chat/completions` and `POST /api/v1/chat/completions`, implemented in `custom_llm/router.py`. Request model `ChatCompletionRequest` accepts OpenAI messages plus `user`, `call_id`, `agent_uuid`, `channel`, `stream`, temperature and token fields. The adapter returns `ChatCompletionResponse` for non-streaming calls or `text/event-stream` with role/content chunks, terminal `finish_reason=stop`, and `data: [DONE]`.

Identity resolution order is `x-agora-session-id`, `x-session-id`, `x-interview-id`, channel headers, request `channel`, `call_id`, `agent_uuid`, then `user`; unresolved IDs create a fresh `sess-*` ID. Existing sessions preserve their authoritative active agent. An `x-agent-id` request that does not match the active agent is ignored with an empty content stream. New sessions without an agent identity fall back to Alex.

The cognitive path is classifier → opening/control response or M1 → context mutation → unified context builder → LangGraph orchestrator → state transition/response → KG persistence → SSE. M1 and orchestrator exceptions are isolated with spoken deterministic fallback questions. KG exceptions are logged and do not fail the turn. `is_ready()` always returns true and only reports adapter availability, not provider or Agora readiness. The synchronous `generate_response()` deliberately emits a static distributed-systems fallback if called inside an already-running event loop; this is a compatibility fallback, not the cognitive path.

## 11. M1 Interview Intelligence

`M1InterviewAnalyzer` accepts `InterviewAnswerInput` and returns the typed `AnswerAnalysis` contract. The model includes normalized performance/confidence, vague/vague reason, contradiction flags/details, missing information, evidence with provenance, competency findings with evidence IDs, and a recommended follow-up. Prompts explicitly prohibit hiring decisions, routing and `NextAction` generation.

Providers are selected by `M1_PROVIDER`: deterministic mock (default), Gemini, Ollama, Groq or OpenAI. Groq uses `openai/gpt-oss-20b`, `GROQ_BASE_URL`, timeout settings and `GROQ_M1_API_KEY` first, falling back to `GROQ_API_KEY`. It validates provider JSON strictly against `AnswerAnalysis`, fills missing evidence subject/source agent/round fields, and raises `M1ProviderError` on missing keys, network errors or schema failure. In `backend/.env`, `M1_PROVIDER=groq`, `GROQ_API_KEY` is nonempty, `GROQ_M1_API_KEY` is absent, so the generic key would be used; no separate M1 key separation is effective in the current environment. M1 itself does not decide difficulty, agent switching, completion or hiring.

## 12. Meta-Orchestrator

`build_orchestrator_graph()` builds a LangGraph with validation, completion analysis, guardrails, optional Groq routing, decision validation, action building and final contract validation. `NextAction` supports `ASK_QUESTION`, `SWITCH_AGENT`, and `COMPLETE`, with target agent, competency, difficulty, question text, rationale and metadata.

Deterministic guardrails force clarification for contradictions/vague answers and fundamentals for weak answers. Strong-but-shallow answers remain with the current agent. Otherwise the graph can call `call_groq()` with `GROQ_ORCHESTRATOR_API_KEY`, `GROQ_ORCHESTRATOR_MODEL` (default `openai/gpt-oss-20b`) and separate base URL/timeout settings. Invalid JSON, invalid target, self-switch, premature completion, API errors and absent key fall back to deterministic policy. In the actual `backend/.env`, `GROQ_ORCHESTRATOR_API_KEY` is absent, so the production process will skip Groq routing and use deterministic fallback.

Routing is genuinely registry-based for selection: `find_best_switch_agent()` scores overlap across every registered agent and does not hardcode Alex→Jordan. Alex/Jordan-specific wording exists in persona prompts and question helpers. The unit suite’s mocked Nemotron tests pass when the orchestrator key is supplied in-process; with no key, four existing cross-agent tests fail because their fixture expects a mocked Groq call but the graph correctly skips it. Physical agent switching is not implemented by the orchestrator; it only changes `InterviewAIContext` and produces handoff metadata.

## 13. Agent Registry and personas

`AgentProfile` defines ID, display name, role, description, focal competencies, questioning style, instructions, difficulty bounds, allowed actions and metadata. `AgentRegistry` stores profiles and optional `AgoraAgentMapping` factories, validates IDs/mappings, and supports arbitrary registration/reset. Alex (`agents/alex.py`) is technical with system design, architecture, coding, scalability, debugging and related areas. Jordan (`agents/jordan.py`) is product-focused with customer understanding, prioritization, strategy, metrics and product trade-offs.

Adding a third profile can be done through `registry.register(profile, mapping)` without changing routing code. A usable production agent still needs a valid Agora project/pipeline mapping and compatible voice configuration. The frontend `AgentRoundMapper` is hardcoded to display only Alex/Jordan, so adding an agent is configuration-only on the backend but requires frontend changes to expose it in job setup.

## 14. Agent context

`AgentTurnContext` composes candidate CV facts, job/JD context, `PersistentCandidateMemory`, mutable `InterviewAIContext`, active `AgentProfile`, current question/answer and M1 analysis. `DefaultCandidateProfileProvider` and `DefaultJobContextProvider` support in-memory profiles/jobs and optional repository objects, but the default `AgentTurnContextBuilder()` constructs them without repositories. Therefore live voice turns normally receive fallback candidate and job objects unless another caller injects providers.

Prompt serialization separates CV claims, JD data, persistent interview evidence and live state, labels data boundaries, and caps prompt output at 12,000 characters (`MAX_CONTEXT_*` constants). `build_turn_context()` deep-copies the interview state; `build_handoff_context()` clones it and changes the active agent while preserving evidence and memory. Short-term context is the mutable current interview state (active agent, difficulty, evaluated/missing competencies, open questions, contradictions, question history). Persistent memory is KG-derived candidate evidence/projects/skills/technologies/round summaries with provenance; it is retrieved read-only and bounded before injection. The current session creation path does not consistently pass real candidate/job IDs into this builder.

## 15. Knowledge Graph and persistent memory

The KG domain models implement nodes `Candidate`, `InterviewRound`, `Question`, `Answer`, `Evidence`, `Competency`, `Project`, `Technology`, and `Skill`. Relationships actually allowed are `PARTICIPATED_IN`, `HAS_PROJECT`, `HAS_SKILL`, `KNOWS_TECHNOLOGY`, `HAS_EVIDENCE`, `HAS_QUESTION`, `HAS_ANSWER`, `TARGETS_COMPETENCY`, `SUPPORTED_BY`, `SUPPORTS_COMPETENCY`, `USES_TECHNOLOGY`, and `DEMONSTRATES_SKILL`.

`KnowledgeGraphPersistenceService` maps an M1 answer into/upserts Candidate, Round, Question, Answer, Competency and Evidence nodes, then creates provenance relationships. `Neo4jKnowledgeGraphRepository` uses parameterized Cypher and validates labels/relationship endpoints. `InMemoryKnowledgeGraphRepository` is used heavily by tests. `CandidateMemoryService` retrieves candidate-scoped evidence, competency summaries, projects, skills, technologies and interview rounds with explicit limits and filters by competency, round and source agent.

Neo4j initialization is defined by idempotent constraints/indexes in `knowledge_graph/schema.py`; no migration or initialization was executed. `NEO4J_URI`, username and password are absent from the current backend environment, so the default KG and memory services disable themselves. Tests cover mocks and repository behavior; no live Neo4j connection was performed. Persistence is synchronous with respect to turn completion by default, implemented in a worker thread via `asyncio.to_thread`; an optional `asyncio.create_task()` background mode is non-durable and can lose writes on process crash. There is no queue, retry log or transactional coupling between context mutation and graph writes.

## 16. Database status

`docker/init-db/01-init.sql` is the only database schema/migration artifact found. It creates enums (as Postgres types), tenants, users, jobs, job rounds, candidates, applications, parsed resumes, eligibility scores, slots, scheduled interviews, questions, answers, evaluations, round/skill assessments, reports, proctoring events, notifications and AI decision logs, plus indexes, broad grants and seed rows. Repositories use Supabase/PostgREST calls through `JobRepo`, `CandidateRepo`, `ApplicationRepo`, `InterviewRepo` and `UserRepo`.

There is no evidence in the repository that this SQL has been applied to a running database. Compose starts Postgres and PostgREST and mounts the SQL as an init directory, so it applies only to a fresh Docker volume. Existing volumes will not receive later edits. There are no RLS policies; grants give broad access to `anon`, `authenticated`, `service_role`, `authenticator` and `postgres`. Schema compatibility risks include text columns where Pydantic expects enums, missing `job_rounds` inserts from job creation, `parsed_resumes.candidate_id` being required but omitted by `ResumeService`, and report/PDF fields that are never populated.

## 17. Redis, transcript and state

The app lifespan creates a Redis connection and pings it. `RedisClient` supports get/set/delete and cache-aside JSON with TTL. No route injects or uses `get_redis`, and there is no pub/sub implementation. Live sessions (`SessionStore`), M1 contexts (`InterviewSessionStore`) and transcripts (`TranscriptStore`) are Python process-local dictionaries/lists with asyncio locks. Transcript events are deduplicated by event ID and a two-second timestamp/text fingerprint, with intermediate-to-final replacement and deterministic ordering.

State expires only when explicitly cleared or when the process exits; there is no TTL, restart recovery, distributed lock or durable transcript storage. Multiple backend workers would have different session/context/transcript state. `TranscriptService._resolve_session_and_agent()` uses `test-room-101` if neither identifier nor channel is provided, which can misattribute malformed webhook/event payloads.

## 18. Reporting and evaluation

The active report path is `routes/evaluation.py` → `EvaluationService` → `openai_client.evaluate_answer`, then `routes/reports.py` → `ReportService`. The legacy path stores 0–10 relevance/depth/accuracy/communication/confidence/overall values, averages them into round scores, selects a recommendation threshold, calls OpenAI for narrative strengths/improvements/salary, and writes a report row. It does not read transcript-store events, M1 `AnswerAnalysis`, KG evidence, orchestrator rationale, difficulty changes or handoff history.

`reports.py` exposes only interview-scoped generation/get/PDF redirect. There is no report list endpoint, no report-by-report-ID endpoint and no PDF generation service. Admin report list/detail clients therefore have incompatible contracts. The candidate done page simulates readiness; the candidate report page is static sample content. Recruiter viewing of a current M1/KG report is therefore not implemented.

## 19. Configuration and environment

Required/optional variables by subsystem (names only; values intentionally omitted):

| Subsystem | Variables |
|---|---|
| Agora | `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_ALEX_PROJECT_ID`, `AGORA_ALEX_PIPELINE_ID`, `AGORA_JORDAN_PROJECT_ID`, `AGORA_JORDAN_PIPELINE_ID`, `AGORA_CUSTOMER_ID`, `AGORA_CUSTOMER_SECRET`, `AGORA_REST_API_KEY`, `AGORA_REST_API_SECRET`, `CUSTOM_LLM_URL` |
| Groq M1 | `M1_PROVIDER`, `GROQ_M1_API_KEY`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL`, `GROQ_TIMEOUT_SECONDS` |
| Groq orchestrator | `GROQ_ORCHESTRATOR_API_KEY`, `GROQ_ORCHESTRATOR_MODEL`, `GROQ_ORCHESTRATOR_BASE_URL`, `GROQ_ORCHESTRATOR_TIMEOUT_SECONDS` |
| Other M1 providers | `GEMINI_API_KEY`, `GEMINI_MODEL`, `OLLAMA_API_KEY`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `OLLAMA_TIMEOUT_SECONDS`, `OPENAI_API_KEY` |
| Database/Supabase | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` |
| Neo4j | `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE` |
| Redis | `REDIS_URL` |
| Auth | `JWT_SECRET`, `JWT_ALGORITHM`, `JWT_EXPIRY_MINUTES` |
| Storage | `AWS_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `AWS_CLOUDFRONT_DOMAIN` |
| Email | `RESEND_API_KEY` |
| Frontend | `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_AGORA_APP_ID`, `NEXT_PUBLIC_APP_ENV`, `NEXT_PUBLIC_WS_URL` |

`backend/.env.example` documents separate M1 and orchestrator variables. The actual `backend/.env` selects `M1_PROVIDER=groq` and has a generic `GROQ_API_KEY`, but `GROQ_M1_API_KEY` and `GROQ_ORCHESTRATOR_API_KEY` are absent. Thus the M1 provider falls back to the generic key and the orchestrator skips Groq entirely; effective key separation is not present. `NEO4J_*` and S3/Resend fields are absent/empty in the inspected environment. No secret values are included in this report.

## 20. Test and validation status

Automated backend run (offline, `DEBUG=false`, M1 mock, live external tests disabled, no network socket): **372 passed, 17 skipped, 0 failed**. The skipped tests are the opt-in real Gemini (6), real Groq (4), real Ollama (3), live Ollama orchestrator (3), and live Neo4j (1) cases. Unit coverage spans M1 providers, classifier, context, KG, transcript, sessions, Agora service/token code, registry, adapter and orchestrator.

An initial run inherited shell `DEBUG=release` and failed collection in 23 modules because Pydantic could not parse that value as a boolean. This was an invocation environment error; rerunning with a process-only `DEBUG=false` override passed. With an orchestrator placeholder key and no network, all 372 tests passed. With the key absent, four existing cross-agent routing tests fail because their fixtures patch `call_groq` but the graph correctly routes around the absent key; these are test/config coupling failures, not live-service results.

Frontend checks:

- `tsc --noEmit --incremental false`: passed.
- `npm run build`: passed in a temporary copy with network access for `next/font` (18 routes generated). It emitted a warning that Next’s `middleware` convention is deprecated in favor of `proxy`.
- First build attempt in the sandbox failed only because Google Fonts could not be fetched; source files were unchanged.
- `npm run lint -- --no-cache`: failed with **37 errors and 59 warnings**, including many `no-explicit-any` errors in interview/prep/portal/admin files, a React set-state-in-effect error in public apply, and unused imports.
- `docker compose config --quiet`: passed with a warning that the `version` attribute is obsolete.
- No Docker image build, container startup, database migration, live Postgres/PostgREST, live Redis, live Agora, live Groq, live Neo4j, S3, Resend or browser RTC smoke test was run.

## 21. Lightweight security review

Evidence-supported findings:

- `GET /auth/me`, sessions, token generation, transcript ingestion and Agora agent start/stop are public routes. Opaque IDs provide some obscurity but no authorization or candidate ownership check.
- Signup accepts the requested `role`, so a public caller can request `admin` unless deployment adds an external restriction.
- Middleware trusts an unsigned decoded JWT payload for UI redirects; backend protected routes do verify signatures, so this is a UI guard weakness rather than backend signature bypass.
- No tenant scoping or RLS is implemented despite `tenant_id` columns and broad SQL grants. Repository queries key only by IDs.
- Agora webhook routes do not verify notification signatures or authenticate senders.
- `RequestLoggingMiddleware` logs method/path/status and request IDs, while Custom LLM logs selected headers including `authorization` in the filtered header set. It does not log the token value deliberately, but authorization metadata is still admitted to structured logging code.
- `TranscriptService` has a synthetic `test-room-101` fallback for malformed/no-identity payloads, creating an attribution risk.
- `CandidateProfileProvider` and job providers treat CV/JD text as data in prompt serialization and context delimiters are present; the boundary is a design strength, but no adversarial prompt test was run.
- Neo4j writes use parameter values and validated static labels/relationship types; no direct unsafe Cypher interpolation was found in ordinary entity writes. The graph-depth interpolation is bounded by `_validate_depth(1..3)`.
- Candidate list search uses Supabase query builders; no raw SQL string concatenation was found in repositories. Arbitrary resume URL download in `ResumeService._download_resume_text()` is accepted from stored data and has no SSRF allowlist; this is a code-level risk if untrusted URLs can be stored.
- CORS allows configured frontend plus localhost:3000 with credentials and all methods/headers. Production origin configuration is therefore important.
- Seed SQL includes a known development password hash and a fixed development JWT secret in Compose. These are not live values in this report, but must not be used beyond local development.

## 22. Performance and latency

The realtime path is sequential: Agora/ASR request → Custom LLM parsing/classification → optional M1 network call → context update/provider lookups → optional orchestrator Groq call → context transition → KG persistence → first SSE token → Agora TTS. M1 and orchestrator each have configurable 20-second Groq timeouts; M1 may be mock/Gemini/Ollama/OpenAI. The adapter logs M1, orchestrator, TTFT and total durations but no benchmark was run against live services.

`AgentTurnContextBuilder` performs candidate/JD provider calls and KG memory reads in worker threads. KG persistence also runs in a worker thread, but the default adapter awaits it before returning the response, adding graph I/O to voice latency. The optional background task avoids waiting but is not durable and can be lost on crash. SSE is word-sliced only after all reasoning completes, so it does not stream LLM tokens or overlap M1/orchestration. Per-session asyncio locks serialize turns within one process; multiple workers have no shared lock.

## 23. Current end-to-end matrix

| Capability | Status | Evidence | Blocker |
|---|---|---|---|
| Recruiter creates job | PARTIAL | `JobService.create_job`, `/admin/jobs/new` | JD parse route absent; `job_rounds` not inserted. |
| Candidate applies | PARTIAL | Multipart route/client and S3 upload code | S3 unconfigured; parsing/eligibility/notification not chained. |
| Recruiter schedules interview | IMPLEMENTED in code | Slots + booking + scheduled interview repo rows | Runtime DB unverified; placeholder room token. |
| Candidate opens interview | IMPLEMENTED in code | Prep page + `/sessions/{id}` | Process-local session, public opaque token. |
| Agora voice connection | UNVERIFIED/PARTIAL | RTC SDK, token builder and v2 join service | No live Agora validation/config proof. |
| STT | UNVERIFIED | Deepgram configured in Agora mappings | Depends on Agent Studio pipeline. |
| Candidate answer reaches backend | PARTIAL | Custom LLM and RTM transcript-event routes | Agora payload/identity behavior unverified; transcript is in memory. |
| M1 analysis | IMPLEMENTED with mock; LIVE UNVERIFIED | `M1InterviewAnalyzer`, providers, tests | Current env needs Groq; no live call. |
| Orchestrator routing | IMPLEMENTED deterministic; Groq UNVERIFIED | LangGraph and 53+ unit tests | Orchestrator key absent; mocked test coupling. |
| Follow-up question | IMPLEMENTED in adapter/policies | `NextAction.ASK_QUESTION` and fallbacks | Voice/TTS delivery unverified. |
| Difficulty adaptation | IMPLEMENTED logic | `calculate_adaptive_difficulty`, bounds tests | Not persisted to ATS report; live behavior unverified. |
| Agent switch (logical) | IMPLEMENTED | Context switch, handoff prompt, RTM UI | No physical Agora start/stop handoff. |
| Persistent memory | IMPLEMENTED abstraction; disabled current env | KG service/repositories/memory service | Neo4j unconfigured; no live test; non-durable background option. |
| Cross-agent handoff | PARTIAL | Handoff context and Jordan grounding | Real target agent not started; candidate/JD providers fallback by default. |
| Interview completion | PARTIAL | `/sessions/{id}/stop`, legacy `/interviews/{id}/end` | Does not update all stores or trigger evaluation/report. |
| Report generation | IMPLEMENTED legacy path | Evaluation + ReportService | Does not consume M1/KG; OpenAI/S3/PDF unverified. |
| Recruiter viewing report | PARTIAL | Admin report pages and interview-scoped API | List/detail API mismatch; PDF absent. |

## 24. Known gaps and blockers

### P0 — blocks a core demo/product path

1. Validate a real Agora candidate→agent→ASR→Custom LLM→TTS conversation and confirm the exact headers/query/session identity sent by Agent Studio.
2. Implement physical agent handoff: start the target pipeline/agent, stop or mute the source, update started-agent state, and verify one-speaker behavior.
3. Replace process-local session/context/transcript state with shared durable state or explicitly constrain deployment to one worker and add recovery semantics.
4. Align the frontend contracts: `/auth/me`, `/jobs/parse-jd`, `/applications/{id}/invite`, `/candidates/me/applications`, `/reports` list/detail, and admin job GET.
5. Ensure candidate identity from scheduled/application data reaches `InterviewAIContext`; remove synthetic candidate IDs from the normal start path.
6. Decide and validate the production M1/orchestrator credential model. Current environment does not effectively separate M1 and orchestrator keys.

### P1 — major incomplete functionality

1. Wire application submission to resume parsing, eligibility scoring, status transitions and notifications.
2. Persist `job_rounds` when jobs are created/updated and reconcile round schema fields.
3. Connect Custom LLM/M1/KG outputs to report generation and recruiter report UI.
4. Implement real report PDF generation/storage and candidate report retrieval.
5. Add candidate/session ownership authorization and tenant scoping/RLS.
6. Add durable transcript persistence, webhook authentication, retries and idempotent background KG writes.
7. Wire repository-backed candidate/JD providers into the live context builder.

### P2 — important but non-blocking

1. Fix frontend lint errors/warnings and replace broad `any` types in Agora/RTM code.
2. Remove static/mock candidate completion/report content and replace with query states.
3. Add live-service CI jobs gated by explicit credentials and a browser smoke test.
4. Add route contract tests generated from backend OpenAPI/client definitions.
5. Add PDF/report list pagination and notification persistence/worker behavior.

### P3 — cleanup/future

1. Replace deprecated Next middleware convention and obsolete Compose `version` field.
2. Remove unused frontend imports and legacy OpenAI question/evaluation paths after a deliberate migration.
3. Add decision-log/cost/latency persistence if operational analytics are required.
4. Expand frontend agent selection beyond Alex/Jordan when a third agent is introduced.

## 25. Technical debt

- There are two interview state models/stores: `InterviewSession`/`SessionStore` for meeting state and `InterviewAIContext`/`InterviewSessionStore` for cognition, with alias synchronization but no durable shared source.
- There are two evaluation architectures: legacy Postgres/OpenAI `EvaluationService` and new M1/KG/orchestrator analysis. Reports still use the former.
- There are two Agora configuration payload paths (`routes/interviews.py:get_agora_agent_config` and `AgoraAgentService` v2 join) with overlapping token/config responsibilities.
- `room_token` is a UUID placeholder alongside real Agora tokens; naming can mislead callers into treating it as a join credential.
- Several frontend API comments mark endpoints as “P4” or existing while the corresponding backend route is absent, creating documentation drift.
- Services `ResumeService`, `EligibilityService`, `NotificationService`, Redis wrapper and report PDF/S3 helpers exist but are not connected to the main workflow.
- In-memory default context providers return generic “Software Engineering Role”/empty candidate data in live turns unless explicitly injected.
- `JobService._to_response` and candidate route handlers mutate repository result dictionaries with `pop`, making reuse of response rows fragile.
- Legacy routes `/interviews/{id}/start` and new `/sessions/{id}/start` can represent different lifecycle states for the same interview without reconciliation.
- Tests are strong for deterministic components but rely on patching/import-time settings and do not prove external contracts. Cross-agent tests are coupled to whether the orchestrator key is nonempty.
- Compose config mixes `backend/.env` with environment overrides and hard-coded development defaults; provider behavior can differ between shell, local and container runs.

## 26. What is safe to change

### SAFE

Pure presentation components, landing-page copy/styles, typed UI loading/error states, isolated frontend query hooks after contract alignment, deterministic classifier rules, prompt wording with contract tests, in-memory repository test fixtures, and documentation. ATS read-only UI changes are generally independent of the voice path if they preserve API types.

### CAUTION

`routes/sessions.py`, session models/stores, transcript normalization, `AgentTurnContextBuilder`, context serialization limits, Agent Registry mappings, environment defaults, database schema, and report/evaluation adapters. These are shared seams between ATS, candidate UI, Agora and the cognitive engine.

### PROTECTED / HIGH RISK

The Custom LLM wire contract (`ChatCompletionRequest/Response`, SSE framing and identity headers), session ID/alias resolution, active-agent guard, M1 `AnswerAnalysis` schema, `NextAction` schema and LangGraph validation, Agora token construction, Agent Studio join payload, transcript event IDs/deduplication, and KG provenance/relationship contracts. Changes here can cause silent duplicate speech, cross-session contamination, invalid TTS, lost evidence or broken agent handoffs.

## 27. Recommended implementation sequence

1. **Create a route contract inventory and fix missing frontend APIs.** Affected: `backend/app/routes/{auth,jobs,applications,candidates,reports}.py`, corresponding `frontend/src/lib/api/**`, hooks and pages. Dependency: none. Acceptance: every client call has a mounted route, matching method/schema/auth, with contract tests. Risk: changing public paths can break existing links.
2. **Fix ATS persistence invariants.** Affected: `JobService`, `ResumeService`, `docker/init-db/01-init.sql`, repositories/schemas. Dependency: contract inventory. Acceptance: job rounds and parsed resume rows satisfy schema, and a fresh local Postgres seed plus CRUD smoke passes. Risk: existing seeded volumes need controlled migration planning.
3. **Wire application processing.** Affected: `ApplicationService`, resume/eligibility/notification services, background worker choice, UI status handling. Dependency: storage/provider configuration. Acceptance: apply → parse → eligibility → shortlist/reject → notification works with mocked providers and failure retries. Risk: uploads and status transitions are user-visible.
4. **Unify candidate/session identity.** Affected: session service/store, context store, `AgentTurnContextBuilder`, candidate prep/room. Dependency: scheduling/application IDs. Acceptance: a scheduled candidate’s real ID, job ID and interview ID survive create/start/Custom LLM/transcript/KG writes; no synthetic fallback in the normal path. Risk: changing aliases can invalidate existing links.
5. **Run a mocked full cognitive turn test.** Affected: adapter, M1, orchestrator, transcript and KG test fixtures. Dependency: identity. Acceptance: candidate answer produces M1 analysis, validated `NextAction`, transcript event and KG persistence with provenance; fast-path controls do not mutate state. Risk: test assumptions around async locks/background tasks.
6. **Validate live Groq separately for M1 and orchestrator.** Affected: environment/CI only plus provider tests. Dependency: key separation. Acceptance: live M1 JSON validates `AnswerAnalysis`; live orchestrator JSON validates `NextAction` routing; latency logs captured without secrets. Risk: rate limits/cost and prompt drift.
7. **Validate live Neo4j and persistence failure modes.** Affected: Neo4j repository/schema/service, integration tests. Dependency: credentials and step 5. Acceptance: schema initialization, upserts, candidate filters, restart/retry behavior and disabled-provider behavior are proven. Risk: graph writes are durable external mutations; use isolated test IDs.
8. **Implement physical Agora handoff.** Affected: `AgoraAgentService`, session service, adapter metadata, frontend RTM/UI. Dependency: live Agora validation and routing. Acceptance: Alex→Jordan→Alex starts/stops the correct pipelines, produces one remote speaker, preserves identity and handoff context, and recovers from failed start. Risk: highest voice-path regression risk; preserve wire contracts.
9. **Connect completion/reporting to new outputs.** Affected: transcript/KG query, report service/schemas/routes, admin/candidate report pages and PDF service. Dependency: durable transcript/KG and end-session semantics. Acceptance: completed voice interview produces a report containing M1 evidence/rationales, recruiter can view it, candidate page no longer uses mock data, PDF download is real. Risk: migration from legacy score scale and report schema.
10. **Add production hardening and validation.** Affected: auth/tenant/RLS, webhook signatures, URL allowlist, Redis/shared state, lint and Docker CI. Dependency: stable E2E. Acceptance: multi-worker/restart tests, authorization tests, browser smoke, lint clean, Docker build/start and provider health checks. Risk: deployment behavior changes; stage incrementally.

## 28. Final architecture verdict

Genuinely implemented: a coherent FastAPI/Next.js ATS prototype, JWT role checks, Postgres/Supabase repository layer, job/application/slot/interview/evaluation/report code, deterministic M1 contracts, a real LangGraph orchestration design, Alex/Jordan registry/personas, OpenAI-compatible Custom LLM/SSE framing, transcript normalization, and a parameterized Neo4j repository with strong offline tests.

Demo-ready with mocked/offline dependencies: ATS screens that use the existing job/candidate/slot/interview routes; deterministic Custom LLM turns; unit-tested M1/orchestrator/KG behavior; and the frontend production build. The browser interview UI is a plausible shell but not a validated live voice demo.

Production-like in isolation: typed provider boundaries, error/fallback logging, context budgeting, per-session locks, evidence provenance and graph relationship validation. Still prototype-grade as a product: process-local state, public opaque-token APIs, no tenant/RLS enforcement, unconnected services, missing route contracts, static candidate report UI, no physical agent handoff, and no live external-service evidence.

The architecture is sound at the conceptual boundary—Agora transport, Custom LLM, M1 analysis, orchestrator decision and persistent memory are separated—but the integration seams are incomplete. The current voice/interview engine contracts should not be casually changed: preserve `ChatCompletion*`, identity headers/session aliases, `AnswerAnalysis`, `NextAction`, transcript event IDs and Agora payload/token behavior while the missing persistence, authorization and live validation work is completed.

### Audit summary

- Files inspected: backend application, routes, services, repositories, schemas, integrations, agents, context, transcript, M1, orchestrator, KG, tests, Docker/SQL/env examples, and frontend app/pages/components/hooks/API/types/configuration.
- Major components inspected: ATS, auth/RBAC, sessions, Agora/RTC/RTM, Custom LLM, M1, orchestrator, registry/personas, context/memory, Neo4j, Postgres, Redis, reporting, frontend and deployment configuration.
- Tests actually run: backend offline suite (372 passed, 17 skipped); an initial environment-misconfigured collection run was separately observed; no live external tests.
- Build checks actually run: TypeScript passed; Next production build passed in a temporary copy; ESLint failed with 37 errors/59 warnings; `docker compose config --quiet` passed with an obsolete-version warning.
- Current failures: frontend lint; four orchestrator cross-agent tests when the orchestrator key is absent; missing frontend/backend route contracts; live integrations unverified.
- Current blockers: live Agora path and physical handoff, durable/shared interview state, route alignment, candidate identity propagation, M1/orchestrator key separation, and report integration.
- Files modified: only this report, `docs/INTRA_AI_CODEBASE_STATUS.md`.
- Confirmation: no source code, configuration, database, migration, test, documentation or frontend file was changed other than creating this requested status report.
- Confirmation: no merge, migration, commit, staging, reset, checkout, cherry-pick, dependency installation or deletion was performed.

## 29. Implementation pass update — 2026-09-05

The baseline audit above was followed by an implementation pass in the same
working tree. The following contracts and workflow seams are now implemented:

- Added JD parsing (`POST /api/v1/jobs/parse-jd`), recruiter job detail, auth
  identity (`GET /api/v1/auth/me`), candidate self-service applications, invite
  transition, and report list/detail routes.
- Job creation and updates now persist `job_rounds`; resume parsing and
  eligibility writes match the deployed Supabase columns and tolerate optional
  S3 storage.
- Resume parsing uses Groq GPT-OSS-20B with strict normalization and a local
  deterministic fallback. M1 and orchestrator keys are separate settings.
- Session start now creates cognitive context with the canonical candidate ID,
  returns credentials on idempotent starts, and fails retryably when Agora does
  not start the initial agent.
- `SWITCH_AGENT` performs a real target-agent Agora start followed by source
  leave when a live platform session exists, while retaining N-agent registry
  routing and handoff context.
- Neo4j nested metadata is serialized safely for Aura properties and decoded on
  reads. Live M1 evidence is persisted with Candidate/Round/Question/Answer/
  Evidence provenance and relationships.
- Reports can be generated from accumulated live context evidence. Session stop
  attempts report generation and returns `report_status=ready` or `pending`;
  legacy evaluation reports remain supported. Candidate report pages and the
  completion page now load real report data instead of mock content.

Validation after implementation:

- Backend: `372 passed, 17 skipped, 3 warnings` using the deterministic test
  provider suite; Python bytecode compilation passed.
- Frontend: `npx tsc --noEmit --incremental false` passed; `npm run build`
  passed and emitted all application routes.
- Live Groq: `/models`, M1 GPT-OSS-20B structured analysis, and live
  Meta-Orchestrator GPT-OSS-20B `NextAction` validation passed.
- Live Supabase: authenticated REST reads and isolated application → Groq
  resume parse → eligibility persistence passed; cleanup completed.
- Live Neo4j Aura: connectivity, isolated graph write/readback, nested metadata
  serialization, and cleanup passed.
- Live Agora: isolated v2 agent join/leave and a full session start → Custom LLM
  opening/answer → M1 → orchestrator → Neo4j → stop path passed. The connected
  test retained the canonical candidate ID and persisted six evidence items.
- Physical handoff: isolated Alex/Jordan start-stop switching passed with the
  configured N-agent session service. Browser microphone/remote-audio media and
  Agora ASR/TTS audio were not exercised by an RTC browser client in this run.
- Docker: `docker compose config --quiet` passed; Compose reports only the
  existing obsolete `version` field warning.

Remaining product hardening: process-local session/context/transcript state is
not yet shared across workers or restarts; webhook signatures, tenant/RLS
authorization, durable transcript storage, PDF rendering/storage, notification
workers, and a browser-level live RTC voice test remain. Frontend ESLint still
reports repository-wide pre-existing issues (37 errors, 56 warnings); the
TypeScript check and production build are clean. AWS deployment remains paused.

## 30. Black-box QA corrective pass — 2026-09-05

The principal QA pass is documented in
[`docs/INTRA_AI_BLACK_BOX_TEST_REPORT.md`](INTRA_AI_BLACK_BOX_TEST_REPORT.md).
It exercised the current source server and the rebuilt Docker stack against the
supplied Supabase, Groq, Neo4j Aura and Agora configuration before applying
fixes. Public privileged signup now returns a structured 403, duplicate
candidate/job applications return a 409, protected routes return a 401 Bearer
challenge, `/api/v1/ready` is available, and Compose uses the configured remote
Supabase project instead of an incompatible local PostgREST JWT. Explicit KG
disable is safe, manual shortlist is idempotent after automatic eligibility,
empty sessions do not create empty reports, and cross-agent ownership prevents
an LLM route from keeping a persona on competencies it does not own.

The final rebuilt-stack E2E completed recruiter → JD parse → job → application
→ eligibility → shortlist/invite → schedule → session → Agora agent start →
Custom LLM/M1/orchestrator turn → Neo4j evidence → completion/report. Backend
regression is 376 passed and 13 opt-in skips; frontend TypeScript and Next
production build pass. Remaining gaps are process-local state, PDF/HR/MCP/
notifications, the remote Supabase DDL migration for the application uniqueness
index, and a browser-level media/ASR/TTS proof. AWS is still paused and was not
touched.
