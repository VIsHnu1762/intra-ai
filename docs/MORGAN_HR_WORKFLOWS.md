# Morgan HR workflows

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

6 September 2026. Working branch: `final`. AWS is **PAUSED**. This task does not commit or push changes.

## Diagnosis

The reported failed conversation was session `redacted-runtime-id-6`, channel `redacted-runtime-id-9`, Agora agent `redacted-runtime-id-7`. Between 06:45:29 and 06:46:03 UTC, all 17 recorded MCP tool calls successfully called `get_dashboard_context`. None called `search_candidates`. MCP initialization and tool discovery succeeded. This was a repeated context-fetch loop, not evidence of a Supabase outage.

The signed-in demo recruiter also owned no applications. The two applications then visible in the old global Candidates page belonged to another recruiter's job. The user explicitly chose private recruiter workspaces. Existing ownership was preserved; Morgan and authenticated ATS pages now enforce the same job-creator boundary, including when recruiters share a tenant. A recruiter must sign in as the owner of the job to manage its applications.

Evidence is stored locally under ignored `tmp/voice-diagnostics/`, including `morgan-readonly-diagnosis.json` and `morgan-workspace-counts.json`.

## Product flow

1. Open **Interviews → Interview Templates** at `/admin/interviews/templates`.
2. Create a named template with rounds, duration, focus areas and one or more registered interviewer agents per round. Duplicate, edit, archive or apply a template to a job.
3. Open **Ask Morgan**. Ask which candidates applied to a job, who needs review, which candidates are ready to schedule, or which interviews are upcoming.
4. Ask Morgan to shortlist selected candidates, or shortlist and schedule them with a named template, start date/time, timezone and gap between interviews.
5. Review the exact candidate list, skipped items, template and consecutive time slots. Confirm the displayed action. The panel shows progress and individual outcomes and refreshes the relevant ATS views.
6. Optionally ask for a Gmail draft/send, a calendar event for a saved interview, or a Slack hiring update. Each action shows the destination and exact content before confirmation.

Examples: “Who applied to the software developer intern job?”, “Which candidates still need review?”, “Shortlist Ada and Chris”, “Use the Intern Screen template to shortlist and schedule those candidates tomorrow from 2 pm, Asia/Kolkata, with five-minute gaps.” Morgan asks for missing details and resolves names through authorized records.

## Implementation

- Morgan receives bounded authorized page context at startup. Candidate-list requests go directly to `search_candidates`; a context refresh is limited to a changed page or selection. Zero accessible candidates is a valid result.
- Read tools include scoped jobs, candidate search with pagination, candidate/application/interview/report details, pipeline overview, templates, available slots and connected-service checks.
- Bulk shortlisting accepts up to 50 explicit applications; scheduling accepts up to 25 applications for one job. The model must not equate a truncated search page with “all candidates.”
- Morgan is instructed to use one bulk tool call for an explicit multi-candidate selection. An unexpired pending review blocks further write proposals under the session lock, so a second tool call cannot silently replace the selection being reviewed. Read tools remain available; declining, expiry or an authorized invalidation clears the review.
- The two bulk tools use a scalar MCP representation for `application_ids`, while the backend and browser API retain canonical lists. The current MCP schema prefers comma-separated literal IDs and also accepts JSON-array strings or existing list callers. The transport decoder bounds strings to 8,192 characters, rejects malformed or empty segments, and then applies the unchanged ID, duplicate, count and ownership checks. No Python evaluation, arbitrary quote removal or object coercion is used.
- Batch review verifies the entire selection before any writes. Active interviews and incompatible application states are shown as skipped. Bookings persist per-interview copies of the selected template; editing or archiving the template later does not change booked interviews.
- Template rounds reuse the registered N-agent catalog and existing interview session materialization. Total active duration is limited to 60 minutes. Saved slot claims are conditional on availability.
- Each mutation has a server-owned, immutable, expiring preview bound to the persisted user and voice session. A fresh resource/recipient/time/status check precedes execution. One-time claims prevent replay; partial batches list successful, skipped and uncertain items separately.
- A confirmation race found during review was corrected: execution now consumes the exact reviewed recipients, calendar payload, template snapshot and batch times, rather than rebuilding them after its durable claim. Identity and resource authorization are checked again after that claim; later batch entries keep their reviewed times even if an earlier entry fails.
- Slow confirmed work runs outside the session lock. Polling and heartbeat continue; an interrupted worker is reported as an unknown outcome, never automatically replayed.
- Authenticated ATS candidate/job/application/interview/report operations use persisted identities and job ownership. Candidate dossiers expose resumes only through authorized applications; same-tenant membership and admin role do not grant access to another recruiter's candidates.

## Composio and Agora

The user connected the Composio endpoint in Agora Agent Studio. App-created Morgan sessions supply the Intra AI MCP gateway; that gateway now bridges selected Gmail, Calendar and Slack operations to the supplied Composio endpoint. The model does not receive the broad remote tool catalog or raw Supabase SQL access. Recruitment actions use the application's own Supabase service and business rules, so changes appear in the ATS.

The shared external connection is bound to one persisted recruiter via `MORGAN_COMPOSIO_OWNER_USER_ID`. Other recruiters cannot use that account's mailbox, calendar or Slack connection. Supporting separately connected accounts for every recruiter would require additional per-user connection provisioning.

Private server settings, stored in ignored `backend/.env`:

```text
MORGAN_COMPOSIO_MCP_URL
MORGAN_COMPOSIO_API_KEY
MORGAN_COMPOSIO_OWNER_USER_ID
```

The official Alex/Jordan Custom LLM, M1, Meta-Orchestrator and knowledge graph pipeline is preserved. Taylor continues its previously verified native Agora practice flow with CV context loaded once. No independent LLM service or API key was added.

Morgan's local deployment now explicitly uses Agora-managed `gpt-4.1-mini`, matching its inspected Studio model label. Its inherited Custom configuration looped after successful tool results. A same-model managed start followed by full runtime replacement of `llm.params` produced one candidate search and a correct final answer with the original MCP JSON format. Join alone retained incompatible custom proxy parameters; the runtime update removes them before the app returns session credentials. No independent LLM key or service was added. Saved Studio ASR/TTS and Taylor's Studio LLM remain in use.

This opt-in mode is controlled by `AGORA_MORGAN_LLM_MODE=managed` and `AGORA_MORGAN_MANAGED_MODEL=gpt-4.1-mini` in the local environment. Example/default mode is `studio`. Failed parameter updates attempt cleanup of only the newly created agent and fail startup instead of returning a usable session. Contract reference: [Agora runtime update](https://docs.agora.io/en/api-reference/api-ref/conversational-ai/update).

## Migration

`backend/migrations/20260906_interview_templates.sql` was applied only to the Supabase project matching the application's configured URL. It creates `interview_templates`, enables RLS, restricts its grants to the backend service role and adds `scheduled_interviews.template_snapshot` JSONB. No existing recruitment rows were rewritten.

Live read-only verification confirmed the table, column, enabled RLS, denied anonymous/authenticated SELECT and granted service-role SELECT/INSERT. Migration SHA-256: `94677facb90c95ede6a72f4be46a132aa00916160eeafe5f7fd099c57ed1d4f7`. Evidence: `morgan-template-migration-live.json`.

## Validation and limits

Focused workflow tests cover authorization of the whole batch, duplicate/missing IDs, timezone errors, changed previews, template snapshots, active-interview skips, partial outcomes, replay prevention, nonblocking result reads and exact reviewed connector destinations. Connector tests use controlled provider responses; those tests do not prove delivery of a real message or event.

Live connector checks confirmed Slack authentication, Calendar enumeration and the matching Supabase project. Gmail initially remained unavailable after reconnection because Morgan's Composio session pinned the old account and auth configuration. The unique active enabled Gmail account belonged to the same Composio session user. After automatic approval review requested explicit authorization, the user approved this exact replacement. One PATCH updated only the Gmail mappings; full-config readback confirmed all other settings, connection mappings, session ID and endpoint were unchanged (version 2 → 3). The deployed Morgan bridge then successfully verified `GMAIL_GET_PROFILE`. No email contents were read. Evidence: `morgan-gmail-session-repair-applied.json` and `morgan-gmail-production-bridge-verification.json`.

Real email, Slack-message and Calendar-event writes have not been performed during this task; connection/profile checks do not prove message delivery.

Bulk scheduling creates Intra AI interview slots. It does not automatically email candidates or create external calendar events; those are separate reviewed actions. Calendar export does not promise free/busy conflict detection. A failed or interrupted batch may contain completed earlier items and requires checking its per-item results before a new request.

Legacy public official-interview RTC/transcript/callback routes retain their existing session-capability contract. This work does not claim to replace all official voice-route authorization. No new browser microphone or spoken Morgan command verification is implied by HTTP/MCP or unit-test results.

## Executed validation

- Backend regression command: `M1_PROVIDER=mock GROQ_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests -q` from `backend/`: **1,346 passed, 17 skipped, 3 warnings**, including the confirmation race fix, managed-mode implementation, pending-review overwrite guard and JSON/CSV MCP compatibility. The skipped provider tests are not claimed as live integration passes. Log: `morgan-workflow-backend-final.log`.
- Frontend: **52 tests passed**, TypeScript and targeted ESLint checks passed, production build passed. Logs: `morgan-confirmations-frontend-tests.log` and `morgan-final-frontend-build.log`.
- `docker compose build backend frontend` passed. The updated containers were loaded locally; backend health returned HTTP 200. No active auxiliary voice session was interrupted.
- Live read-only privacy checks against Supabase: authorized lists returned HTTP 200 with owned records only, cross-recruiter direct access returned 403 in both directions, anonymous candidate listing returned 401. Evidence: `recruiter-privacy-live-readonly-summary.json`.
- Live public MCP/API batch check: two fictional candidates were found by name and ID, shortlisted only after confirmation, then scheduled using a 25-minute template with five-minute gaps. Both requests returned `executing` promptly and later `succeeded` with two successful items. Repeat confirmation returned the saved result with no duplicate interviews. Browser-facing APIs returned both correct names, `scheduled` statuses and 25-minute durations.
- Editing that test template to 15 minutes/version 2 left both saved interview snapshots at the reviewed 25 minutes/version 1. The test ended its own Morgan agent and removed every tracked job, candidate, application, slot, interview and template row. No official interview agent, email, Slack message or external calendar event was started. Evidence: `morgan-bulk-live-summary.json`. Unused fictional scheduled-session cache entries can remain until the backend restarts.
- A signed-in, read-only browser check passed for the recruiter dashboard, Ask Morgan panel and Interview Templates route. The create form showed the registered Alex/Jordan choices, round controls, duration budget and focus field. The form was cancelled without saving. A later deployed-page check confirmed the readable default focus label, “Coding & Problem Solving.” This verifies rendered navigation and form controls; UI save/edit/archive persistence and browser voice were not exercised. Evidence: `morgan-signedin-readonly-ui-qa.json` and `template-focus-label-deployed-ui-verification.json`.
- Earlier live native Morgan tests exposed a conversational loop after the initial prompt fix: Agora's history stored successful empty candidate-search results, but Morgan called search again instead of producing a final answer. Diagnostic-only `tool_choice=auto` and `max_history=32` overrides did not resolve the loop and were not shipped. Subsequent managed-mode tests below establish lookup continuation; the original provider's hidden request assembly remains unverified. Evidence: `morgan-native-loop-diagnosis.json`.
- A no-tool native question produced a normal answer. Appending a factual completion summary to successful empty search results still produced repeated tool calls; that experiment was removed from source and the deployed endpoint. See [the detailed continuation diagnosis](MORGAN_TOOL_CONTINUATION_DIAGNOSIS.md) for call-ID correlation and the read-only Studio inspection.
- The subsequent same-model managed join plus full runtime params replacement passed: one native `search_candidates` call, one matching real result and a correct final answer. The implementation was then built and loaded in the local backend; `/api/v1/health` returned 200 and running settings confirmed managed mode with `gpt-4.1-mini`. Browser microphone/audio playback after this fix has not yet been verified. Evidence: `morgan-managed-clean-params-probe.json`, `morgan-managed-clean-params-turns.json`, `morgan-managed-production-build.log`, `morgan-managed-production-deploy.log`.
- With the original array-valued MCP schemas, deployed native lookup correctly named two fictional applicants, but natural-language and explicit-tool batch requests selected individual status changes. The pending-review guard prevented the second proposal from replacing the first. Reapplying the same runtime prompt did not resolve this; allowing only the bulk tool produced no call. A separate new no-argument `get_recruiting_overview` control passed, so newly added tools were not uniformly unavailable. The public gateway delivered all 26 tools; the final model-facing schema remains unobservable.
- After the two bulk MCP fields were advertised as JSON-array strings, a fresh native natural-language shortlist test passed with the full catalog and no provider override or manual MCP call. Morgan searched once, initially submitted an invalid string, then corrected it to a valid two-ID JSON-array string. The server created one exact two-candidate review with no writes before approval. Authenticated confirmation returned `executing`, then `succeeded` for both; replay returned the same result, and the browser-facing API showed both applications as `shortlisted`. The agent was independently verified `STOPPED`, and all tracked fictional rows were removed. Evidence: `morgan-native-shortlist-mcp-compatible-20260906.json` and its `-cleanup.json` companion. This is native text-input integration, not browser microphone E2E.
- The corresponding native scheduling test selected the correct bulk tool but twice supplied a plain comma-separated string of the two exact fictional application IDs. The JSON-only decoder rejected both calls; no pending review, slot or interview was created. The existing tunnel inspector captured only the verified fixture-ID strings. Later cleanup independently confirmed `STOPPED`, no worker, unchanged `shortlisted` application states and zero remaining tracked rows. Evidence: `morgan-native-schedule-mcp-compatible-20260906.json`, its `-cleanup.json` companion, and `morgan-native-schedule-argument-shape.json`.
- The observed CSV syntax is now supported by the bounded MCP decoder, with actionable format errors and unchanged canonical validation. **The final native scheduling rerun passed** using the full deployed catalog, natural-language requests, and no provider overrides or manual MCP calls. Morgan called `search_candidates`, `list_interview_templates` and `bulk_schedule_interviews` once each. Its CSV argument selected exactly the two fictional applications, producing one reviewed 25-minute/version-1 template schedule at 09:00 and 09:30 UTC with five-minute gaps. There were no writes before approval. Confirmation returned `executing`, then two successes and zero failures; replay returned the same saved result and left exactly two interviews. Browser-facing APIs returned both names, `scheduled` statuses and 25-minute durations. Editing the template to version 2/15 minutes left both booked snapshots at version 1/25 minutes. Evidence: `morgan-native-schedule-csv-compatible-20260906.json`. This is native text-input integration; browser microphone/audibility remains a separate acceptance check. See [the continuation diagnosis](MORGAN_TOOL_CONTINUATION_DIAGNOSIS.md) for the controlled trajectory.
- Independent final cleanup confirmed that agent `redacted-runtime-id-8` was `STOPPED`, its session was disconnected/inactive/not executing, and exact tracked application, candidate, slot, template, job and scheduled-interview counts were all zero. No external communications or official interview agents were started. Evidence: `morgan-native-schedule-csv-compatible-20260906-cleanup.json`.
- A read-only direct-table privacy audit checked `jobs`, `candidates`, `applications`, `parsed_resumes`, `scheduled_interviews` and `reports`. All six contained records, had RLS enabled with no policies, and exposed zero rows to anonymous count-only REST requests. Database metadata showed neither `anon` nor `authenticated` bypasses RLS or owns those tables. An authenticated Supabase JWT request was not tested. Redundant table grants remain, but the current default-deny RLS prevented anonymous row access. No table privileges or records were changed. Evidence: `ats-table-privacy-live-readonly.json`.

The table privacy audit does not cover RPC functions, views, Storage, or public email-based application identity linking. Authenticated ATS scope checks, the six direct-table checks and new template-table grants are the boundaries verified here.
