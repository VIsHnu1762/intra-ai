# Taylor native practice and final coaching

Publication note: personal details and live runtime identifiers are redacted;
exact correlation records remain in ignored local diagnostics.

Date: 6 September 2026. Branch: `final`. Working-tree changes; no commit or push in this task. AWS remains **PAUSED**.

## Diagnosis

The user reported a 10–12 second delay after telling Taylor they were preparing for a software developer internship. In live session `redacted-runtime-id-28`, the backend observed repeated `get_training_context` calls roughly every four seconds, with individual calls taking about 1.5–2.2 seconds. Taylor's transcript announced that it was fetching CV details instead of continuing practice. The exact perceived audio delay was not independently timed.

Taylor already used the saved Agora Studio model. The unnecessary work was the repeated context tool loop, not the official interview Custom LLM pipeline. No Groq, Supabase, Neo4j, Alex or Jordan configuration was changed to address it.

## Current flow

1. Candidate optionally selects an application and target role, and chooses an experience level (intern by default).
2. Server authorizes the candidate/application, loads the saved parsed CV and selected JD once, and builds a bounded native-model prompt. An explicit practice role takes priority over the saved job title.
3. Agora starts Taylor in its isolated training project. Taylor has tools explicitly disabled and an empty MCP list, overriding inherited Studio tool configuration. No public tool tunnel or application Custom LLM callback is required for Taylor.
4. A single initial greeting uses the candidate's first name. With a known role it asks about a small project; otherwise it asks which role they want. The prompt requests one short, connected question per turn at the chosen level.
5. **Finish & Get Feedback** stops browser microphone, RTC/RTM and playback first. The server reads the running agent's native history, then asks that same native model for final coaching through `/think`.
6. A fresh request marker must appear in history before feedback is accepted. The native response uses 14 fixed markers, from `INTRA_FEEDBACK_BEGIN` through `INTRA_FEEDBACK_END`, enclosing the summary, three scores/reasons, one strength, one improvement and one example linked to its answer index. The parser requires every marker exactly once in order and rejects extra or trailing content. It accepts removed whitespace between fields, requires ASCII integer scores/indices, and validates the resulting object against the existing strict schema and actual source answers. Legacy complete JSON remains supported without repairing missing quotes or braces. The server then closes the cloud agent. The UI displays an indicative practice score and coaching beside the actual source answers.

This uses Agora's documented [join overrides](https://docs.agora.io/en/api-reference/api-ref/conversational-ai/join), [native thinking request](https://docs.agora.io/en/api-reference/api-ref/conversational-ai/think), and [running-agent conversation history](https://docs.agora.io/en/api-reference/api-ref/conversational-ai/history). A successful `/think` acknowledgment alone is not proof of generated feedback or audible speech.

## Evidence and lifecycle safeguards

- CV claims are background, not proof of answer quality. Coaching evaluates recorded practice answers only. The prompt requests no more than 110 words across the feedback values and scores relevance against the actual question, not merely the same project. Practice scores remain model-generated coaching, not a calibrated hiring assessment.
- A suggested answer must match complete sentences from its selected source answer in their original order, with only explicit `[add your actual ...]` prompts added. The comparison preserves punctuation, operators, numbers and negations while allowing case/whitespace normalization. A rewrite that fails this check becomes a deterministic **Answer template** containing the candidate's own wording and missing-detail prompts; the valid score and other coaching are retained. Long template excerpts are explicitly labelled, with the full recorded answer shown separately. The UI tells candidates to fill brackets only with true details. No second model is used for this boundary.
- Role selection and clarification requests are excluded from scoring; a genuine uncertain answer such as “I don’t know” remains an attempt.
- At least two eligible answers are needed. Up to six are sampled across the available history. Scores average clarity, relevance and specificity, each validated as an integer from 0 to 100.
- Incomplete or invalid output, insufficient answers, timeouts and interrupted sessions never receive a fabricated score. Browser transcripts do not substitute for native provider history when scoring.
- Concurrent finish retries return the saved pending/completed result. Generation is bounded to 35 seconds. A private 65-second recovery deadline handles a worker disappearing mid-request without generating another score.
- The cloud agent stays alive during feedback generation. Terminal feedback triggers cleanup; cleanup failures remain queued for retry. Page exit ends the session, and local tracks are closed even if SDK teardown fails.
- Session transcripts and feedback use the auxiliary Redis namespace with a 24-hour record TTL. No official interview scores, application status, candidate evidence or knowledge graph entries are written by practice feedback.

## Automated validation

Commands from `backend/`:

```sh
M1_PROVIDER=mock GROQ_API_KEY='' GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests -q --tb=short
```

Result on the final grounded implementation: **1,088 passed, 17 skipped, 3 warnings in 4.07 seconds**. The warnings are existing dependency deprecations. Coverage includes context bounds, role/level overrides, native adapter contracts, normalized marker boundaries, rejected missing/duplicate/out-of-order/unknown fields, strict ASCII scores/indices, legacy JSON validation without repairs, canonical source-answer matching, ownership, pending retries, worker recovery and cleanup. Grounding regressions reject invented fields, facts borrowed from another answer, dropped negations and changed technical symbols such as `C++`, `-5`, `==`, `!=` and decimal values. The concurrency contract accepts a prompt pending response and then the same saved terminal feedback.

A preliminary unqualified pytest invocation inherited configured Groq credentials: **1,074 passed, 13 skipped, 3 failed**. Those failures were live Groq tests reporting `ConnectError`; they do not establish live provider functionality. The isolated command above passed without changing `.env`.

Frontend: **34 Node tests passed**, including React-rendered source/template separation, escaping and legacy response compatibility. TypeScript, targeted ESLint and production build passed. Docker backend and frontend builds passed and were loaded locally. The retry control accurately says **Check Saved Feedback** because it retrieves the saved result. `git diff --check` passed. A scan of 74 changed-source/browser-bundle files found no configured sensitive credential values.

Logs are under ignored `tmp/voice-diagnostics/`: `taylor-grounded-backend-tests.log` (final isolated backend run), `taylor-grounded-backend-build.log`, `taylor-grounded-frontend-build.log`, `taylor-native-backend-tests-final.log` (earlier marker run), and `taylor-practice-frontend-build.log`.

Implementation: `backend/app/voice/{agora,context,feedback,models,routes,service}.py`; Taylor training page, feedback panel, voice hook and practice helpers under `frontend/src/`. Tests include `test_training_context.py`, `test_training_feedback.py`, and the updated auxiliary adapter/session/MCP suites. The official interview implementation was not edited.

## Live validation

The updated `/training` page was checked in Chrome while signed in as the demo candidate. It displays the selected application, explicit Software Developer Intern target, intern level, and Start Training. Automated tests alone do not establish microphone, ASR or audible playback success.

### User microphone session

The user spoke in session `redacted-runtime-id-29`, channel `redacted-runtime-id-35`, agent `redacted-runtime-id-32`. It started at 06:22:36 UTC and ended at 06:26:15 UTC on 6 September. Startup confirmed CV and selected job context were present. The browser transcript showed connected follow-ups about the user's LMS application, use of a coding agent, and how they structured instructions for that agent.

After the session ended, Agora's `/turns` endpoint recorded one completed greeting, 12 voice-input turns, seven completed ASR/LLM/TTS turns, five interruptions caused by new speech, and zero provider errors. Completed voice-turn provider `e2e` latency ranged from **1,947 to 2,239 ms**, averaging **2,071 ms**. LLM time to first token was 533–865 ms; TTS time to first byte was 132–287 ms. These are provider measurements, not independently timed browser speaker latency. The user's confirmation of hearing clear, faster replies remains pending.

The first two completed voice turns had 2,052/1,947 ms provider response latency and 6,811/11,128 ms recorded playback duration. This supports real microphone input, recognition, model response and speech generation. Browser captions corroborated the conversation; captions and provider playback records alone do not prove what reached the user's speakers. Artifacts: `tmp/voice-diagnostics/taylor-browser-voice-metrics-summary-039b584c.json` and the corresponding safe provider turn capture.

This microphone session ran the earlier JSON feedback request and ended with feedback unavailable. Its voice evidence must not be presented as successful final feedback validation. Redis confirmed `DISCONNECTED` and Agora confirmed `STOPPED` before the fixed-marker backend was deployed.

### Issues caught by live native tests

- An initial diagnostic selected an optional database column absent from this schema. The diagnostic was corrected; the application schema was not changed.
- Injecting a synthetic answer before Taylor finished speaking caused Agora to shorten the previous assistant question in native history. The test was paced to let questions finish. Both fictional answers were then present and eligible for feedback. No score was invented for the incomplete-question runs.
- A headless test approached Agora's 60-second empty-channel timeout. Later diagnostics used a 120-second idle timeout for their own newly created test agent only, through the same authorized service. The deployed browser session configuration remains unchanged at 60 seconds.
- Native feedback arrived with completed prose but missing final JSON delimiters. In one run it stopped at 2,495 characters; a compact request still stopped at 1,134 characters. Both returned unavailable with no score. The fifth capture ended inside the last explanation string, without its closing quote/braces. This motivated the explicit trailing completion marker; no provider, token limit or TTS configuration was changed speculatively.
- A sixth capture included the trailing marker's words but still lacked final JSON delimiters and the marker's period. That disproved the suffix workaround. The current format uses ordered text fields and a final word marker; it does not depend on retained closing punctuation or reconstruct incomplete JSON.
- A rejected trial rewrite introduced an unstated timestamp field. The prompt was tightened to require stated facts or explicit placeholders for new details. Generated examples remain suggestions that the candidate should check, not verified interview evidence.

The diagnostic uses clearly fictional Python task-tracker answers. Text injection into `/think` tests the native model/history/feedback path; it is **not** microphone, ASR, RTC playback or user-audibility verification. Trial artifacts are retained under `tmp/voice-diagnostics/taylor-native-practice-*`.

### Fixed-marker native feedback result

The seventh native diagnostic **passed the feedback transport and lifecycle checks** in session `redacted-runtime-id-30`, channel `redacted-runtime-id-36`, agent `redacted-runtime-id-33`. It started through the real authorized voice service with a diagnostic-only 120-second headless idle allowance; it used the deployed authenticated HTTP endpoints for feedback, readback, repeated submission and cleanup. No additional model, Custom LLM callback or MCP tool was used.

Two clearly fictional task-tracker answers were injected through the same Studio agent's native `/think` API. The provider history preserved both eligible question/answer pairs after the test allowed the preceding questions time to finish speaking. A fresh server feedback-request marker preceded the response. The response contained 1,005 characters and all 14 field markers exactly once in the required order, including `INTRA_FEEDBACK_END`; the actual strict feedback parser accepted it without adding or repairing punctuation.

The feedback endpoint returned **ready in 13.045 seconds**, with an indicative practice score of **78/100**: clarity 80, relevance 85, specificity 70. Two answers were reviewed. Reading the saved feedback and repeating the finish request both returned exactly the same result. A separate read-only comparison verified that its cited question and answer excerpt exactly matched the first recorded fictional question and answer. The session returned `DISCONNECTED`, cleanup returned HTTP 200, Agora subsequently reported `STOPPED`, and the application's status remained unchanged. Total diagnostic time was 45.747 seconds.

The provider measured 684 ms LLM time to first token and 254 ms TTS time to first byte on the feedback turn, with a 2,250 ms provider `e2e` metric. These differ from the 13.045-second HTTP feedback completion time. The feedback turn was interrupted by `api_leave` after the structured result was saved; this test does not claim that the entire feedback text played aloud. It is a native text-injection and HTTP reporting test, **not** browser microphone or audibility validation. The earlier real microphone session is documented separately above.

**Grounding limitation caught by this run:** although the source question and answer binding were exact, the model's proposed example added a `created date` field that neither fictional answer stated. This historical result proves the fixed-marker integration and saved result lifecycle, not factual correctness of every generated example. The source-sentence/placeholder guard described above was subsequently implemented and deployed. Its successful eighth live diagnostic below supersedes this earlier content-quality result.

Sanitized artifacts under `tmp/voice-diagnostics/`: `taylor-native-practice-summary-seventh.json`, `taylor-native-practice-stages-seventh.jsonl`, `taylor-native-practice-generated-feedback-seventh.txt`, `taylor-native-practice-source-binding-seventh.json`, and `taylor-native-practice-turns-seventh.json`. They retain the diagnostic outcome, generated coaching and safe metadata without raw CV content or credentials.

### Final grounded native feedback result

The eighth diagnostic **passed on the deployed grounded implementation** in session `redacted-runtime-id-31`, channel `redacted-runtime-id-37`, agent `redacted-runtime-id-34`. It used the real persisted candidate/application authorization and the same saved Studio agent, with the same diagnostic-only 120-second headless allowance. There were no MCP calls or independent LLM provider calls.

The two fictional task-tracker answers and their preceding questions were present in native history without adapter truncation. Taylor's questions stayed on that project: task fields, representation of task completion, then organizing automated tests for the add-task function. The feedback response followed the fresh request marker and contained 1,062 characters with all 14 field markers exactly once in order. The strict parser validated it without punctuation repair.

The authenticated feedback endpoint returned **ready in 12.971 seconds**, reviewing two answers and producing an indicative score of **67/100**: clarity 75, relevance 65, specificity 60. Its relevance explanation correctly identified that the second fictional answer discussed related validation improvements rather than answering how task completion was represented. This checks relevance against the actual question, while the score remains uncalibrated practice coaching.

The returned example had `example_kind: template`. Its cited question and full answer excerpt exactly matched the canonical recorded fictional exchange. The example exactly equalled that original answer plus the two explicit `[add your actual ...]` prompts; the source-only validator also passed. No invented `created date` or timestamp appeared in the displayed example. This verifies the deployed server boundary for the observed unsafe native rewrite, rather than claiming that the model itself always generates grounded examples.

GET readback and repeated POST finish returned the exact saved feedback. The session was `DISCONNECTED`, explicit cleanup returned HTTP 200 with `DISCONNECTED`, and the application's status remained unchanged. Total diagnostic time was 44.441 seconds. There is no remaining feedback transport or source-grounding blocker demonstrated by this run.

This is a **native text-injection and authenticated HTTP integration test**, not a new microphone, ASR, RTC playback or audible-greeting test. It does not supersede the separate limitations of the earlier real microphone session or the pending user audibility confirmation. The 12.971-second endpoint duration measures completed feedback generation and persistence, not provider first-token latency or speaker latency.

Sanitized artifacts under `tmp/voice-diagnostics/`: `taylor-native-practice-summary-eighth.json`, `taylor-native-practice-stages-eighth.jsonl`, `taylor-native-practice-generated-feedback-eighth.txt`, and `taylor-native-practice-feedback-body-eighth.json`. The last file is the actual saved API response containing only the fictional diagnostic source answers and generated coaching, for isolated UI review. All diagnostic sessions have been cleaned up; no further cloud probes were started.

The actual eighth saved response was rendered through the real React feedback panel, shared helpers and application styles. Visual inspection found no clipping; the recorded answer was separate from the **Answer template**, and the instructions to fill brackets only with true details were visible. This was an isolated static rendering of synthetic feedback, not browser microphone E2E. Artifacts: `taylor-feedback-panel-eighth.html`, `taylor-feedback-panel-eighth.png`, and `taylor-feedback-ui-qa-eighth.json` under the same diagnostics directory. The final **34 passing frontend tests** are logged in `taylor-feedback-final-34-frontend-tests.log`.
