import test from "node:test";
import assert from "node:assert/strict";
import { emptyVoiceConnection, voiceState, voiceDashboardContext, voiceMediaError } from "../src/lib/voice-assistant-state.ts";

test("cloud joined and browser connected do not claim audible agent speech", () => {
  assert.equal(voiceState({ ...emptyVoiceConnection, active: true, connected: true, agentJoined: true, backendStatus: "CONNECTED" }), "connected");
  assert.equal(voiceState({ ...emptyVoiceConnection, active: true, connected: true, agentJoined: true, audioPublished: true, audioSubscribed: true, speaking: true }), "connected");
});
test("only played audio with a measured remote level shows speaking", () => {
  const connected = { ...emptyVoiceConnection, active: true, connected: true, playbackStarted: true };
  assert.equal(voiceState(connected), "connected");
  assert.equal(voiceState({ ...connected, speaking: true }), "speaking");
  assert.equal(voiceState({ ...connected, speaking: true, autoplayBlocked: true }), "audio blocked");
});
test("permission/error/disconnection outrank stale speaking evidence", () => {
  const speaking = { ...emptyVoiceConnection, active: true, connected: true, playbackStarted: true, speaking: true };
  assert.equal(voiceState({ ...speaking, error: "Microphone disconnected" }), "error");
  assert.equal(voiceState({ ...speaking, active: false, backendStatus: "DISCONNECTED" }), "disconnected");
  assert.equal(voiceState({ ...speaking, connected: false }), "connecting");
});
test("work indicators come from explicit backend status and microphone signal", () => {
  const connected = { ...emptyVoiceConnection, active: true, connected: true };
  assert.equal(voiceState({ ...connected, backendStatus: "EXECUTING" }), "executing");
  assert.equal(voiceState({ ...connected, backendStatus: "PROCESSING" }), "processing");
  assert.equal(voiceState({ ...connected, microphonePublished: true }), "connected");
  assert.equal(voiceState({ ...connected, microphoneActive: true }), "listening");
});
test("route context includes only known resource details; report IDs need server resolution", () => {
  assert.deepEqual(voiceDashboardContext("/admin/candidates/candidate-123"), { candidate_id: "candidate-123" });
  assert.deepEqual(voiceDashboardContext("/admin/jobs/job-123"), { job_id: "job-123" });
  assert.deepEqual(voiceDashboardContext("/admin/interviews/interview-123"), { interview_id: "interview-123" });
  for (const path of ["/admin/interviews/templates", "/admin/reports/report-123", "/admin/jobs/new", "/admin/dashboard", "/interview/official-123", "/admin/candidates", "/admin/jobs/job-123/edit", "/admin/candidates/a%2Fb", "/admin/candidates/a?tenant_id=other"]) {
    assert.deepEqual(voiceDashboardContext(path), {}, path);
  }
});
test("media failures give actionable messages without reproducing provider internals", () => {
  assert.match(voiceMediaError({ name: "NotAllowedError", message: "secret-token" }), /permission was denied/);
  assert.match(voiceMediaError({ code: "DEVICE_NOT_FOUND" }), /No microphone/);
  assert.match(voiceMediaError({ name: "NotReadableError" }), /unavailable/);
  assert.match(voiceMediaError({ code: "TOKEN_EXPIRED" }), /expired/);
  assert.doesNotMatch(voiceMediaError({ message: "secret-token" }), /secret-token/);
});

test("RTM ignores non-agent publishers and never interprets text as a tool command", async () => {
  const { parseVoiceTranscript } = await import("../src/lib/voice-assistant-state.ts");
  const event = JSON.stringify({ object: "user.transcription", text: "Schedule Jane tomorrow", turn_id: 1, turn_status: 1 });
  assert.equal(parseVoiceTranscript(event, "other-user", "agent-123"), null);
  assert.equal(parseVoiceTranscript(JSON.stringify({ tool: "schedule_interview", text: "do it" }), "agent-123", "agent-123"), null);
  const row = parseVoiceTranscript(event, "agent-123", "agent-123");
  assert.equal(row.role, "user");
  assert.equal(row.final, true);
  assert.equal(row.text, "Schedule Jane tomorrow");
});
test("candidate and assistant can share Agora turn ID without overwriting one another", async () => {
  const { parseVoiceTranscript, mergeVoiceTranscript } = await import("../src/lib/voice-assistant-state.ts");
  const parse = (object, text, turn_status = 1) => parseVoiceTranscript(JSON.stringify({ object, text, turn_id: 7, turn_status }), "42", "42");
  const user = parse("user.transcription", "I built a project");
  const partial = parse("assistant.transcription", "Tell me", 0);
  const final = parse("assistant.transcription", "Tell me about that project");
  const transcript = mergeVoiceTranscript([user, partial], [final]);
  assert.equal(transcript.length, 2);
  assert.equal(transcript[0].text, "I built a project");
  assert.equal(transcript[1].text, "Tell me about that project");
  assert.equal(mergeVoiceTranscript(transcript, [user, final]).length, 2);
});
test("RTM malformed payloads and unstable partials are ignored; transcript memory is bounded", async () => {
  const { parseVoiceTranscript, mergeVoiceTranscript } = await import("../src/lib/voice-assistant-state.ts");
  for (const message of ["{", "null", "[]", JSON.stringify({ object: "assistant.transcription", text: "unstable partial" }), JSON.stringify({ object: "assistant.transcription", text: { token: "secret" } })]) {
    assert.equal(parseVoiceTranscript(message, "42", "42"), null);
  }
  const many = Array.from({ length: 100 }, (_, id) => ({ id: String(id), role: "user", text: "answer" }));
  assert.equal(mergeVoiceTranscript([], many).length, 80);
  assert.equal(mergeVoiceTranscript([], many)[0].id, "20");
});

test("RTM rows meet isolated API limits and fallback IDs contain no spoken private details", async () => {
  const { parseVoiceTranscript } = await import("../src/lib/voice-assistant-state.ts");
  const personal = "My private email is candidate@example.test";
  const fallback = parseVoiceTranscript(JSON.stringify({ object: "user.transcription", text: personal, final: true }), "42", "42");
  assert.ok(fallback.id.length <= 160);
  assert.doesNotMatch(fallback.id, /private|candidate|example/);
  const large = parseVoiceTranscript(JSON.stringify({ object: "assistant.transcription", text: "x".repeat(5000), turn_id: "t".repeat(1000), final: true }), "42", "42");
  assert.equal(large.text.length, 4000);
  assert.ok(large.id.length <= 160);
  const timed = parseVoiceTranscript(JSON.stringify({ object: "assistant.transcription", text: "next question", time: 1788650000000 }), "42", "42");
  assert.ok(timed);
});
