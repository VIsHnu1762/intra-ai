/** Only explicit backend work or RTC evidence advances the assistant's UI. */
export type VoiceConnection = {
  active: boolean;
  connecting: boolean;
  connected: boolean;
  agentJoined: boolean;
  audioPublished: boolean;
  audioSubscribed: boolean;
  playbackStarted: boolean;
  microphonePublished: boolean;
  microphoneActive: boolean;
  speaking: boolean;
  autoplayBlocked: boolean;
  backendStatus: string;
  error: string | null;
};
export const emptyVoiceConnection: VoiceConnection = {
  active: false, connecting: false, connected: false, agentJoined: false,
  audioPublished: false, audioSubscribed: false, playbackStarted: false,
  microphonePublished: false, microphoneActive: false, speaking: false,
  autoplayBlocked: false, backendStatus: "idle", error: null,
};
export function voiceState(connection: VoiceConnection): string {
  if (connection.error) return "error";
  if (!connection.active) return connection.backendStatus === "idle" ? "idle" : "disconnected";
  if (connection.connecting || !connection.connected) return "connecting";
  if (connection.autoplayBlocked) return "audio blocked";
  if (connection.speaking && connection.playbackStarted) return "speaking";
  if (connection.backendStatus.toLowerCase() === "executing") return "executing";
  if (connection.backendStatus.toLowerCase() === "processing") return "processing";
  if (connection.microphoneActive) return "listening";
  return "connected";
}

/** Route context is a hint only; every ID is re-authorized by the backend. */
export function voiceDashboardContext(pathname: string): Record<string, string> {
  const match = /^\/admin\/(jobs|candidates|interviews)\/([a-zA-Z0-9_-]+)\/?$/.exec(pathname);
  if (!match || ["new", "templates"].includes(match[2])) return {};
  const key = { jobs: "job_id", candidates: "candidate_id", interviews: "interview_id" }[match[1]];
  return key ? { [key]: match[2] } : {};
}

export function voiceMediaError(error: unknown): string {
  const code = error && typeof error === "object" ? String((error as { name?: string; code?: string }).code || (error as { name?: string }).name || "") : "";
  if (/PERMISSION|NotAllowed|Security/i.test(code)) return "Microphone permission was denied. Allow microphone access in your browser, then try again.";
  if (/NotFound|DEVICE_NOT_FOUND/i.test(code)) return "No microphone was found. Connect a microphone, then try again.";
  if (/NotReadable|TRACK_IS_DISABLED|DEVICE_IN_USE/i.test(code)) return "Your microphone is unavailable. Close other apps using it or choose another input in your browser.";
  if (/TOKEN|INVALID_KEY/i.test(code)) return "The voice connection has expired or could not be authorized. End this session and reconnect.";
  return "The voice connection could not be established. Check your microphone and network, then try again.";
}

export type AssistantTranscript = { id?: string; role: string; text: string; at?: string };
// Stable opaque fallback: transcript IDs must not contain the candidate's spoken text.
function transcriptDigest(value: string): string {
  let first = 2166136261;
  let second = 5381;
  for (const character of value) {
    first = Math.imul(first ^ character.charCodeAt(0), 16777619);
    second = Math.imul(second, 33) ^ character.charCodeAt(0);
  }
  return `${(first >>> 0).toString(36)}${(second >>> 0).toString(36)}-${value.length}`;
}
/** Studio transcripts are accepted only from the configured assistant publisher. */
export function parseVoiceTranscript(message: unknown, publisher: unknown, agentUid: string, now = new Date().toISOString()): (AssistantTranscript & { id: string; final: boolean }) | null {
  if (!agentUid || String(publisher) !== String(agentUid)) return null;
  try {
    const raw = message instanceof Uint8Array ? new TextDecoder().decode(message) : message;
    if (typeof raw !== "string") return null;
    const event = JSON.parse(raw);
    if (!event || !["assistant.transcription", "user.transcription", "agent.message"].includes(event.object)) return null;
    const text = event.text ?? event.content;
    if (typeof text !== "string" || !text.trim()) return null;
    const role = event.object === "user.transcription" || event.role === "user" ? "user" : "assistant";
    const final = event.is_final === true || event.final === true || event.status === "final" || event.turn_status === 1;
    const turnId = event.turn_id ?? event.id ?? event.start_ts ?? event.timestamp ?? event.time;
    if (turnId === undefined && !final) return null;
    if (turnId !== undefined && typeof turnId !== "string" && typeof turnId !== "number") return null;
    const key = turnId === undefined ? `text-${transcriptDigest(text.trim())}` : `turn-${transcriptDigest(String(turnId))}`;
    const id = `rtm:${transcriptDigest(agentUid)}:${role}:${key}`;
    return { id, role, text: text.trim().slice(0, 4000), at: now, final };
  } catch { return null; }
}

/** Reconcile final server rows and local progressive RTM updates without duplicate turns. */
export function mergeVoiceTranscript(existing: AssistantTranscript[], incoming: AssistantTranscript[]): AssistantTranscript[] {
  const merged = new Map(existing.map(entry => [entry.id || `${entry.role}:${entry.at}:${entry.text}`, entry]));
  for (const entry of incoming) merged.set(entry.id || `${entry.role}:${entry.at}:${entry.text}`, entry);
  return [...merged.values()].slice(-80);
}
