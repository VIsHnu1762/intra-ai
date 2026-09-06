# Contextual follow-up correction — 6 September 2026

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

## Observed failure

Room `redacted-runtime-id-1` used a sample Payment Ledger CV and a Kafka/PostgreSQL job description. That fixture was mistakenly supplied as the user's new test room. It explains the payment-ledger opening; it does not describe the user's real CV.

The candidate's Razorpay SDK answer arrived in the Custom LLM callback. M1 completed successfully, but Meta was bypassed on brief/vague/weak answers. The resulting deterministic database/retry questions ignored the SDK contribution. An M1 finding outside the job's configured competencies could also select a target that was rejected later, discarding its question. A standalone “Hello” was incorrectly analyzed as another answer.

Evidence: `tmp/voice-diagnostics/redacted-runtime-id-1-evidence.json` contains the scoped session/callback/history capture. The observed four callbacks returned HTTP 200; Meta was not used on the affected turns. The failure was in follow-up selection, not missing microphone input or an unreachable tunnel.

## Change

- Brief/vague/weak answers now reach the existing Meta model for contextual question wording. Deterministic policy still requires the current agent, selected competency and appropriate difficulty; it rejects a premature handoff or completion.
- Target selection respects the job's configured competency subset before generation.
- A clear, simple, grounded M1/Meta follow-up is retained instead of being unconditionally overwritten by the question bank. Repetition, exhaustion, difficulty and grounding checks remain active.
- Prompts prioritize the current answer and the candidate's own contribution. A concise SDK answer must not imply that the candidate built the payment provider's internals.
- Standalone greetings are conversational controls and do not create scored interview evidence. Greetings followed by a substantive answer are still analyzed.
- Lexical grounding no longer matches unrelated words solely through a four-letter prefix (for example, integration/interaction). Contradiction details remain available for grounding a clarification. This is a conservative lexical check, not a guarantee of semantic quality.

AICredits remains the provider for both realtime intelligence layers. Agora, session identity, context, Knowledge Graph, handoff and report architecture are unchanged by this correction. No new provider or dialogue model was introduced.

## Verification

The focused regression suite passed **174 tests**. It covers the SDK answer, a short server-log answer, configured targets, model attempts to switch/complete incorrectly, repetition, unrelated questions, existing contradiction handling and greeting controls.

The full backend suite passed **1,574 tests**, with **35 skipped** and **3 existing deprecation warnings**, in 7.68 seconds:

```sh
cd backend
env M1_PROVIDER=mock ORCHESTRATOR_PROVIDER=groq GROQ_API_KEY='' GROQ_M1_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' PYTHONPATH=. venv/bin/pytest -q
```

This test environment disables real provider calls; AICredits responses are mocked in provider/routing contract tests. It does not represent the running service's provider configuration. Logs: `adaptive-followup-focused.log` and `adaptive-followup-backend-tests.log` under `tmp/voice-diagnostics/`.

The backend Docker image built successfully. Before restart, the user confirmed the meeting had ended; the Agora API reported zero agents and the auxiliary session store reported zero active/executing sessions (`adaptive-followup-before-restart.json`).

The local backend was restarted and became healthy. Runtime inspection confirmed the updated graph and greeting classifier were loaded, with both layers still selecting `google/gemini-3.1-flash-lite` through AICredits. Backend health and the new prep page returned HTTP 200.

Replacement room: http://localhost:3000/interview/redacted-runtime-id-2/prep. The session was verified in `CREATED` state, with Alex/Jordan selected and zero candidate projects. Configuration and readiness evidence are saved in `context-followup-user-test-config.json` and `context-followup-user-test-room.json` under `tmp/voice-diagnostics/`.

Fresh browser voice quality after this fix remains for the user's test. No new paid inference benchmark or microphone test was performed. The replacement demo room uses an empty CV and a generic software-developer practice brief, so its opening asks the candidate to describe a recent project. It does not claim to validate real CV extraction. Real recruiter-scheduled sessions retain their saved CV/JD hydration.

**AWS remains PAUSED.**

## Follow-up LMS regression and second correction

The user's test of `redacted-runtime-id-2` still produced the medium-level login/database/availability bank questions after LMS, API and Redis answers. The scoped Agora history confirms the answers arrived and the callbacks completed. M1 classified these answers under `software_architecture`, while the actual questions targeted `system_design`. The first answer was also analyzed against the intervening greeting acknowledgement instead of the opening question. The old logs do not retain the original Meta wording or each replacement flag, so they cannot identify every validator gate that fired.

The adapter now preserves the actual active question across greetings, audio checks, repeats, pauses and service retries. Routing, difficulty and stale-follow-up checks resolve the exact question being answered independently of M1's evidence labels. Grounding includes short technical terms such as LMS/API and the active question's subject. Exact question IDs associate answers with the correct history item without promoting an unrelated competency to mastery. New selection logs record the question source, replacement flags and question fingerprints without logging raw provider response text.

Verification: focused continuity checks **112 passed**; full backend suite **1,596 passed, 35 skipped, 3 existing warnings**, 8.80 seconds. The same offline environment command above was used. Logs: `lms-continuity-focused.log`, `lms-continuity-backend-tests.log`, and `lms-continuity-backend-build.log` in `tmp/voice-diagnostics/`.

At the user's explicit restart request, the old room's Alex agent was stopped and the room marked completed. The new backend became healthy and runtime source inspection confirmed the correction was loaded. Both realtime layers still use AICredits Gemini 3.1 Flash-Lite. New room: http://localhost:3000/interview/redacted-runtime-id-3/prep — created with Alex/Jordan and an empty CV; prep and health returned HTTP 200. Fresh audible question quality remains for the user's test.

## Completed-room log review: framing, ASR continuation and early completion

The user's next run (`redacted-runtime-id-3`) completed at 10:28 UTC. Five captured callbacks returned HTTP 200. Alex and Jordan used the same channel, and Agora history confirmed the handoff. The new selection diagnostics showed Alex's first question came from Meta unchanged (`source=meta`, empty replacement policy). It was nevertheless a broad architecture-and-ownership question, incorrectly accepted at EASY because it fit the word limit and the old compound detector missed “and clarify”.

The next answer ended in “an external service like a—”; the following service name arrived in another ASR segment. The first segment was graded and a debugging question was queued. That question was interrupted, but the second answer segment was then graded as a debugging answer. Finally, Jordan asked who used the project and received a short user-identification answer. The old early-close rule treated low M1 performance plus an EASY objective as sufficient to close each competency, leading to completion after Jordan's first question. This was not a tunnel failure. Evidence is saved in `tmp/voice-diagnostics/voice-segmentation-diagnosis.json` and the two scoped cloud histories in `redacted-runtime-id-3-evidence.json`.

Corrections:

- Reject explicit second requests such as “and clarify/describe/explain”; safely retain one question where possible. Broad architecture walkthroughs do not qualify as EASY solely by word count.
- Hold explicit unfinished connector clauses without scoring or advancing. Rejoin adjacent unfinished ASR messages from the incoming history before evaluating the continuation, preserving the original question. Do not cross a spoken assistant reply or merge an earlier complete answer; full restatements avoid duplication. Empty and conversational control turns remain unassessed.
- Require an explicit admission of inability for early closure of an offered simple objective. Brief relevant answers, low scores alone, uncertainty and mixed contributions continue to a follow-up. Distinct-objective exhaustion remains the finite assessment bound; it never asserts mastery.
- Prompts explicitly credit answers to the question asked, including naming users, and ask for clarification when the project acronym is ambiguous.

Validation: **165 focused tests passed**, followed by **1,667 full backend tests passed, 35 skipped, 3 existing deprecation warnings**, 7.95 seconds. The full suite caught an exception-path regression in the first fragment implementation; parsing now preserves the existing classifier-failure fallback, and the suite passes unchanged for that failure case. The historical observed-conversation test now requires all closures to use objective exhaustion, because its only high-confidence answer names coding constructs rather than admitting inability; its finite-turn, no-repeat, handoff, provenance and no-mastery assertions remain intact. Separate tests retain early closure for explicit supported inability.

Build, safe restart, effective source verification and health checks passed. No new live provider benchmark or browser microphone test was run. Current room: http://localhost:3000/interview/redacted-runtime-id-4/prep (`CREATED`, Alex/Jordan, empty CV, HTTP 200). Fresh audible framing remains for the user's test. AICredits remains selected and **AWS remains PAUSED**.

## Specific information targets and the recruiter-scheduled demo

The next captured conversation (`redacted-runtime-id-4`) exposed an additional
failure: Alex resisted the candidate's correction from “webmaster application”
to “LMS application”. After the candidate described authentication and database
access, the selected fallback asked what happens if an unspecified part of the
whole application stops working. The source trace identifies Meta prose, an M1
contradiction probe, and fallback selection separately; microphone transport did
deliver the candidate's answers. Scoped evidence is in
`tmp/voice-diagnostics/redacted-runtime-id-4-evidence.json` and
`specificity-runtime.log`. Earlier successful transport checks did not validate
the relevance of these questions.

The existing Meta call now selects an exact phrase from the current answer,
one missing information target, a bounded expected answer, and an objective.
Validation rejects invented anchors and repeated targets. A valid information
target can repair broad or compound wording without another LLM call. A specific
existing M1 probe is preferred before the generic question bank. The validated
target is retained in question history and passed to M1 so an answer supplying
one requested field is not penalized for missing unasked system architecture.
The finite objective limits still apply. Structural validation improves
grounding; it cannot prove every generated question is semantically appropriate.

Complete corrections of a spoken project name are acknowledged without scoring
technical competence, consuming a question, or inventing a contradiction. The
question keeps its identity and information target, with its original wording
retained as metadata. Genuine implementation claims still reach M1. Positively
stated new project names reach M1 in an isolated snapshot before evaluation, and
both models see the current project explicitly. CV claims are not rewritten.

Full offline backend validation passed **1,706 tests, 35 skipped**, with three
existing deprecation warnings (`specific-demo-backend-tests.log`). After a final
article/grammar correction in the deterministic question renderer, **51 focused
framing/target tests passed** (`specific-demo-framing-tests.log`). No tests were
removed or weakened. The same offline environment command above was used.

For the requested demo, the real signup/application/scheduling APIs created a
candidate, a published Software Developer Intern job, a reusable 15-minute
Alex/Jordan template, and a scheduled interview. The user-confirmed LMS project,
FastAPI, React and PostgreSQL form the demo CV; unprovided education/employment
claims were omitted. Résumé parsing now honors the selected AICredits M1
transport instead of unconditionally calling old Groq settings. The setup checks
verify login, persisted CV, recruiter ownership, candidate name, linked portal
application, both agents, duration and an immediately open prep page. A regular
scheduled meeting avoids starting the ten-minute instant invitation expiry while
the user prepares the recording. Private account details and precise record IDs
are kept only in ignored `tmp/demo-setup/` artifacts.

The final backend image built and became healthy. The deployed renderer and
AICredits selections were checked in `specific-demo-final-runtime.json`.
`tmp/demo-setup/final-verification.log` confirms the new account can log in and
the linked scheduled interview remains immediately open after the restart.
`tmp/demo-setup/hydration-verification.json` records the persisted LMS project,
application-specific CV and JD hydration without starting voice.

Fresh audible conversation quality remains for the user's test. Provisioning
does not start an Agora agent or claim voice E2E, handoff or report verification
for this new interview. Both realtime models remain AICredits Gemini 3.1
Flash-Lite. **AWS remains PAUSED.**
