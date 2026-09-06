# CV context, HR reports, and Taylor feedback recovery

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

Prepared 2026-09-06. This update concerns the demo candidate's application and the
reported CV, post-interview report, and practice-feedback failures. AWS remains
**PAUSED**. Existing interview voice providers, N-agent handoffs, and recruiter
workspace isolation are preserved.

## Findings and changes

### CV and interview opening

The application already had a parsed LMS project and FastAPI, React, and
PostgreSQL skills. The opening-question formatter only substituted the project
into questions containing particular placeholder phrases. Coding and debugging
questions did not always contain those phrases, so a loaded CV could go
unmentioned.

The opening now explicitly names the selected CV project and candidate's first
name, names the job, and asks one project-related question appropriate to the
configured competency. CV claims remain background, not scored answer evidence.
Alex's legacy `coding` competency alias now normalizes to
`coding_problem_solving`; the future demo job/template use that canonical key.
The completed interview's template snapshot and duration were not rewritten.

A one-page PDF CV was generated and visually checked at
`output/pdf/Candidate_Software_Developer_Intern_CV.pdf`. It includes only the user's
confirmed name, email, LMS project, and technology details. It does not invent
education, employment, dates, or performance metrics.

CV downloads now use the authenticated application API in both the candidate
portal and HR candidate view. Candidates can download their own application's
CV; another candidate or an unrelated recruiter is denied before storage is
read. Bearer tokens are never attached to external resume links.

### Missing HR and candidate interview report

For completed interview `redacted-runtime-id-5`, the saved source
has nine evaluated answers with complete identity links. The first narrative
request returned `AICREDITS_TIMEOUT` after 60 seconds. No report row or narrative
draft was saved. This shared generation failure explains why neither the HR
report nor candidate feedback was ready.

The existing report model now receives minimal reasoning effort for narrative
formatting. Duplicate raw transcripts and question history are omitted from
that request only when all scored answers' texts are recovered. Every answer,
evidence item, score, round, and coverage gap remains included, and the complete
durable source remains unchanged. Both provider stages log timing and failures.

The HR Reports page now lists recent completed interviews independently of
published report rows. Failed report preparation is visible with a link to its
status and explicit retry action. Reading a report does not generate one.
The candidate still receives only the saved overall rating and three feedback
lines, never the private recruiter assessment.

### Taylor practice feedback

The observed failure belongs to the older demo candidate account, not the demo candidate's
new account. A pending feedback request at 10:38:39Z crossed backend startup at
10:38:46Z. The UI continued polling until cleanup recovered the stopped session.
The original provider response is unknown because pre-restart generation logs
were lost. The old cloud session has ended; no score has been invented for it.

New feedback attempts save their unique request marker and original reviewed
answers before sending the native Agora request. Native generation runs outside
the long session lock. After interruption, authenticated reads and the cleanup
worker can recover already-generated output from that exact request's history.
They never issue a second model request. Attempt, agent, and ownership checks
fence late or concurrent results; partial or unrelated output is rejected.
Validated feedback is persisted before cloud cleanup. Unrecoverable interruptions
show an explicit message explaining that no score was generated.

## Authorization and remaining live work

The PDF exists locally but has **not** been uploaded or parsed. Automatic
approval review rejected that operation because it sends the personal CV to
AICredits without explicit authorization for that transfer. A user approval
question is pending; no alternate upload route was attempted.

A separate approval question is pending for retrying the completed interview's
report from its nine saved answers and evidence. The prepared retry script makes
at most one generation request, verifies HR/candidate projections and ownership,
and checks that the original source and score remain unchanged. It has not run.

No new browser microphone/voice E2E test was performed for this update. The
historical failed Taylor session cannot be presented as a successful recovery.

## Validation and deployment

The final backend suite passed **1,744 tests**, with 35 opt-in/live or isolated
database tests skipped and three existing dependency warnings:

```sh
cd backend
env M1_PROVIDER=mock ORCHESTRATOR_PROVIDER=groq GROQ_API_KEY='' GROQ_M1_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' PYTHONPATH=. venv/bin/pytest -q -rs
```

The final frontend suite passed **62 tests** (`node --test tests/*.test.mjs`),
including rendering a failed completed interview when no report rows exist,
private binary CV downloads, report projections, and feedback presentation.
`npx tsc --noEmit` and `git diff --check` passed. Both Docker production images
built successfully.

Before local deployment, read-only checks found zero Agora interview agents,
zero active/executing auxiliary sessions, and zero in-progress report
generations. Backend and frontend were recreated and both became healthy.

Read-only checks against the deployed APIs confirmed:

- Authenticated HR reports, the report detail route, candidate portal, and
  training pages return HTTP 200. Anonymous HR/portal requests correctly
  redirect to login (HTTP 307); these route checks do not constitute browser
  microphone or client-side interaction testing.
- HR's completed-interview list contains the demo candidate and the correct intern job.
- HR report status is HTTP 200, with `failed`, `AICREDITS_TIMEOUT`, and retryable
  true. This is **not** a ready-report result; generation is pending approval.
- the demo candidate and the job's recruiter download the same existing 763-byte TXT CV
  with HTTP 200. An unrelated candidate receives HTTP 403. The newly generated
  PDF is still local pending the separate upload approval.
- Actual saved application data hydrates one LMS project, three skills, the JD,
  both configured agents, and canonical competencies. Isolated current-source
  rendering produces a first-name, LMS-CV, job-specific opening with one question.
- The completed interview's stored template snapshot remained unchanged.

Evidence files are ignored runtime artifacts under `tmp/voice-diagnostics/`:
`cv-report-training-backend-tests.log`, `cv-report-frontend-tests.log`,
`cv-report-training-restart-check.json`, `cv-report-training-deployment.log`,
`cv-report-demo-readonly-verification.json`, and
`training-interrupted-feedback-diagnosis.json`.

Useful local routes:

- HR: `http://localhost:3000/admin/reports`
- This report's status/retry page:
  `http://localhost:3000/admin/reports/redacted-runtime-id-5`
- Candidate portal: `http://localhost:3000/portal`
- Practice: `http://localhost:3000/training`

Live report generation and a fresh Taylor voice/feedback run were **not**
performed. The user can test voice; no browser-audio success is inferred from
the backend tests. No code was committed or pushed in this update.
