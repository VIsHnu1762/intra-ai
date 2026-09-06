# Conversation continuity and Groq credential update

Date: 6 September 2026. Scope: the working tree's live interview dialogue, clarification, progression, and provider-error behavior. AWS remains **PAUSED**.

Links into `tmp/voice-diagnostics` refer to local test artifacts, which are excluded from Git along with credentials and generated documents.

## Findings from the user's live sessions

The original failing room was `voice-personalized-1788647921`, with Alex cloud generation `A44CJ53DT42NC42AE89NJ84PM47CP34R`. Weak-answer guardrails repeatedly kept the same interviewer active. “Easy” question templates still spoke abstract evaluation labels and lists of missing details. Clarification requests were sometimes scored as answers. The configured Jordan card did not prove that Jordan's physical agent had joined or spoken.

The follow-up browser room, `voice-clear-1788649504`, exposed additional failures. Alex generation `A44CT39PR29PW52FY88JC74EC76JM94N` produced one greeting, then received real candidate speech. The capture contains **10 HTTP 200 Custom LLM callbacks**, while backend logs contain **7 completed M1 analyses and 2 Groq 429 errors**. HTTP 200 on a callback therefore did not establish successful model processing. The old M1 error handler returned the same “technical details and trade-offs” question on each error, concealing the outage and causing repetition.

The user explicitly reported that audio **did not break in this follow-up test**. The remaining complaint was disconnected questions: “I built LLM software” was followed by a generic question instead of a question about that software. “What are you asking specifically? I can't understand” and “What?” also reached assessment; unfinished ASR fragments advanced the interview.

Evidence: [original audio diagnosis](../tmp/voice-diagnostics/personalized-audio-diagnosis.json), [follow-up callbacks and cloud history](../tmp/voice-diagnostics/voice-clear-1788649504-evidence.json), [follow-up runtime log](../tmp/voice-diagnostics/voice-clear-runtime.log). These are local diagnostic artifacts, not a certification of the complete recruiting workflow.

## Implemented behavior

- Explicit project mentions persist as conversational context. “I built LLM software” leads to “What task does your LLM software help someone complete?” Subsequent input, output-check, and limitation questions stay with that project. Related technical and product competencies use it too. Mentioning Redis or Kafka as a dependency cannot replace the project. CV text remains background information, not scored interview evidence.
- Spoken questions are short and contain one question. When safe, a compound model-authored question retains its first complete question, preserving its original context. Other invalid questions use concrete, bounded objectives. Unrelated examples announce the topic change.
- Bare “What?”, clarification with “specifically/exactly,” and dash-separated speech repairs bypass M1, scoring, graph writes, and progression. Clearly unfinished fragments remain silent until the candidate continues. Genuine knowledge admissions and complete technical answers still receive assessment.
- Stable objective IDs prevent fresh wording or changing gap labels from creating endless retries. Insufficient assessment remains explicitly insufficient; it does not become mastery. Exhaustion advances to another configured objective or registered interviewer, including N-agent configurations.
- M1/context changes are staged across asynchronous routing. Cancellation before a decision commits cannot leave new evidence, difficulty, or an unspoken question in canonical interview state.
- Provider errors now disclose a service pause instead of inventing a question. The UI displays “Interview paused — service unavailable.” Groq retry hints are retained without logging keys or raw quota messages. A cooldown blocks repeated model calls; an explicit “continue” after it retries the original unevaluated answer, not the control word.
- Roster labels distinguish selected agents from physical RTC presence. Browser diagnostics include packet loss, discarded packets, receive delay, and freeze duration. No speculative audio/VAD changes were made after the user's audio clarification.

Relevant source: `backend/app/custom_llm/{adapter,classifier,service_pause}.py`, `backend/app/orchestrator/{graph,policies,questions,assessment,service}.py`, `backend/app/interview_intelligence/provider.py`, `backend/app/integrations/groq_client.py`, and the candidate interview page/audio lifecycle helper.

## Replacement credentials

The two newly supplied keys were saved only in the backend environment: key 1 for `GROQ_ORCHESTRATOR_API_KEY`, key 2 for `GROQ_API_KEY`. The existing analysis component is named **M1** in this codebase; no additional M2/third model was introduced. Both roles retain `openai/gpt-oss-20b`.

Both keys returned **HTTP 200** in fixed, non-sensitive credential smoke tests. The first structured-output smoke attempt for the Meta key returned 400; a plain-text smoke request succeeded. This verifies credentials/model access, not a complete interview or structured-output reliability. [Sanitized results](../tmp/voice-diagnostics/replacement-keys-verification.json).

Automatic approval review rejected a separate scripted context-heavy provider check because the payload was insufficiently verified for sensitive candidate data. The completed safer check sent only a fixed “ready” prompt, with no CV, JD, or interview payload. That rejected script was not rerun. The user subsequently entered the application and performed the real browser interview documented below; its live M1 requests used the replacement credential.

## Confirmed browser interview

The user entered `voice-clear-1788650221`, channel `intra-voice-clear-1788650221`, and spoke to both interviewers. Alex's cloud generation was `A44CK23WF88RW25AK43XP94JA57KL59K`; Jordan's was `A44CD43VE42FA84TD79NR64DH86XD82N`.

After the candidate said “I personally built a LMS software,” Alex asked what task the LMS helped someone complete, what information it needed to keep, and how one request moved through it. At **23:23:34 UTC on 5 September**, the backend recorded a real `alex → jordan` switch. Jordan's cloud history records his greeting with speech start/end timestamps, referring to the candidate's LMS, followed by “How would you learn what users need from your LMS?” Further spoken follow-ups stayed with the LMS and its users.

The final capture contains **35 HTTP 200 Custom LLM callbacks**, **22 successful Groq/M1 analyses**, **22 orchestrator decisions**, and **22 completed KG writes with no logged KG write failures**. All 22 routing decisions used deterministic guardrails (`llm_used=False`); this run does **not** verify a live Meta-Orchestrator model decision with the new key. Its credential smoke test is separate evidence.

The user explicitly confirmed **“Yes, clear and connected”** when asked whether both voices were clear and the questions connected to the project, and subsequently reported that the overall flow was working well. Cloud history includes candidate ASR and Jordan's completed assistant speech intervals. A complete exported browser `user-published → subscribe → play` event trace was not collected for this room; browser audibility is confirmed by the user, not inferred solely from cloud logs.

A final read-only Neo4j query at **23:29:05 UTC** found **1 round, 22 questions, 22 answers, and 10 evidence nodes** under the isolated test candidate. Every evidence node had a candidate-scoped answer, every answer had a question, and evidence IDs were unique. These counts prove persistence/provenance, not perfect semantic evaluation: the repeat-request miss below was found in this same fixture. The real candidate's memory was not used as the test write target.

Evidence: [live summary](../tmp/voice-diagnostics/relevance-live-validation-summary.json), [callbacks and cloud history/turns](../tmp/voice-diagnostics/voice-clear-1788650221-evidence.json), [runtime](../tmp/voice-diagnostics/relevance-latest-runtime.log), [Neo4j provenance](../tmp/voice-diagnostics/relevance-live-kg-summary.json).

## Remaining provider pauses and final repeat-request fix

The confirmed session still encountered **five Groq HTTP 429 tokens-per-minute responses**, with provider retry delays of **8, 13, 10, 8, and 1 seconds**. The latest occurred at **23:25:25 UTC**. After the candidate said “Continue,” M1 succeeded at **23:25:37 UTC**, and Jordan spoke another question. The new credentials are valid; replacing a key does not establish that the runtime has enough quota for uninterrupted interviews. No quota or billing change was made.

Reviewing this last pause revealed an avoidable model call: **“Can you come again?”** was classified as an answer. The final patch recognizes this request and polite variants, repeats the active question, and bypasses M1, routing, scoring, and KG writes. Reported speech and substantive answers mentioning “come again” remain assessable. **141 targeted tests passed** after this patch, including 12 new repeat-request/negative-control cases. The backend was rebuilt and restarted after the user confirmed they had finished the test. The restarted backend returned healthy, and its loaded classifier returned `REPEAT_QUESTION` for the exact live utterance ([health check](../tmp/voice-diagnostics/relevance-repeat-health.json)). This narrow final patch has regression coverage and runtime verification; a new human voice test after it is not claimed.

The isolated room was closed successfully, stopping Jordan, with `report_status=not_applicable`. [Stop result](../tmp/voice-diagnostics/relevance-confirmed-stop.json), [targeted tests](../tmp/voice-diagnostics/relevance-repeat-request-tests.log), [final backend build](../tmp/voice-diagnostics/relevance-repeat-build.log), [restart](../tmp/voice-diagnostics/relevance-repeat-restart.log). Provider limits remain a real reliability limitation; the repeat-request fix removes unnecessary calls but does not claim to eliminate 429s.

## Validation and limits

- Full backend suite before the final narrow repeat-request patch: **750 passed, 13 skipped, 3 dependency warnings in 110.08 seconds**, exit 0. [Regression log](../tmp/voice-diagnostics/relevance-verified-backend-tests.log). Command from `backend`: `GROQ_ORCHESTRATOR_API_KEY='' venv/bin/python -m pytest tests --ignore=tests/test_real_groq_integration.py -q`. This disables the live orchestration key for ordinary regression fixtures; separate credential checks are documented above. Skips are the 12 legacy Ollama cases and one opt-in Neo4j case. No tests were deleted; obsolete wording assertions were updated to concrete scenario, grounding, and single-question requirements while retaining routing/scoring/error guarantees.
- Project/grounding regressions: **106 passed**. Classifier/clarification/service-pause regressions: **119 passed**. Provider rate-limit/lifecycle/evidence-identity regressions: **42 passed**. These overlap with the full suite and must not be added together.
- Frontend audio lifecycle: **10 passed**. TypeScript check passed. Backend and frontend Docker builds passed; local services were restarted with the new keys. [Audio tests](../tmp/voice-diagnostics/relevance-audio-tests.log), [TypeScript](../tmp/voice-diagnostics/relevance-typescript.log), [build](../tmp/voice-diagnostics/relevance-final-build.log).
- The old isolated room was closed with `report_status=not_applicable`; it was not represented as a durable candidate report. A fresh room was prepared from the existing application CV/JD under a separate test candidate ID: [room details](../tmp/voice-diagnostics/conversation-fix-room.json).
- Fresh room: `http://localhost:3000/interview/voice-clear-1788650221/prep`. Its preparation page returned HTTP 200; the backend health check passed. Backend runtime configuration confirmed Groq GPT-OSS-20B and two distinct configured credentials without exposing values. [Health](../tmp/voice-diagnostics/relevance-final-health.json), [services](../tmp/voice-diagnostics/relevance-final-services.json). [Offline linked-question examples](../tmp/voice-diagnostics/relevance-question-examples.json) demonstrate the exact LLM-software follow-ups; they are explicitly not live audio evidence.
- Browser question continuity and a physical Jordan handoff were verified as documented above. The later repeat-request patch was verified by focused regressions and the restarted runtime; it has not had a separate human voice retest.
- Full durable application → completed interview → final evidence-backed report remains outside this isolated voice fixture's validation. **AWS is still PAUSED.**
