# Morgan: native MCP continuation diagnosis

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

Date: 6 September 2026. Morgan now passes native candidate lookup, confirmed two-candidate shortlisting and confirmed two-candidate template scheduling through the full MCP catalog. The bounded CSV decoder resolved the observed scheduling input mismatch in the final native rerun. Browser microphone and audible playback after these changes remain unverified. AWS remains **PAUSED**.

## Original failure boundary

Morgan's app session starts successfully. Agora calls the authenticated Intra AI MCP gateway, candidate search reads the recruiter's authorized Supabase records, and Agora history stores successful results with matching tool-call IDs. Morgan then requests the same search again instead of producing a final answer.

The failure is between the completed tool result and the next conversational answer. The actual downstream LLM request is not visible in Agora's history API, so an underlying model, provider-adapter or saved-configuration defect is not yet proven. Supabase connectivity, MCP reachability and mismatched tool-call IDs are not supported explanations for these captured failures.

Subsequent read-only turn diagnostics exposed the actual upstream rejection in five later turns of the original voice session, after speech interrupted its initial loop: HTTP 400, `invalid_request_error`, parameter `messages.[0].role`. The provider says a `tool` message lacks a preceding assistant message with `tool_calls`. The correctly paired stored histories came from separate uninterrupted probes, not those failed voice turns. The captured error locates the interrupted session's failed replies at the conversation-forwarding boundary; it does not yet explain the initial repeated search or prove whether history truncation or another adapter behavior caused the malformed request.

A comparison using Agora-managed `gpt-4.1-mini`, matching the inspected Studio model label, also failed before a tool call when applied only at join. Its upstream error rejected inherited request fields named `agent_id`, `agent_uuid`, `auth_jwt`, `call_id`, `cid`, and `type`. No field values were exposed. This shows the join override did not remove Studio-derived request parameters. Its subsequent failure-message TTS turn completed; that fallback is not a successful candidate-list answer. The join-only configuration was not shipped.

## Deployed fix and current evidence

Morgan now starts with an explicit Agora-managed LLM configuration and replaces the entire runtime `llm.params` object with the selected model before returning session credentials. This removes the inherited custom proxy parameters. Failed updates attempt to stop only the newly created agent and fail startup. The original MCP JSON result format, app prompt, controlled tools, RTC identity and saved Studio ASR/TTS remain in use. Taylor and the official interview pipeline are unchanged. No independent LLM service or key was added.

The controlled managed-join-plus-update comparison produced exactly one `search_candidates` call, a matching real empty result and a correct final answer, with no provider error. Its session was `redacted-runtime-id-13`, Agora agent `redacted-runtime-id-20`. The implementation was subsequently built and loaded locally; health returned HTTP 200.

A separate test through the deployed start API, with no provider overrides or manual MCP calls, found both fictional applicants using one native search and answered with both names. Its next request exposed a separate batching issue: Morgan proposed two individual status updates instead of one bulk shortlist. Neither proposal was confirmed, no application status changed, and the test removed its six fixture rows and ended its own agent. The prompt and tool descriptions now instruct Morgan to select the bulk tool for multiple candidates. A server guard preserves an unexpired pending review and rejects additional write proposals until it is confirmed or declined; read tools remain available, and expired/invalidated reviews clear safely. These safeguards remained in place for the later transport tests below.

These tests use Agora's native text-input endpoint. They prove model/tool continuation, not browser microphone input or audible playback. The original custom provider's hidden request assembly remains unverified; the managed fix avoids the configuration path that failed rather than proving its internal cause.

### Batch selection investigation with canonical array schemas

The batch guidance did not resolve native tool selection. A subsequent natural-language test still called `update_application_status`; the server rejected the second individual proposal with `CONFLICT`, preserving the first review. In a separate diagnostic, even naming `bulk_shortlist_candidates` and supplying both exact fictional application IDs produced a single-application proposal. Morgan's reply described both IDs, but the persisted review contained one. The diagnostic declined that proposal, verified both applications were still `applied`, and removed its fixtures.

The existing tunnel's captured HTTP response proves that Agora received all 26 current MCP tools, with exact updated descriptions and schemas, including both bulk tools. The running backend also reconstructs the 4,125-character prompt containing the new instructions. Agora's status/history APIs do not expose the final model-facing system messages or tool definitions. At this stage the failure was after public MCP discovery and before correct bulk tool selection; a hidden schema-conversion or inherited-configuration cause was not established. Earlier bulk API success alone did not establish native batch-command success.

Reapplying the same `system_messages` through the documented runtime update did not resolve the issue. A separate disposable session restricted the join allowlist to `bulk_shortlist_candidates` while retaining its original array schema. It produced no tool call or persisted review, although its prose claimed the review was prepared. No excluded single-update tool was called. The agent was independently verified `STOPPED`; both applications remained `applied` and all tracked fixtures were removed.

A full-catalog control then called the newly added no-argument `get_recruiting_overview` once, received a successful scoped result and produced a stable answer. This rules out all new tools being unavailable, but does not expose the downstream schema transformation or establish a general prohibition on array inputs.

### Scalar schema: native shortlist passes

The only compatibility change in the next test was the MCP boundary representation of `application_ids` for the two bulk tools: a bounded JSON-array string in a deep copy of the advertised schema, decoded before normal service dispatch. The backend and browser API retained their canonical list contracts. Model, prompt, endpoint, ASR/TTS, full catalog, ownership rules and confirmation were unchanged.

Session `redacted-runtime-id-14`, agent `redacted-runtime-id-21`, passed a natural-language two-candidate shortlist with no manual MCP invocation or provider override. Morgan searched once and identified both fictional applicants. Its first bulk call contained an invalid string and was rejected; it corrected the next call to a valid JSON-array string containing both actual application IDs. The resulting single review contained two eligible candidates and no writes occurred before confirmation. Authenticated approval returned `executing`, then `succeeded` for two items. Repeat confirmation returned the identical saved result; browser-facing APIs showed both application statuses as `shortlisted`. Cleanup independently confirmed the provider stopped and all tracked fictional rows were removed.

This is evidence that the scalar MCP representation permits successful native bulk selection on this deployment. It does not reveal the internal reason the original array schema failed. It is a native text-input and real-database test, not browser microphone or speaker verification.

### Scheduling CSV mismatch and bounded fix: final native rerun passes

Session `redacted-runtime-id-15`, agent `redacted-runtime-id-22`, correctly selected `bulk_schedule_interviews` but twice supplied `application_ids` as a plain 73-character string containing two fictional UUIDs separated by one comma. It used no brackets or quotes. The existing tunnel inspector captured this exact scalar value after checking that it contained only the tracked fixture IDs and delimiter; no headers or credentials were retained.

The then-deployed JSON-only decoder rejected both calls before proposal creation. No interview or slot was created. The probe's initial cleanup was conservatively deferred when immediate stop verification failed; the separate cleanup artifact subsequently confirmed `STOPPED`, a disconnected inactive session, no worker, both applications still `shortlisted`, zero interviews/slots and zero remaining tracked fixture rows. The initial failure artifact must be read with that final cleanup artifact.

The MCP boundary now prefers comma-separated application IDs and also accepts JSON-array strings and existing list callers. Strings remain capped at 8,192 characters. CSV segments are trimmed and must be literal resource IDs; empty segments, arbitrary quotes, malformed IDs and object coercion are rejected. There is no Python evaluation. The canonical service still validates duplicates, limits of 50 for shortlist and 25 for schedule, application/job ownership, times, template selection and the exact review before execution. Invalid format responses explain accepted syntax without echoing input IDs.

The final rerun, session `redacted-runtime-id-16`, agent `redacted-runtime-id-8`, **passed** with the full deployed catalog, natural-language requests, no provider overrides and no manual MCP calls. Native history shows exactly three calls: one `search_candidates`, one `list_interview_templates` and one `bulk_schedule_interviews`. The last call used the exact two fictional IDs in the observed CSV format; no retry was needed.

The single review selected both eligible applications and the saved version-1, 25-minute template, with interview starts at 09:00 and 09:30 UTC and five-minute gaps. No writes occurred before confirmation. Authenticated approval returned `executing` followed by two successes, zero failures and zero skips. Repeat approval returned the identical saved result and exactly two persisted interviews. Browser-facing API readback showed both fictional names, `scheduled` statuses and 25-minute durations. A subsequent edit of the template to version 2/15 minutes left both booked snapshots unchanged at version 1/25 minutes. This verifies native model-to-MCP scheduling plus reviewed execution and database readback; it does not establish browser microphone or audible output.

Independent cleanup subsequently confirmed agent `redacted-runtime-id-8` was `STOPPED`, the session was `DISCONNECTED`, inactive and not executing, and every exact tracked application, candidate, slot, template, job and scheduled-interview count was zero. No official interview agent or external communication was started.

Focused MCP/session/tool/workflow coverage passes **284 tests**. The full backend command `M1_PROVIDER=mock GROQ_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests -q` passes **1,346 tests, with 17 skipped and 3 warnings**. Frontend coverage passes **52 tests**, with production build and targeted checks passing. The scheduling result above is a separate live integration check, not an inference from those test counts.

A signed-in read-only browser check separately passed dashboard, Morgan-panel and template-form navigation. The form was cancelled without saving, and the deployed readable focus label was verified. UI save/edit/archive persistence and new Morgan microphone E2E were not tested. Gmail's explicitly approved session mapping repair was read back and the deployed bridge verified `GMAIL_GET_PROFILE`; no email contents or message sends were involved. Taylor is unchanged by this work and retains the user's earlier practice-flow confirmation.

## Controlled observations

| Check | Observed result |
| --- | --- |
| Original reported conversation | 17 successful `get_dashboard_context` calls; no candidate search |
| Startup context and direct-search prompt | Morgan selects `search_candidates`; repeated successful searches still produce no answer |
| Tool-call pairing | 15/15 captured results match the preceding assistant tool-call ID |
| No-tool conversational control | One user message and one assistant answer; no tool calls; answer captured after 12.46 seconds including startup |
| Diagnostic `tool_choice=auto` | Six completed results, no final answer; not retained |
| Diagnostic `max_history=32` | Six completed results, no final answer; not retained |
| Additional plain-language result summary | All seven captured tool results contain the completion summary; no final answer |
| `structuredContent` in that experiment | Returned by Intra AI, but Agora history reports `null`; this alone does not reveal downstream model input |
| Recruiter privacy | The test recruiter owns no applications; zero matches is correct for that account |
| Reapply identical batch system prompt | Native still chose individual status updates; no incorrect proposal approved |
| Only original array bulk tool allowed | No tool call or persisted review; native prose incorrectly claimed a review existed |
| Newly added no-argument overview tool | One real native call, successful result and stable answer |
| Full catalog with JSON-array string fields | Native shortlist corrected one malformed input, created the exact two-item review, then confirmed and persisted both shortlists |
| Native scheduling with JSON-only decoder | Correct bulk tool selected; two plain CSV ID strings rejected before any proposal or booking |
| CSV-compatible decoder | Native search, template lookup and bulk scheduling called once each; exact two-item review, two confirmed bookings, replay and snapshot preservation pass |

The format experiment preserved the original JSON text block and appended a factual completion summary. It did not solve the problem and was removed from source. The native tests used Agora's text-input endpoint, not a browser microphone, so they do not establish audible playback or voice E2E success.

## Studio inspection

The inspected live Morgan pipeline is `edd04216a71747f99bcd05c012ab9ce8`, Studio edit ID `18270`. At inspection a second Morgan existed in the account but was not the pipeline configured by this application. The user subsequently reported deleting the unused Morgan `18268` and Taylor `18269`. The app's retained Taylor is `18277`, pipeline `52595fa620a34fa682c468c602978bd8`; both retained IDs were verified in the running backend and local environment. Assistant-driven deletion was blocked by approval review and no agent was deleted by the assistant.

Observed UI settings:

- Model label: `Custom - gpt-4.1-mini`.
- Maximum history: 32.
- ASR: Deepgram Nova 3, English (US).
- TTS: MiniMax Speech 2.8 Turbo, Radiant Girl.
- Studio Actions: no MCP servers listed. App-created sessions explicitly supply the Intra AI MCP gateway.
- Live status; Last Published and Last Edited both show 6 September 2026, 01:26.

The visible custom configuration was empty and the Full REST export supplied a pipeline reference. Neither surface exposed the effective upstream endpoint, `tool_choice`, token limit, or an immutable published configuration. No Studio configuration, account, or publication was changed.

## Representative session identifiers

| Test | Intra AI session | Agora agent |
| --- | --- | --- |
| Original reported conversation | `redacted-runtime-id-6` | `redacted-runtime-id-7` |
| Captured original result format | `redacted-runtime-id-17` | `redacted-runtime-id-23` |
| No-tool control | `redacted-runtime-id-18` | `redacted-runtime-id-24` |
| Appended summary experiment | `redacted-runtime-id-19` | `redacted-runtime-id-25` |

All isolated probes verified their own agents stopped, including deferred cleanup where immediate provider state had not settled. Diagnostic-only proposals were declined without hiring mutations. The confirmed native shortlist and final native scheduling tests changed only their tracked fictional applications and bookings; independent cleanup verified their absence afterward. A separate disposable fictional-data test validated confirmed shortlist and scheduling APIs, while the later native tests establish actual model tool selection. No test sent email, Slack messages or calendar invitations, or modified existing real candidate applications.

## Local evidence

Sanitized diagnostic artifacts are under ignored `tmp/voice-diagnostics/`:

- `morgan-native-loop-diagnosis.json`
- `morgan-native-tool-call-correspondence.json`
- `morgan-native-conversation-control.json`
- `morgan-native-result-format-probe.json`
- `morgan-studio-readonly-ui-inspection.json`
- `morgan-original-turns-live.log`
- `morgan-managed-native-provider-live.log`
- `morgan-managed-clean-params-probe.json`
- `morgan-managed-clean-params-turns.json`
- `morgan-managed-production-build.log`
- `morgan-managed-production-deploy.log`
- `morgan-native-bulk-shortlist-live-20260906-managed.json`
- `morgan-native-shortlist-batch-fixed-20260906.json`
- `morgan-batch-actual-mcp-catalog.json`
- `morgan-native-explicit-bulk-tool-20260906.json`
- `morgan-native-prompt-reapply-diagnostic-20260906.json`
- `morgan-bulk-only-allowlist.json`
- `morgan-native-new-overview-20260906.json`
- `morgan-native-shortlist-mcp-compatible-20260906.json` and `morgan-native-shortlist-mcp-compatible-20260906-cleanup.json`
- `morgan-native-schedule-mcp-compatible-20260906.json` and `morgan-native-schedule-mcp-compatible-20260906-cleanup.json`
- `morgan-native-schedule-argument-shape.json`
- `morgan-native-schedule-csv-compatible-20260906.json`
- `morgan-native-schedule-csv-compatible-20260906-cleanup.json`
- `morgan-mcp-csv-compatibility-tests.log`
- `morgan-workflow-backend-final.log`
- `morgan-confirmations-frontend-tests.log`
- `morgan-signedin-readonly-ui-qa.json`
- `template-focus-label-deployed-ui-verification.json`
- `morgan-gmail-session-repair-applied.json`
- `morgan-gmail-production-bridge-verification.json`
- `morgan-bulk-live-summary.json`

An attempt to create a separate public diagnostic tunnel was rejected by automatic approval review because it would add an exposed endpoint. The local relay was stopped. Subsequent testing used the existing authorized endpoint.

See [Morgan HR workflows](MORGAN_HR_WORKFLOWS.md) for implemented features, tests, privacy scope and remaining validation limits.
