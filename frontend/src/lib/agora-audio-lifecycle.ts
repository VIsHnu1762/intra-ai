/** RTC UIDs can arrive as numbers or strings. Missing agent UIDs never allow a wildcard. */
export function createAgentUidFilter(agents: ReadonlyArray<{ agora_rtc_uid?: number | string | null }>) {
  const allowed = new Set(agents
    .map(agent => agent.agora_rtc_uid)
    .filter(uid => uid !== null && uid !== undefined && String(uid).trim() !== "" && String(uid) !== "0")
    .map(String));
  return (uid: unknown) => uid !== null && uid !== undefined && allowed.has(String(uid));
}

/** Each initialization owns its resources, including ones acquired after cancellation. */
export function createAudioLifecycle() {
  let active = true;
  const cleanups = new Set<() => void | Promise<unknown>>();
  const release = (cleanup: () => void | Promise<unknown>) => {
    try { void Promise.resolve(cleanup()).catch(() => {}); } catch { /* Best-effort SDK teardown. */ }
  };
  return {
    get active() { return active; },
    own(cleanup: () => void | Promise<unknown>) {
      if (!active) { release(cleanup); return false; }
      cleanups.add(cleanup);
      return true;
    },
    dispose() {
      if (!active) return;
      active = false;
      for (const cleanup of cleanups) release(cleanup);
      cleanups.clear();
    },
  };
}

type PlayableAudioTrack = { isPlaying: boolean; play(): void | Promise<void> };

/** Event and post-join discovery may refer to the same track; start playback only once. */
export function createIdempotentAudioPlayer() {
  const pending = new WeakMap<PlayableAudioTrack, Promise<void>>();
  return (track: PlayableAudioTrack): Promise<void> => {
    const existing = pending.get(track);
    if (existing) return existing;
    if (track.isPlaying) return Promise.resolve();
    const operation = (async () => { await track.play(); })();
    pending.set(track, operation);
    void operation.finally(() => pending.delete(track)).catch(() => {});
    return operation;
  };
}

/** Allowlisted metadata only: never log device IDs, labels, constraints or audio samples. */
export function microphoneDiagnostics(
  track: Pick<MediaStreamTrack, "enabled" | "muted" | "readyState" | "getSettings">,
  stats: { sendBytes?: number; sendPackets?: number; sendBitrate?: number; sendVolumeLevel?: number } = {},
) {
  const settings = track.getSettings();
  return {
    enabled: track.enabled, muted: track.muted, ready_state: track.readyState,
    echo_cancellation: settings.echoCancellation ?? null,
    noise_suppression: settings.noiseSuppression ?? null,
    auto_gain_control: settings.autoGainControl ?? null,
    channel_count: settings.channelCount ?? null, sample_rate: settings.sampleRate ?? null,
    send_bytes: stats.sendBytes ?? null, send_packets: stats.sendPackets ?? null,
    send_bitrate: stats.sendBitrate ?? null, send_volume_level: stats.sendVolumeLevel ?? null,
  };
}

/** SDK receive metadata; freeze duration is seconds, receive delay is milliseconds. */
export function remoteAudioQualityDiagnostics(stats?: {
  packetLossRate?: number; receivePacketsLost?: number; receiveDelay?: number; totalFreezeTime?: number;
  currentPacketLossRate?: number; receivePacketsDiscarded?: number;
}) {
  const numeric = (value: number | undefined) => typeof value === "number" && Number.isFinite(value) ? value : null;
  return {
    packet_loss_rate: numeric(stats?.packetLossRate),
    current_packet_loss_rate: numeric(stats?.currentPacketLossRate),
    receive_packets_lost: numeric(stats?.receivePacketsLost),
    receive_packets_discarded: numeric(stats?.receivePacketsDiscarded),
    receive_delay_ms: numeric(stats?.receiveDelay),
    total_freeze_seconds: numeric(stats?.totalFreezeTime),
  };
}

/** Being configured for a later turn is distinct from physical RTC presence. */
export function agentPresenceLabel(present: boolean, current: boolean, speaking: boolean) {
  if (!present) return current ? "Connecting" : "Selected";
  return speaking ? "Speaking" : "In room";
}
