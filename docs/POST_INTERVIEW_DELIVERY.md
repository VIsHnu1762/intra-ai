# Post-interview delivery report

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

Prepared 2026-09-06. This report distinguishes implemented behavior, automated
regression results, and live evidence. **Local deployment completed**: the built
backend and frontend containers were recreated successfully. Backend health and
the fresh interview preparation page returned HTTP 200. No active interview or
auxiliary application sessions were present before the restart. AWS remains paused.

The latest user instruction selects paid AICredits for realtime M1 and
Meta-Orchestrator, superseding the attachment's earlier instruction to keep
those two providers on Groq. Both realtime layers now use
`google/gemini-3.1-flash-lite` through AICredits and their separate credential
slots. Effective settings were verified inside the restarted backend. The post-interview provider slots below remain
GPT-5 Nano and Gemini 2.5 Flash-Lite. See
[AICredits integration details](AICREDITS_POST_INTERVIEW.md) for provider contracts
and explicitly labeled model experiments; historical model choices in that
document are not proof of the final runtime configuration.

## A. Post-interview report

The implementation reuses `ReportService`, the existing reports table and
recruiter report routes. It does not create a second reporting system.

Completion persists the scheduled interview and application as completed, then
calls `ReportService.request_report()` on the caller's live event loop. The
provider work runs outside that loop. This fixes the prior risk of cancelling a
report task when the temporary persistence thread's event loop closes. A
recruiter can also request generation or retry from the report page through
`POST /api/v1/interviews/{interview_id}/report/generate`.

Source preparation uses all available, unique, valid scored M1 evidence from
the interview context, with actual answer/question links and legacy persisted
evaluations where applicable. It retains distinct round IDs, observed agent
IDs, competency findings, and available confirmed handoffs. Configured rounds
without observed scores appear as coverage gaps, not fabricated assessments.
The four single/multiple-round and single/multiple-agent combinations have
automated aggregation coverage.

When a durable source snapshot is unavailable, recovery reads only this
interview's Neo4j records. It accepts the exact interview ID and its deterministic
`intra-{interview_id}` channel alias, verifies candidate/round/answer
relationships, and rejects conflicts. It never borrows scores from another
interview or rewrites historical graph data. A context snapshot keyed by channel
is normalized only when the registered session proves that channel belongs to
the same interview and candidate.

At least **two distinct scored answers with complete identity links** are
required. Multiple findings about one answer do not satisfy this guard. Missing
evidence produces an explicit failure state; an empty or zero-filled report is
not presented as ready. A valid existing score of zero remains valid.

The service persists the source assessment before requesting a GPT-5 Nano
narrative through AICredits. Narrative strengths and improvements must cite
actual supplied evidence IDs. The model does not set the score. The validated
draft is persisted before candidate feedback generation, so a feedback retry
reuses the same source and recruiter narrative.

Supabase stores source, draft and attempt state on `scheduled_interviews`, and
the completed output in `reports`. The additive migration
`backend/migrations/20260906_post_interview_reports.sql` was applied to the
configured hosted project and verified. Its claim/finish operations fence
concurrent attempts; required-field readiness agrees with the Python service.
The RPCs are restricted to service-role execution and existing RLS remains.

Recruiters open `/admin/reports/{report_id}` or the interview's report link.
The API supports report or interview IDs, status polling, and explicit retry.
States are `not_completed`, `not_started`, `generating`, `ready`, and `failed`.
An interrupted attempt becomes retryable after its lease expires. Opening or
refreshing a ready report reads saved data and does not regenerate it.

### Actual report generation verified

With explicit user approval, the existing completed interview
`redacted-runtime-id-26` was recovered and reported. Supabase had
no answer/evaluation rows for this older interview; scoped Neo4j recovery found
**two actual answers, two scored evidence items, two questions, and one observed
scored round**. Both scored answers were included. No interview data was seeded
or fabricated.

The operation made one Nano request and one Gemini request and completed in
**39.593 seconds**, including source recovery and persistence. It preserved
report ID `redacted-runtime-id-27`, saved two supported improvement
citations, and passed repeated service reads and ready-report replay without
additional model calls. The source had no recorded historical handoffs; none
were invented. New successful physical handoffs now record metadata at the
actual ownership-commit point, with failed/stale handoffs excluded.

This is a live generation/persistence result for an existing completed
interview, **not** a newly recorded complete browser interview.

## B. Overall candidate performance feedback

The report's existing overall metric remains the source of truth: the mean of
all unique valid M1 evidence scores multiplied by ten, or the existing legacy
mean-of-round-type-means calculation. Historical scores are not retrospectively
rescaled. The 1–5 rating is deterministic:

`rating = round_half_up(1 + overall_score / 25, 1)`

This maps 0/100 to 1/5 and 100/100 to 5/5. It is an overall aggregate across the
available scored interview, not a separate model evaluation or a rating of the
last answer. The strict two-distinct-answer gate prevents a single-answer
aggregate from being published as overall performance. Coverage gaps remain
visible to the recruiter.

Gemini 2.5 Flash-Lite receives the overall score/rating, aggregate coverage
counts, and supported narrative strengths/improvements. It receives no raw CV,
raw answer text, internal evidence IDs, recruiter recommendation, or private
notes. The service supplies the deterministic performance-band sentence and
validates the remaining short feedback. Exactly three nonblank lines and the
rating are persisted with the same report.

The actual saved report's existing aggregate is **1.0/100**, mapping to
**1.0/5**, across its two scored answers. During verification Gemini's initial
strength sentence was unsupported by the narrative's empty strengths list.
The validation now substitutes an honest insufficient-strength statement in
that case. A narrowly scoped, approved compare-and-swap corrected only that
second line of the newly generated report. It left scores, source evidence,
other feedback lines and all other report fields unchanged, made no model
calls, and passed immutable readback/replay again.

Candidates see only the saved rating and three feedback lines on the completed
interview screen, `/interview/{id}/report`, and the portal's performance link.
`GET /api/v1/interviews/{id}/performance` exposes only interview ID, readiness
state, rating, feedback, creation timestamp and a safe status message.
Candidates cannot retrieve the detailed recruiter report, report status/list,
or PDF. Persisted identity and job ownership are rechecked server-side;
recruiter/admin role alone never grants another recruiter's workspace access.

Automated workflow tests verify those boundaries, two-answer grounding,
rating consistency, invalid provider output, partial failure/retry and stable
saved results. **NOT VERIFIED — fresh HTTP access-boundary checks; the user elected to test.**

## C. AICredits configuration

All credentials remain server-side and are never included in this report.

| Setting | Post-interview purpose |
| --- | --- |
| `AICREDITS_API_KEY_GPT5_NANO` | Recruiter narrative credential |
| `AICREDITS_API_KEY_GEMINI_FLASH_LITE` | Candidate feedback credential |
| `AICREDITS_GPT5_NANO_MODEL` | Default `openai/gpt-5-nano` |
| `AICREDITS_GEMINI_FLASH_LITE_MODEL` | Default `google/gemini-2.5-flash-lite` |
| `AICREDITS_BASE_URL` | Default `https://api.aicredits.in/v1` |
| `AICREDITS_TIMEOUT_SECONDS` | Independent post-interview request timeout |

The two steps use their own key slots. Missing credentials fail explicitly;
there is no automatic key/model/provider substitution. Native transport tests
cover malformed/truncated/oversized content, non-finite values, rejected
redirects, safe errors and secret exclusion. The provider client does not
persist application records; the report service owns validation and commits.

Actual provider verification includes benign format requests, a clearly
fictional two-answer in-memory report/feedback probe, and the explicitly
authorized actual report above. The fictional probe produced a validated
70/100 aggregate and 3.8/5 projection, with Nano taking 15.673 seconds and
Gemini 1.060 seconds. It created no user or hiring records. Those timings are
provider completion measurements, not voice response latency.

Realtime M1/Meta provider/model configuration is a separate current user
instruction. Both realtime layers now select Gemini 3.1 Flash-Lite, independently of the
report slots. Two grounded fictional turns took 5.102 and 4.708 seconds for M1
plus Meta, excluding all audio stages. A complete 3–4 second voice response is
not verified. The user elected to perform the fresh browser voice test.

## D. Interview room

The existing camera stage, header, agent sidebar, transcript content, connection
states, microphone/camera controls, audio activation and leave action remain in
their existing layout. The styling uses the portal's existing `bg`, `surface`,
`brand`, `brand-light`, `border`, `text-primary`, `text-muted`, `text-inverse`,
and semantic success/warning/error tokens. The previous custom dark surfaces,
gradients and text colors were aligned with those shared tokens.

This is theme alignment, not a redesigned interview room or an STT/TTS
replacement. The source changes are in
`frontend/src/app/(candidate)/interview/[token]/page.tsx`. The build/type checks
passed. **NOT VERIFIED — a fresh browser voice interview after deployment; the user
elected to test it.** Existing user-confirmed voice tests from earlier work are
historical and cannot establish the newly deployed end-to-end result.

## E. Interviews page

The recruiter Interviews page now has the scheduled-interview list and its
existing candidate, room, report and scheduling actions. The Calendar View
toggle and calendar rendering were removed from this page only. Interview
templates remain accessible.

Scheduling services, slot fields, calendar integration, reschedule/cancel APIs
and Morgan's calendar tools were retained. No AWS/calendar infrastructure was
removed or added. Taylor and Morgan configuration are outside this report/UI
change. Source/build checks passed; the newly built page's live visual check
is left to the user's test.

## F. Regression and remaining verification

| Verification | Observed result |
| --- | --- |
| Full backend suite | **1,562 passed, 35 skipped, 3 warnings**, 7.33 seconds |
| Focused report/source/workspace/handoff suite | **198 passed**, 2 existing deprecation warnings |
| Frontend tests | **59 passed**, as reported by the frontend/deployment owner |
| Frontend type checking and production build | Passed; Docker frontend image deployed locally |
| Backend Docker build | Passed; image deployed locally |
| Hosted report migration | Applied; schema, readiness RPC, grants and retained RLS verified |
| Live actual Nano report + Gemini feedback | Passed; two actual scored answers, saved report, immutable replay |
| Saved report's one-line validation correction | Passed; guarded single-field correction, no model calls, immutable replay |
| HTTP report/status/projection/authorization checks | **NOT VERIFIED**; prepared script was not run after the user deferred testing |
| Fresh official browser voice + automatic completion-to-report | **NOT VERIFIED** after these changes |
| All four round/agent aggregation modes | Automated tests passed; no claim of four fresh voice sessions |
| Current page visual inspection | User will test |

The source-focused command was:

```sh
cd backend
venv/bin/python -m pytest tests/test_voice_handoff.py tests/test_post_interview_reports.py tests/test_report_evaluation.py tests/test_recruiter_workspace.py -q
```

Key ignored evidence artifacts under `tmp/voice-diagnostics/`:

- `post-interview-backend-final.log`
- `report-handoff-review-tests.log`
- `post-interview-backend-docker-build.log`
- `post-interview-frontend-docker-build.log`
- `post-interview-report-migration-live.json`
- `actual-completed-report-evidence-readonly.json`
- `actual-completed-report-evidence.json` — historical generation result before the feedback correction
- `actual-completed-report-feedback-correction.json` — current corrected result and replay checks
- `synthetic-report-provider-live.json`
- `probe-saved-report-http.py` — prepared, not yet run

The old interview proves recovery and reporting for its available evidence; it
does not prove that an unseen round occurred or reconstruct absent historical
handoffs. Deferred browser/HTTP checks are not represented as passed. The
overall application remains on the existing Agora, Custom LLM, context,
orchestrator and Knowledge Graph architecture. **AWS remains PAUSED.**

## Manual test handoff

The original `redacted-runtime-id-1` demo room was subsequently tested by
the user. It revealed stale sample Payment Ledger context and a deterministic
fallback that replaced contextual questions after brief/weak answers. This is
documented with the correction in [CONTEXTUAL_FOLLOWUP_FIX.md](CONTEXTUAL_FOLLOWUP_FIX.md).

Current replacement demo room: http://localhost:3000/interview/redacted-runtime-id-4/prep

The replacement is an in-memory Alex/Jordan validation fixture with an empty CV
and generic software-developer practice brief. It was created but not started.
The updated backend is healthy; backend health and the prep page returned HTTP
200. Follow-up regressions and the full backend suite passed (1,574 tests, 35
skipped). The user will assess fresh voice quality. No additional model benchmark
or microphone test was run. Existing scheduled interviews retain their saved
CV/JD context and also use the corrected follow-up routing. A subsequent LMS
test exposed question-identity and competency-label mismatches; the second
correction is documented in `CONTEXTUAL_FOLLOWUP_FIX.md`. It was loaded after
the user's explicit restart request, with **1,596 backend tests passing**.
The next completed-room review exposed compound framing, split speech and
premature completion. Those corrections are also documented there and loaded;
the latest full backend run passed **1,667 tests**, with 35 skipped. Browser
voice quality after that update remains for the user's test.
