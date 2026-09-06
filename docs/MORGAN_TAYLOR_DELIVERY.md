# Taylor and Morgan: initial integration delivery record

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

Date: 6 September 2026. Branch: `final`. Changes are in the working tree; this task did not commit or push them.

**Historical record:** the initial delivery results below were recorded earlier on 6 September 2026 and are not the latest acceptance results. For current Morgan candidate actions, private recruiter access, templates, Composio integration and test counts, see [Morgan HR workflows](MORGAN_HR_WORKFLOWS.md). For the managed-mode fix and subsequent native bulk tests, see [Morgan tool continuation diagnosis](MORGAN_TOOL_CONTINUATION_DIAGNOSIS.md). Architecture notes below identify the relevant current changes; historical test counts remain labelled as such.

The isolated assistant integration is implemented. The initial control-plane verification below covers Agora startup, Morgan MCP tools, scheduling, confirmation, cancellation and cleanup. Taylor was subsequently changed to preload CV context and use native Agora conversation without MCP after a live context-fetch loop was observed. See [Taylor native practice delivery](TAYLOR_NATIVE_PRACTICE.md) for the current design and validation. AWS remains **PAUSED**.

## 1. Files created in the initial delivery

- `backend/app/voice/`: `__init__.py`, `agora.py`, `authorization.py`, `context.py`, `models.py`, `routes.py`, `security.py`, `service.py`, `store.py`, `tools.py`.
- `backend/tests/test_auxiliary_agora.py`, `test_voice_sessions.py`, `test_voice_mcp.py`, `test_voice_tools.py`.
- `frontend/src/app/(candidate)/training/page.tsx`.
- `frontend/src/components/voice/morgan-assistant.tsx`, `voice-assistant-panel.tsx`.
- `frontend/src/hooks/use-voice-assistant.ts`, `frontend/src/lib/api/voice-assistants.ts`, `frontend/src/lib/voice-assistant-state.ts`.
- `frontend/tests/voice-assistant-state.test.mjs` and this report.

Diagnostic scripts and sanitized evidence remain in ignored `tmp/voice-diagnostics/`.

## 2. Files modified in the initial delivery

`.gitignore`, `backend/.env.example`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/app/integrations/email_client.py`, `frontend/src/app/(candidate)/portal/page.tsx`, `frontend/src/components/layout/admin-layout.tsx`. The email adapter gains an explicit sender override. Local, ignored `backend/.env` contains the supplied new-project configuration.

`<workspace-root>/Morgan and Taylor.md` was read and preserved. No credential values were embedded in application source or this report. Official interview agent, Custom LLM, M1, Meta-Orchestrator, context, knowledge-graph and report implementations were not changed.

## 3. Initial environment variables

New server-side configuration:

```text
AGORA_TRAINING_HR_APP_ID
AGORA_TRAINING_HR_APP_CERTIFICATE
AGORA_TRAINING_HR_API_TOKEN
AGORA_TAYLOR_AGENT_ID
AGORA_TAYLOR_AGENT_RTC_UID
AGORA_MORGAN_AGENT_ID
AGORA_MORGAN_AGENT_RTC_UID
VOICE_ASSISTANT_PUBLIC_URL
VOICE_ASSISTANT_SESSION_SECONDS    default 1800
VOICE_ASSISTANT_IDLE_SECONDS       default 90
RESEND_FROM_EMAIL                  verified sender for Morgan email tools
```

The initial Resend email path also needed `RESEND_API_KEY`. Morgan subsequently gained the scoped Composio bridge and opt-in managed-mode configuration documented in [Morgan HR workflows](MORGAN_HR_WORKFLOWS.md); those newer settings are not enumerated in this historical list. No new frontend environment secrets are needed.

## 4. Agora configuration architecture

The immutable auxiliary project configuration has no fallback to the official project. Exact Taylor/Morgan pipeline IDs and agent UIDs come from the supplied configuration. Each session gets a unique channel and fresh, UID-bound RTC/RTM tokens. The server calls Agora's v2 join API; the browser receives only its short-lived connection credentials.

Initially both assistants inherited the saved Studio LLM, ASR and TTS configuration. Taylor still uses its saved native Studio model and explicitly disabled tools. Morgan's local deployment now opts into Agora-managed `gpt-4.1-mini`, matching its inspected Studio model label, and replaces inherited runtime `llm.params` before returning credentials. Morgan preserves saved Studio ASR/TTS and uses authorized MCP tools. Existing M1 and Meta remain `openai/gpt-oss-20b` on Groq. No independent LLM service, additional LLM key or Ollama integration was introduced. The documented default remains Studio mode; see the current Morgan report for the tested managed override and startup cleanup behavior.

Live testing found a real provider constraint: `remote_rtc_uids` must not exceed `2147483647`. Session generation and token validation now enforce this bound, with boundary and agent-UID collision regression tests.

## 5. Taylor architecture

[Candidate training](http://localhost:3000/training) offers general practice or a selected application, an optional target role, and an experience level. The server loads the authenticated candidate's own parsed CV and selected job once before Agora starts. CV selection is scoped to the selected application/job. Taylor has no live context-fetch tool or Custom LLM callback. Instructions request short, connected questions at the selected level.

Finish & Get Feedback stops browser audio, reads the running agent's native history, asks that same saved model for practice coaching, and then ends the cloud session. Validated feedback includes an indicative score, improvement areas and example answers grounded in the recorded answers. Insufficient evidence and provider failures yield no invented score. Practice transcripts, feedback and session state use a separate Redis namespace with a 24-hour record TTL. Taylor never invokes the official adaptive interview or evidence/report pipeline.

## 6. Morgan architecture

[Recruiter dashboard](http://localhost:3000/admin/dashboard) has a collapsible **Ask Morgan** panel. Authorized job, candidate or interview context follows the current dashboard route. Browser audio uses an isolated RTC/RTM lifecycle with microphone controls, transcript display, explicit join/subscription/playback states, autoplay recovery and cleanup.

Morgan uses Agora's native Streamable HTTP MCP connection to `/api/v1/voice/mcp`. It receives session-scoped backend tools, preloaded authorized page context and the retained Studio voice. The current local model configuration is the explicit Agora-managed mode described above, superseding the initial inherited Custom configuration.

## 7. Morgan tools in the initial delivery

Reads: `search_candidates`, `get_candidate`, `get_application`, `get_interview`, `get_report`, `find_available_slots`, `get_dashboard_context`, `get_action_status`.

Confirmed actions: `schedule_interview`, `reschedule_interview`, `cancel_interview`, `update_application_status`, `send_candidate_email`, `send_reminder_email`.

At the initial checkpoint, scheduling used existing saved Intra AI slots and email used Resend. The later implementation adds reusable templates, reviewed bulk shortlist/scheduling, scoped Gmail, Calendar and Slack tools. See the current workflow report for that expanded catalog and its validation limits; the list above is historical.

## 8. Authorization model

Every endpoint resolves the JWT subject against the persisted user. Candidate identity comes from the linked account. The current private-workspace rule requires job-creator ownership even when two recruiters share a tenant; tenant fields add consistency checks, not permission to access another recruiter's job. Admin status does not grant unrestricted cross-workspace access. Resource relationships must agree. This supersedes the initial tenant-sharing boundary.

Morgan MCP tokens have a separate audience and bind user, session, persona and expiry. Ordinary login tokens are rejected by MCP; MCP tokens cannot stand in for browser login tokens. Taylor receives no MCP credentials and is denied MCP access. Saved action previews/results recheck access to their original resources before being disclosed.

## 9. Confirmation model

Mutation tools create an immutable, five-minute proposal. The recruiter reviews the candidate, job, operation and slot/email details, then presses **Confirm Action**. The model has no confirmation tool; a spoken “yes” alone cannot execute a mutation.

Execution reauthorizes resources, detects changed review details, and uses a Redis one-time claim. Repeated confirmation retrieves the existing result. Uncertain provider outcomes are reported as unverified and are not blindly replayed. The panel displays actual backend results; Agora's saved voice can announce them.

## 10. Session lifecycle

States cover connecting, connected, executing, error and disconnected. Redis preserves isolated session and confirmation records across worker replacement. Sessions are capped at 30 minutes; server cleanup handles absent heartbeats, expiry and failed startup. Browser cleanup releases microphone, RTC/RTM clients, playback, polling and subscriptions. Empty Agora channels also have a provider idle timeout.

No API certificate, REST token, MCP bearer token or RTC token is stored in the session record. Safe logs record session IDs and lifecycle/tool stages without credentials or spoken CV content.

## 11. Initial integration tests executed

From `backend/`:

```sh
M1_PROVIDER=mock GROQ_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests -q
GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests/test_real_groq_integration.py -q
```

The second command used approved network access and the existing Groq key; environment overrides applied only to the test process.

From `frontend/`: `node --test tests/*.test.mjs`, `npx tsc --noEmit`, targeted ESLint, and production builds. `docker compose build backend frontend` and `git diff --check` were also run. Changed files were scanned against known credential values.

## 12. Historical initial test results

- Offline backend: **954 passed, 17 skipped**; existing dependency deprecation warnings.
- Live official Groq regression: **4 passed** in 101.59 seconds.
- Frontend: **20 passed**; TypeScript, targeted ESLint and production build passed.
- Final runtime: backend health and training page returned 200, unauthenticated assistant start returned 401, and zero auxiliary sessions remained active. Scanning 85 changed-source/browser-bundle files found no configured sensitive credential values.
- Initial sandboxed live Groq attempts failed with `ConnectError`; the approved-network rerun passed. An offline run with missing Groq keys but `M1_PROVIDER=groq` correctly failed configuration; the offline invocation above selects the mock provider explicitly.

Evidence: `morgan-taylor-backend-offline.log`, `morgan-taylor-live-groq-tests.log`, `morgan-taylor-frontend-tests.log`, and build logs under `tmp/voice-diagnostics/`.

These counts describe the initial checkpoint only. The latest CSV-compatible Morgan source passes **1,346 backend tests with 17 skipped and 3 warnings**, and **52 frontend tests**. Native lookup, confirmed two-candidate shortlisting and confirmed two-candidate template scheduling now pass; see the current reports for the separate live evidence and browser-voice limits.

## 13. Initial Taylor result (before native practice update)

Session `redacted-runtime-id-10` started with HTTP 201 in the new project and ended with HTTP 200 / `DISCONNECTED`. Agora performed MCP initialization and tool discovery during agent startup. A separate diagnostic HTTP client verified public MCP context retrieval, including CV skills/projects/education/experience and the selected job. Unauthenticated and ordinary-login-token MCP requests returned 401.

**Not verified:** browser RTC participation, microphone input reaching Taylor, audible greeting, or multi-turn conversation.

## 14. Historical initial Morgan lifecycle result

Session `redacted-runtime-id-11` started and ended successfully in the separate project. Agora MCP initialization/discovery and diagnostic public context requests succeeded; the correct Morgan tool set was exposed. Unauthorized MCP requests returned 401.

**Not verified:** browser audio or spoken command interpretation. Lifecycle evidence is in `morgan-taylor-live-summary.json` and `morgan-taylor-live-stages.log`.

## 15. Historical initial Morgan operation result

Real HTTP/MCP test session `redacted-runtime-id-12` used a new fictional candidate, draft QA job, application and future slot:

1. MCP scheduling proposal left zero interviews, a shortlisted application and a free slot.
2. Authenticated confirmation created exactly one matching scheduled interview and booked the slot.
3. Repeated confirmation returned that same interview without duplication.
4. Agora accepted the saved-voice announcement; this is not proof of generated or played audio.
5. MCP result retrieval succeeded; confirmed cancellation cancelled the interview, released the slot and returned the application to shortlisted.
6. The agent ended and every created database fixture row was deleted, with absence verified. No email was sent.

This was a **diagnostic HTTP/MCP operation, not a spoken browser E2E test**. Evidence: `morgan-scheduling-live-summary.json` and `morgan-scheduling-live.log`.

## 16. Initial Alex regression result

Official interview code and project configuration remain intact. The backend suite covers session greeting, clarification, repeat handling, context, evidence, reports and Agora behavior; live Groq tests passed M1 analysis and adapter/orchestration checks. No fresh Alex browser conversation was performed in this task.

## 17. Initial Jordan regression result

Official agent registry and handoff path remain intact; automated handoff/context tests passed within the backend suite. No fresh Jordan browser handoff or audible conversation was performed in this task.

## 18. Current validation limits and superseding reports

- Taylor was subsequently tested with the user's microphone: Agora recorded one greeting and seven completed voice-input/ASR/LLM/TTS turns without provider errors. See the current [Taylor delivery report](TAYLOR_NATIVE_PRACTICE.md) for feedback validation and audibility limits. Morgan's browser greeting, two spoken turns, mute/end cleanup, and a spoken proposal followed by panel confirmation remain unverified.
- The explicitly approved Gmail session-mapping repair and deployed `GMAIL_GET_PROFILE` check now pass. Email delivery, Slack-message writes and external Calendar-event creation have not been tested against real recipients. The Resend fallback still requires its own credential and verified sender.
- External Calendar export is now implemented as a separately reviewed action for a saved interview. It is not automatically performed by bulk scheduling and does not promise free/busy conflict detection.
- Native text-input lookup, a confirmed two-candidate shortlist and a confirmed two-candidate template schedule pass. The final CSV scheduling rerun used one search, one template lookup and one bulk call, with exact review, no writes before approval, successful replay and preserved booked snapshots. These cloud tests do not establish new Morgan browser audibility.
- Signed-in read-only dashboard/Morgan-panel/template-form checks pass. The form was cancelled without saving; UI save/edit/archive persistence remains unverified.
- Morgan's public MCP origin is the existing local development tunnel. Taylor no longer depends on that tunnel.
- Existing scheduling persistence spans multiple database writes; Redis confirmation claims prevent duplicate replay but are not a cross-table database transaction.
- **AWS is still PAUSED.** No AWS work was performed.

For Taylor practice: sign in as a candidate at `/training`, select an application if desired, press **Start Training**, answer at least two questions, then choose **Finish & Get Feedback**. For the remaining Morgan test, sign in as a recruiter, open **Ask Morgan**, and ask for candidates or available slots. Review the exact proposed action before confirming. Keep only one active voice session tab and use headphones.
