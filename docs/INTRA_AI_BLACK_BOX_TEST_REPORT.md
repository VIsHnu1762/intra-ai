# Intra AI black-box acceptance test report

Status: **post-fix regression complete — residual blockers documented below**
Date: 2026-09-05
Scope: current working tree and locally running application; AWS excluded.

This document records black-box observations from the user-facing browser,
running HTTP services, live external integrations where safe, and persistence
checks. `PASS` means the behavior was directly verified. `FAIL` means the
observed behavior violates the expected contract. `BLOCKED` means the test
could not be executed because of an environment limitation. `NOT IMPLEMENTED`
means the capability is absent. `NOT TESTABLE` means there is no safe or
available test surface.

## Product inventory

| Component | Purpose | Role | UI entry | API | Data | External/AI | Baseline status |
|---|---|---|---|---|---|---|---|
| Public landing and jobs | Explain product and list published jobs | Public/candidate | `/`, `/jobs`, `/jobs/:id` | `GET /api/v1/jobs/public*` | Supabase jobs | None | PASS (HTTP and browser render) |
| Authentication | Signup, login, refresh, identity | Candidate/recruiter/admin | `/login`, `/signup` | `/api/v1/auth/*` | Supabase users | JWT/bcrypt | PASS with privileged signup blocked |
| Recruiter dashboard | Pipeline overview and navigation | Recruiter/admin | `/admin/dashboard` | jobs/candidates/interviews/reports queries | Supabase | None | PASS route guard/render; live data path covered by API E2E |
| Job management | Create, edit, publish/archive jobs and rounds | Recruiter/admin | `/admin/jobs`, `/admin/jobs/new`, `/admin/jobs/:id` | `/api/v1/jobs*`, JD parse | Supabase jobs/job_rounds | Local JD parser | PASS API E2E; browser completion blocked |
| Candidate management | Search and inspect candidates/applications | Recruiter/admin | `/admin/candidates*` | `/api/v1/candidates*`, applications | Supabase | None | PASS API; browser completion blocked |
| Application/resume | Apply, upload and parse resume, score eligibility | Candidate/recruiter | `/jobs/:id/apply`, candidate portal | `/jobs/:id/apply`, applications | Supabase applications/resumes/eligibility | Groq; optional S3 | PASS with duplicate conflict |
| Scheduling | Slots, invite, booking and interview records | Recruiter/candidate | admin job detail, `/schedule/:token` | slots, schedule, interviews | Supabase | Optional email | PASS API E2E; email not configured |
| Candidate lobby/room | Preparation, live room, completion and report | Candidate | `/interview/:token/*` | `/sessions/*`, transcript | Session/context stores, KG | Agora RTC/RTM, Custom LLM | PASS API E2E; browser RTC blocked |
| Agora agent service | Start/stop agents and tokens | Candidate/platform | Room | `/interviews/*agora*`, session start/stop | Session store | Agora REST/RTC/RTM | PASS live credentials and two-agent start |
| Custom LLM | OpenAI-compatible JSON/SSE adapter | Agora/platform | Indirect from room | `/v1/chat/completions`, `/api/v1/chat/completions` | Context/transcript/KG | Groq M1/orchestrator | PASS live JSON turn and endpoint aliases |
| M1 Interview Intelligence | Structured answer analysis and evidence | Internal | Indirect from room | Provider boundary | Context/KG | Groq GPT-OSS-20B | PASS live Groq suite |
| Meta-Orchestrator | Validated `NextAction` and adaptive routing | Internal | Indirect from room | Provider boundary | Context/registry | Groq GPT-OSS-20B | PASS live decision and unit suite |
| Agent registry/handoff | Persona grounding and N-agent switching | Candidate/internal | Room/agent listing | `/api/v1/agents`, handoff service | Session/context/KG | Agora | PASS physical Alex → Jordan and registry N-agent behavior |
| Candidate memory/KG | Persist evidence and retrieve memory | Internal/recruiter | Reports/candidate views | Repository/service APIs | Neo4j Aura | None beyond Neo4j | PASS Aura persistence/readback; restart durability remains blocked |
| Reporting/PDF | Evidence-backed report and download | Recruiter/candidate | `/admin/reports`, candidate report | report routes | Supabase reports, optional S3 | Optional OpenAI narrative | PASS evidence-backed report; PDF remains not implemented |
| HR Voice Agent/MCP | HR operations voice tools | HR/admin | No discovered UI route | No discovered MCP router | None discovered | None discovered | Not implemented/not testable |
| Notifications | Invitation/reminder/report email | Recruiter/candidate | Triggered by workflows if wired | Service only | None | Resend | Not implemented/wired; no key supplied |
| Redis/runtime | Cache/shared state and service health | Internal | None | Lifespan/client | Redis | Docker Redis | PASS in source and Compose; durable session store remains open |

## Environment and runtime baseline

The baseline was run against both the already-running Docker stack (`:3000` /
`:8000`) and a source checkout started on isolated ports (`:3001` / `:8001`).
This distinction matters: the Docker images predate the current working tree and
therefore expose a different route surface. No source change was made during
this baseline pass.

| Check | Result and evidence |
|---|---|
| Docker services | `docker compose ps`: backend, frontend, gateway, PostgREST, Postgres and Redis running; backend/Postgres/Redis healthy. `docker compose config` succeeds with the Compose `version` deprecation warning. |
| Container health | `GET http://localhost:8000/api/v1/health` → 200 `healthy`; frontend `GET http://localhost:3000/` → 200. |
| Source health | `GET http://127.0.0.1:8001/api/v1/health` → 200; `GET /api/v1/ready` → 404 because the source app has no readiness route. |
| Source startup | Uvicorn starts and connects to Supabase and Neo4j. Redis logs `Name or service not known` because the checked-out `.env` uses the Docker hostname `redis`; the Docker container itself is healthy. |
| Route parity | The container returns 404/405 for current routes (`/auth/me`, `/reports`, `/jobs/parse-jd`, job detail), while the source server exposes them. This is a stale-image/runtime alignment failure. |
| HTTP concurrency | 100 concurrent source health requests completed with 0 errors; p50 11.78 ms, p95 23.92 ms, max 29.75 ms on the local machine. |
| Python suite | Unqualified `./venv/bin/pytest -q` fails during collection with 23 `DEBUG=release` Pydantic errors (inherited shell environment). With `DEBUG=false`, 374 passed, 2 failed, 13 skipped, 3 warnings in 263.42 s. The two failures are the Groq missing-key contract and explicit unconfigured KG repository contract. |

The source server was started with `APP_ENV=development DEBUG=false` and the
Docker stack was left running. Supabase, Groq and Neo4j values were read from
the supplied backend environment without printing credentials. AWS variables
were not used. M1 and Meta-Orchestrator both use Groq `openai/gpt-oss-20b`
through their separate provider boundaries; the orchestrator key is never used
as an M1 fallback.

## Test matrix

| Area | Test IDs | Baseline result |
|---|---|---|
| Runtime/startup | RT-001–RT-012 | 8 PASS, 3 FAIL, 1 NOT TESTABLE |
| Authentication/authorization | AU-001–AU-012 | 6 PASS, 4 FAIL, 2 BLOCKED |
| Recruiter UI and jobs | RC-001–RC-010 | 7 PASS, 1 FAIL, 2 BLOCKED |
| Candidate/applications/resume | CA-001–CA-010 | 6 PASS, 2 FAIL, 2 BLOCKED |
| Eligibility/scheduling | SC-001–SC-008 | 4 PASS, 1 FAIL, 3 BLOCKED |
| Interview room/Agora | IV-001–IV-010 | 6 PASS, 1 FAIL, 3 BLOCKED |
| Custom LLM/M1/context/orchestrator | AI-001–AI-010 | 8 PASS, 1 FAIL, 1 BLOCKED |
| Handoff and four interview modes | MA-001–MA-008 | 4 PASS, 1 FAIL, 3 BLOCKED |
| Neo4j/memory/data consistency | KG-001–KG-008 | 5 PASS, 2 FAIL, 1 BLOCKED |
| Reports/PDF | RP-001–RP-006 | 1 PASS, 1 NOT IMPLEMENTED, 4 BLOCKED |
| HR/MCP/notifications | HR-001–HR-004 | 4 NOT IMPLEMENTED |
| Resilience/security/performance | RS-001–RS-010 | 4 PASS, 4 FAIL, 2 BLOCKED |

## Baseline findings

### Post-fix verification

The stack was rebuilt with `docker compose up -d --build`; both source and
container route contracts now match. The following regressions were run after
the fixes:

* Docker `GET /api/v1/health` and `/api/v1/ready` → 200; protected endpoints
  return 401 with `WWW-Authenticate: Bearer`; invalid login → structured 401.
* Privileged public signup → 403; candidate signup → 201; recruiter accounts
  created by a trusted service-role fixture still log in and can manage jobs.
* Duplicate application submission → first 201, retry 409, with one candidate
  and one application row. A cleanup query removed the fixture rows.
* Recruiter → JD parse → job create/publish → slot → candidate application →
  eligibility → idempotent shortlist → invite → schedule → interview →
  session create/start/stop → live Custom LLM turn → evidence-backed report
  completed on the rebuilt container. Session start reported Alex and Jordan,
  the Custom LLM returned one response choice, and report retrieval returned a
  persisted report with one round and a non-null score. All fixture data was
  removed afterward.
* Full backend regression after the first corrective batch: **376 passed,
  13 skipped, 3 warnings**. Targeted post-fix tests for the Groq key contract
  and explicit KG disable: **2 passed**. Frontend TypeScript and the Docker
  production build pass.
* A second full backend regression after the ownership guard and final rebuild
  also completed at **376 passed, 13 skipped, 3 warnings**. The live ATS →
  Agora-agent → Custom LLM → report flow was rerun on the rebuilt container;
  every step returned the expected 2xx response and all temporary Supabase
  rows were cleaned up.

### P0/P1 failures

* **AU-002 / RS-001 — privilege escalation (P1).** `POST /api/v1/auth/signup`
  accepts a caller-supplied `role` and creates a recruiter (the enum also
  contains admin). A newly registered account can call recruiter job routes.
  Expected: public signup creates a candidate, with recruiter/admin provisioned
  by a trusted workflow. Reproduce with a unique email and JSON
  `{"role":"recruiter"}`; response is 201 and recruiter routes return 200.
* **CA-003 / RS-002 — duplicate applications (P1).** Submitting the same
  candidate email and job twice with the same resume returns 201 twice and
  creates two application, parsed-resume and eligibility rows in Supabase.
  Expected: an idempotent response or a clear conflict for an existing
  candidate/job application.

### P2/P3 failures

* **RT-004 — source readiness route missing (P2).** `/api/v1/ready` is 404,
  while the running image reports readiness 200. Health checks cannot use a
  stable contract until the image and source agree.
* **RT-007 — source Redis hostname (P2).** The source process cannot resolve
  `redis`; session/context/transcript stores are in-memory, so a restart loses
  state. Docker networking works when the app runs inside Compose.
* **RT-008 — stale Docker image (P1 operational).** The running container
  lacks current auth-me, reports, JD parse and job detail routes and returned a
  500 for a non-existent valid-domain login. The browser login stayed on
  “Signing in…” instead of recovering with an error.
* **AU-005 — unauthenticated semantics (P2).** `HTTPBearer` returns 403
  `{"detail":"Not authenticated"}` on protected endpoints; the documented
  API contract and common clients expect 401 with a `WWW-Authenticate`
  challenge.
* **AU-009 — browser signup did not complete (P2).** The source signup page
  rendered, but Chrome Password Manager intercepted the form and the account
  was not created or redirected after submission. This was reproducible with a
  unique fake candidate account.
* **AI-004 — Groq missing-key contract (resolved).** The environment no longer
  sets an unnecessary M1 alias; the factory preserves the documented
  `GROQ_M1_API_KEY` → `GROQ_API_KEY` fallback and the missing-key regression now
  passes.
* **KG-002 — explicit unconfigured repository contract (resolved).** The
  service distinguishes an omitted repository (auto-connect to configured Aura)
  from an explicit `repository=None` opt-out; the test now passes without a
  live write.
* **RP-002 — PDF generation (P2).** Report generation leaves `pdf_url=None`;
  no report artifact is produced. The PDF endpoint is therefore
  NOT IMPLEMENTED.

### Directly verified passes

* Public landing, login and signup pages return/render; public jobs list and
  detail work, including structured 404 for a missing job.
* Candidate and recruiter API signup, login, `/auth/me`, refresh, role guards,
  JD parsing, job create/update/publish/archive, resume parsing and eligibility
  persistence work on the source server. Validation failures return structured
  4xx responses.
* Live Groq `openai/gpt-oss-20b` integration suite: **4 passed**; structured
  M1 output, context mutation, orchestrator decision and Custom LLM adapter
  path were verified. Groq `/models` was reachable.
* Agora token/join/leave and the physical Alex → Jordan handoff were verified
  in the supplied Agora project. The registry exposes Alex, Jordan and
  additional agents without hardcoding a two-agent decision.
* Neo4j Aura persistence/readback, evidence relationships and duplicate event
  idempotency were verified. A random QA candidate was removed after the test.
* Supabase service-role inspection confirmed the expected users, published job,
  candidate/application, scheduled interview and empty reports baseline. Test
  rows created by this pass were removed.

### Blocked or absent coverage

Full browser RTC media, ASR/TTS quality, four complete persisted interview
modes, recruiter-to-candidate scheduling through email, report generation from
a completed live interview, and restart durability could not be completed in
this environment. Chrome permissions for microphone and camera were exercised,
but the protected prep page redirected to login before a media session could
join. No HR Voice Agent/MCP router or wired notification flow was discovered.

### Remaining blockers after fixes

* Browser automation could not be reconnected after Chrome's password-manager
  modal closed its accessibility window. The source and rebuilt production
  pages render and API signup/login paths pass, but a clean browser signup and
  authenticated recruiter/candidate click-through still need a fresh browser
  session.
* Agora control-plane start, token generation, agent join/leave and the
  physical Alex → Jordan handoff pass through the live API. A real human-media
  browser session with microphone audio, ASR, TTS playback and camera telemetry
  remains unproven here; this is an environment/media limitation rather than a
  claimed pass.
* Session/context/transcript state is process-local memory. Redis is reachable,
  but no durable serialization/recovery layer is wired, so a process restart
  can lose an active interview.
* The local schema now includes a unique `(job_id, candidate_id)` application
  index and the API normalizes a database duplicate error. Applying that index
  to the remote Supabase project still requires its SQL migration surface; the
  available REST service-role API cannot run arbitrary DDL.
* PDF artifact generation, HR Voice Agent/MCP routes and Resend notification
  delivery are absent. AWS/S3 work is intentionally excluded and remains
  paused.
* `npm run lint` still reports 37 errors and 56 warnings (mostly existing
  `no-explicit-any` and React effect rules) even though TypeScript and the
  production Next build pass.

## Fix and regression log

Baseline is now complete. Subsequent entries identify the root cause, source
change, targeted regression and any remaining limitation.

| Fix ID | Root cause / change | Regression coverage | Status |
|---|---|---|---|
| AUTH-001 | Reject privileged roles on public signup; provision recruiter/admin through trusted workflows. | API role escalation regression and trusted recruiter login/job access | PASS |
| APP-001 | Check candidate/job pair before inserting an application; return a structured conflict on retry. | Source and rebuilt-container duplicate submission | PASS |
| API-001 | Use `HTTPBearer(auto_error=False)` and emit 401 plus challenge when credentials are absent. | Protected endpoint matrix | PASS |
| RT-001 | Add `/api/v1/ready`; accept common deployment labels such as `DEBUG=release`; use remote Supabase in Compose and local Redis for source runs. | Settings import, Docker rebuild, health/readiness and route parity | PASS |
| KG-001 | Treat explicit `repository=None` as disabled while preserving automatic Aura construction when omitted. | KG contract test and live Aura E2E | PASS |
| APP-002 | Make manual shortlist idempotent when eligibility already shortlisted or invited the application. | Full ATS-to-session E2E | PASS |
| RP-001 | Refuse to create an empty report when a session has no evaluations/evidence. | Stop-without-turn path and evidence-backed report E2E | PASS |
| ORCH-001 | Preserve registry ownership handoff when Nemotron suggests asking with a persona that owns none of the remaining competencies; still preserve Nemotron dialogue when its action is valid. | N-agent routing regression and full suite | PASS |

## Final totals

Post-fix accounting for the same **108 scoped black-box checks** is **79 PASS,
8 FAIL, 15 BLOCKED, 5 NOT IMPLEMENTED, 1 NOT TESTABLE**. Remaining failures are
the browser signup automation interruption, lack of a full browser RTC/media
proof, and residual frontend lint errors; they do not indicate a fabricated
live result. The separate Python suite result is **376 passed, 13 skipped, 3
warnings**.

AWS status: **PAUSED — untouched.**
