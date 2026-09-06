import test from "node:test";
import assert from "node:assert/strict";
import { createAgentUidFilter, createAudioLifecycle, createIdempotentAudioPlayer, microphoneDiagnostics, remoteAudioQualityDiagnostics, agentPresenceLabel } from "../src/lib/agora-audio-lifecycle.ts";

test("selected agents are allowed across numeric/string SDK UIDs; another candidate tab is excluded", () => {
  const accepts = createAgentUidFilter([{ agora_rtc_uid: 468707 }, { agora_rtc_uid: "468708" }]);
  assert.equal(accepts("468707"), true);
  assert.equal(accepts(468708), true);
  assert.equal(accepts(2882289352), false);
  assert.equal(accepts(0), false);
});

test("missing agent UID metadata fails closed instead of playing every remote mic", () => {
  const accepts = createAgentUidFilter([{}, { agora_rtc_uid: null }, { agora_rtc_uid: 0 }]);
  for (const uid of [undefined, null, 0, "0", "", "undefined", 468707]) assert.equal(accepts(uid), false);
});

test("cancelling initialization releases existing resources once and immediately closes late microphone capture", async () => {
  const scope = createAudioLifecycle();
  const closed = [];
  scope.own(() => { closed.push("rtc"); });
  let resolveCapture;
  const capture = new Promise(resolve => { resolveCapture = resolve; });
  const initialized = (async () => {
    const track = await capture;
    if (!scope.own(() => track.close())) return;
    track.publish();
  })();
  scope.dispose();
  scope.dispose();
  resolveCapture({ close: () => closed.push("late-mic"), publish: () => assert.fail("cancelled mic was published") });
  await initialized;
  assert.equal(scope.active, false);
  assert.deepEqual(closed, ["rtc", "late-mic"]);
});

test("disposing an older initialization cannot release resources owned by its replacement", () => {
  const old = createAudioLifecycle();
  const current = createAudioLifecycle();
  const closed = [];
  old.own(() => closed.push("old"));
  current.own(() => closed.push("current"));
  old.dispose();
  assert.equal(current.active, true);
  assert.deepEqual(closed, ["old"]);
  current.dispose();
  assert.deepEqual(closed, ["old", "current"]);
});

test("event/snapshot concurrent discovery starts the same remote track only once", async () => {
  let resolvePlayback;
  let calls = 0;
  const play = createIdempotentAudioPlayer();
  const track = { isPlaying: false, play: () => { calls++; return new Promise(resolve => { resolvePlayback = resolve; }); } };
  const event = play(track);
  const snapshot = play(track);
  assert.equal(calls, 1);
  assert.equal(event, snapshot);
  track.isPlaying = true;
  resolvePlayback();
  await Promise.all([event, snapshot]);
  await play(track);
  assert.equal(calls, 1);
});

test("a rejected autoplay attempt can be retried, and replacement tracks can play", async () => {
  const play = createIdempotentAudioPlayer();
  let calls = 0;
  const track = { isPlaying: false, play: () => { if (++calls === 1) throw new Error("autoplay blocked"); track.isPlaying = true; } };
  await assert.rejects(play(track), /autoplay blocked/);
  await play(track);
  assert.equal(calls, 2);
  let replacementCalls = 0;
  await play({ isPlaying: false, play: () => { replacementCalls++; } });
  assert.equal(replacementCalls, 1);
});

test("microphone diagnostics expose effective capture and counters without device identifiers or audio", () => {
  const result = microphoneDiagnostics({
    enabled: true, muted: false, readyState: "live",
    getSettings: () => ({ echoCancellation: true, noiseSuppression: true, autoGainControl: false, channelCount: 1,
      sampleRate: 48000, deviceId: "private-device", groupId: "private-group", label: "private-label" }),
  }, { sendBytes: 1200, sendPackets: 10, sendBitrate: 24000, sendVolumeLevel: 100 });
  assert.equal(result.echo_cancellation, true);
  assert.equal(result.ready_state, "live");
  assert.equal(result.send_bytes, 1200);
  assert.equal(result.auto_gain_control, false);
  assert.doesNotMatch(JSON.stringify(result), /private|deviceId|groupId|label/);
});

test("remote quality diagnostics preserve SDK units and exclude identifiers", () => {
  const diagnostics = remoteAudioQualityDiagnostics({ packetLossRate: 0.1, currentPacketLossRate: 0.2,
    receivePacketsLost: 12, receivePacketsDiscarded: 3, receiveDelay: 85, totalFreezeTime: 1.25,
    deviceId: "private-device", rawAudio: "private-samples" });
  assert.equal(diagnostics.receive_packets_lost, 12);
  assert.equal(diagnostics.packet_loss_rate, 0.1);
  assert.equal(diagnostics.receive_delay_ms, 85);
  assert.equal(diagnostics.total_freeze_seconds, 1.25);
  assert.doesNotMatch(JSON.stringify(diagnostics), /private|deviceId|rawAudio/);
});

test("unavailable receive counters are unknown, not fabricated zero loss", () => {
  assert.equal(remoteAudioQualityDiagnostics().packet_loss_rate, null);
  assert.equal(remoteAudioQualityDiagnostics({ totalFreezeTime: NaN }).total_freeze_seconds, null);
  assert.equal(remoteAudioQualityDiagnostics({ receivePacketsLost: 0 }).receive_packets_lost, 0);
});

test("roster never describes a merely configured interviewer as physically present", () => {
  assert.equal(agentPresenceLabel(false, false, false), "Selected");
  assert.equal(agentPresenceLabel(false, true, false), "Connecting");
  assert.equal(agentPresenceLabel(false, false, true), "Selected");
  assert.equal(agentPresenceLabel(true, false, false), "In room");
  assert.equal(agentPresenceLabel(true, true, true), "Speaking");
});
