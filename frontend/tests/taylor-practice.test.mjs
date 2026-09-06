import test from "node:test";
import assert from "node:assert/strict";
import { practiceScore, practiceOptions } from "../src/lib/taylor-practice.ts";

test("practice score is displayed only for ready, valid numerical feedback", () => {
  assert.equal(practiceScore({ status: "ready", indicative_score: 76.4 }), 76);
  assert.equal(practiceScore({ status: "ready", indicative_score: 0 }), 0);
  for (const value of [undefined, null, "76", NaN, Infinity, -1, 101]) assert.equal(practiceScore({ status: "ready", indicative_score: value }), null);
  for (const status of ["requesting_feedback", "insufficient_evidence", "unavailable"]) assert.equal(practiceScore({ status, indicative_score: 76 }), null);
});

test("practice setup honors candidate role preference, falls back to selected job, and never invents a role", () => {
  assert.deepEqual(practiceOptions("Frontend Intern", "intern", "Senior Full Stack Engineer"), { experience_level: "intern", target_role: "Frontend Intern" });
  assert.deepEqual(practiceOptions("  ", "junior", "  Backend Engineer  "), { experience_level: "junior", target_role: "Backend Engineer" });
  assert.deepEqual(practiceOptions("", "intern"), { experience_level: "intern" });
});

test("Taylor latency logs one observed remote-audio transition per final user turn", async () => {
  const { createPracticeLatencyTracker } = await import("../src/lib/taylor-practice.ts");
  const tracker = createPracticeLatencyTracker();
  assert.equal(tracker.remoteAudio(true, 10), null); // Greeting has no candidate turn.
  tracker.remoteAudio(false, 20);
  tracker.finalUserTranscript("turn-1", 100);
  tracker.finalUserTranscript("turn-1", 150); // Duplicated final does not reset timing.
  assert.equal(tracker.remoteAudio(true, 450), 350);
  assert.equal(tracker.remoteAudio(true, 500), null);
  tracker.remoteAudio(false, 600);
  assert.equal(tracker.remoteAudio(true, 700), null); // Pause within the same reply.
  tracker.finalUserTranscript("turn-2", 800);
  assert.equal(tracker.remoteAudio(true, 850), null); // Already-speaking audio is not a new response.
  tracker.remoteAudio(false, 900);
  assert.equal(tracker.remoteAudio(true, 1100), 300);
});

test("finish silences SDK and native audio before requesting feedback, and leaves cloud alive until response", async () => {
  const { completePracticeFeedback, releasePracticeAudio } = await import("../src/lib/taylor-practice.ts");
  const events = [];
  let resolveFeedback;
  const cloudFeedback = new Promise(resolve => { resolveFeedback = resolve; });
  const result = completePracticeFeedback({
    releaseLocal: () => releasePracticeAudio({ dispose: () => events.push("sdk-dispose") }, [
      { getMediaStreamTrack: () => ({ stop: () => events.push("microphone-stop") }) },
      { getMediaStreamTrack: () => ({ stop: () => events.push("remote-audio-stop") }) },
    ]),
    flushTranscript: async () => { events.push("transcript-flush"); },
    requestFeedback: () => { events.push("read-history-and-score"); return cloudFeedback; },
    closeCloud: async () => { events.push("cloud-end"); },
    isCancelled: () => false,
    errorMessage: () => "Unavailable",
  });
  await Promise.resolve();
  assert.deepEqual(events, ["sdk-dispose", "microphone-stop", "remote-audio-stop", "transcript-flush", "read-history-and-score"]);
  resolveFeedback({ status: "ready", indicative_score: 72 });
  assert.deepEqual(await result, { feedback: { status: "ready", indicative_score: 72 }, cloudClosed: true });
  assert.equal(events.at(-1), "cloud-end");
});

test("pagehide during transcript flush ends the cloud without starting scoring", async () => {
  const { completePracticeFeedback } = await import("../src/lib/taylor-practice.ts");
  let cancelled = false;
  let completeFlush;
  let ended = 0;
  const result = completePracticeFeedback({
    releaseLocal: () => {},
    flushTranscript: () => new Promise(resolve => { completeFlush = resolve; }),
    requestFeedback: async () => assert.fail("Scoring must not start after pagehide"),
    closeCloud: async () => { ended++; },
    isCancelled: () => cancelled,
    errorMessage: () => "Unavailable",
  });
  cancelled = true;
  completeFlush();
  assert.equal((await result).feedback.status, "unavailable");
  assert.equal(ended, 1);
});

test("a best-effort transcript failure cannot skip authoritative cloud feedback or cleanup", async () => {
  const { completePracticeFeedback } = await import("../src/lib/taylor-practice.ts");
  const events = [];
  const result = await completePracticeFeedback({
    releaseLocal: () => events.push("local-end"),
    flushTranscript: async () => { throw new Error("Transcript unavailable"); },
    requestFeedback: async () => { events.push("score"); return { status: "insufficient_evidence", indicative_score: null }; },
    closeCloud: async () => { events.push("cloud-end"); },
    isCancelled: () => false,
    errorMessage: () => "Unavailable",
  });
  assert.deepEqual(events, ["local-end", "score", "cloud-end"]);
  assert.equal(result.cloudClosed, true);
});

test("lost feedback response still attempts stop and retains cleanup failure for retry", async () => {
  const { completePracticeFeedback } = await import("../src/lib/taylor-practice.ts");
  let ended = 0;
  const result = await completePracticeFeedback({
    releaseLocal: () => {},
    requestFeedback: async () => { throw new Error("network timeout"); },
    closeCloud: async () => { ended++; throw new Error("network offline"); },
    isCancelled: () => false,
    errorMessage: () => "Saved feedback could not be retrieved.",
  });
  assert.equal(ended, 1);
  assert.equal(result.cloudClosed, false);
  assert.equal(result.feedback.status, "unavailable");
  assert.equal(result.feedback.indicative_score, null);
});

test("SDK teardown exceptions cannot leave captured browser microphone or remote audio running", async () => {
  const { releasePracticeAudio } = await import("../src/lib/taylor-practice.ts");
  let stops = 0;
  assert.doesNotThrow(() => releasePracticeAudio({ dispose: () => { throw new Error("SDK failure"); } }, [
    { getMediaStreamTrack: () => ({ stop: () => { stops++; } }) },
    { getMediaStreamTrack: () => ({ stop: () => { stops++; } }) },
  ]));
  assert.equal(stops, 2);
});

test("an in-progress feedback result preserves the cloud agent for saved-result polling", async () => {
  const { completePracticeFeedback } = await import("../src/lib/taylor-practice.ts");
  const result = await completePracticeFeedback({
    releaseLocal: () => {},
    requestFeedback: async () => ({ status: "requesting_feedback" }),
    closeCloud: async () => assert.fail("Cloud must remain alive while feedback is being generated"),
    isCancelled: () => false,
    errorMessage: () => "Unavailable",
  });
  assert.equal(result.awaitingFeedback, true);
  assert.equal(result.cloudClosed, false);
});

test("an unexpected local-release failure prevents scoring and still closes cloud resources", async () => {
  const { completePracticeFeedback } = await import("../src/lib/taylor-practice.ts");
  let closed = false;
  const result = await completePracticeFeedback({
    releaseLocal: () => { throw new Error("Local teardown failure"); },
    requestFeedback: async () => assert.fail("Do not run scoring if local release failed"),
    closeCloud: async () => { closed = true; },
    isCancelled: () => false,
    errorMessage: () => "Unavailable",
  });
  assert.equal(closed, true);
  assert.equal(result.feedback.status, "unavailable");
});

test("feedback count distinguishes sampled answers from all recorded answers", async () => {
  const { practiceAnswerCount } = await import("../src/lib/taylor-practice.ts");
  assert.equal(practiceAnswerCount({ status: "ready", answered_questions: 14, reviewed_answers: 6 }), "Feedback based on 6 of 14 practice answers.");
  assert.equal(practiceAnswerCount({ status: "ready", answered_questions: 4, reviewed_answers: 4 }), "Feedback based on 4 practice answers.");
  assert.equal(practiceAnswerCount({ status: "ready", answered_questions: 14 }), "14 practice answers recorded.");
  assert.equal(practiceAnswerCount({ status: "ready", answered_questions: -1 }), null);
});
