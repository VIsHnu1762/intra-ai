"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { IAgoraRTCClient, IMicrophoneAudioTrack, IRemoteAudioTrack, IAgoraRTCRemoteUser } from "agora-rtc-sdk-ng";
import { ApiError } from "@/lib/api/client";
import { completePracticeFeedback, releasePracticeAudio, createPracticeLatencyTracker, type TaylorPracticeFeedback, type TaylorPracticeOptions } from "@/lib/taylor-practice";
import { voiceAssistantsApi, type VoiceAgent, type VoiceContext, type VoiceCredentials, type VoicePendingAction, type VoiceTranscriptEntry, type VoiceToolResult } from "@/lib/api/voice-assistants";
import { createAudioLifecycle, createIdempotentAudioPlayer } from "@/lib/agora-audio-lifecycle";
import { reconcileMorganActionSnapshot } from "@/lib/morgan-workflows";
import { emptyVoiceConnection, voiceMediaError, voiceState, parseVoiceTranscript, mergeVoiceTranscript, type VoiceConnection } from "@/lib/voice-assistant-state";

type OwnedSession = {
  id: string | null;
  scope: ReturnType<typeof createAudioLifecycle>;
  microphone?: IMicrophoneAudioTrack;
  client?: IAgoraRTCClient;
  remote?: IRemoteAudioTrack;
  flushTranscript?: () => Promise<void>;
};

export function useVoiceAssistant(agent: VoiceAgent) {
  const [connection, setConnection] = useState<VoiceConnection>({ ...emptyVoiceConnection });
  const [transcript, setTranscript] = useState<VoiceTranscriptEntry[]>([]);
  const [pendingAction, setPendingAction] = useState<VoicePendingAction | null>(null);
  const [toolResult, setToolResult] = useState<VoiceToolResult | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [muted, setMuted] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [actionSession, setActionSession] = useState<{ sessionId: string; confirmationId: string; startedAt: number } | null>(null);
  const actionSessionRef = useRef<typeof actionSession>(null);
  const owned = useRef<OwnedSession | null>(null);
  const orphanId = useRef<string | null>(null);
  const mounted = useRef(true);
  const submittedConfirmations = useRef(new Set<string>());
  const toolResultRef = useRef<VoiceToolResult | null>(null);
  const showToolResult = useCallback((result: VoiceToolResult | null, authoritative = false) => {
    toolResultRef.current = result;
    if (authoritative && result?.confirmation_id === actionSessionRef.current?.confirmationId && ["succeeded", "partial", "failed", "declined"].includes(result?.status || "")) {
      actionSessionRef.current = null;
      if (mounted.current) setActionSession(null);
    }
    if (mounted.current) setToolResult(result);
  }, []);
  const starting = useRef(false);
  const closing = useRef(false);
  const finishingPractice = useRef(false);
  const practiceCancelled = useRef(false);
  const confirmationRequest = useRef<string | null>(null);
  const confirmationEpoch = useRef(0);
  const changingMute = useRef(false);
  const contextQueue = useRef<Promise<void>>(Promise.resolve());
  const contextVersion = useRef(0);
  const lastActivity = useRef(Date.now());
  const play = useRef(createIdempotentAudioPlayer());
  const patch = useCallback((changes: Partial<VoiceConnection>) => {
    if (mounted.current) setConnection(current => ({ ...current, ...changes }));
  }, []);
  const markActivity = useCallback(() => { lastActivity.current = Date.now(); }, []);

  const end = useCallback(async (reason?: string) => {
    if (finishingPractice.current) practiceCancelled.current = true;
    if (closing.current) return false;
    closing.current = true;
    try {
      const current = owned.current;
      owned.current = null;
      current?.scope.dispose(); // Release browser capture even if the backend is unavailable.
      const id = current?.id || orphanId.current;
      orphanId.current = id;
      patch({ ...emptyVoiceConnection, backendStatus: "ended", error: reason || null });
      if (mounted.current) { setMuted(false); setPendingAction(null); setSessionId(null); }
      if (!id) return true;
      try {
        await current?.flushTranscript?.();
        await voiceAssistantsApi.end(id);
        if (orphanId.current === id) orphanId.current = null;
        return true;
      } catch {
        patch({ error: "Your microphone is off, but the session could not be closed on the server. Retry ending the session." });
        return false;
      }
    } finally { closing.current = false; }
  }, [patch]);

  const finishPractice = useCallback(async (): Promise<TaylorPracticeFeedback | null> => {
    const current = owned.current;
    if (agent !== "taylor" || !current?.id || finishingPractice.current || closing.current) return null;
    finishingPractice.current = true;
    practiceCancelled.current = false;
    const id = current.id;
    // Deactivate callbacks BEFORE local leave/track-ended events can fire.
    owned.current = null;
    orphanId.current = id;
    patch({ ...emptyVoiceConnection, backendStatus: "ended" });
    if (mounted.current) { setMuted(false); setPendingAction(null); setSessionId(null); }
    try {
      const { feedback, cloudClosed, awaitingFeedback } = await completePracticeFeedback({
        releaseLocal: () => releasePracticeAudio(current.scope, [current.microphone, current.remote]),
        flushTranscript: current.flushTranscript,
        requestFeedback: () => voiceAssistantsApi.finishPractice(id),
        closeCloud: () => voiceAssistantsApi.end(id),
        isCancelled: () => practiceCancelled.current || !mounted.current,
        errorMessage: error => error instanceof ApiError ? error.message : "Feedback could not be retrieved. Use Check Saved Feedback to check whether it was saved; this will not generate another assessment.",
      });
      if (cloudClosed) {
        if (orphanId.current === id) orphanId.current = null;
      } else if (!awaitingFeedback) {
        patch({ error: "Your microphone is off, but the session could not be closed on the server. Retry ending the session." });
      }
      return feedback;
    } finally { finishingPractice.current = false; }
  }, [agent, patch]);

  const start = useCallback(async (context: VoiceContext = {}, practice?: TaylorPracticeOptions) => {
    if (starting.current || closing.current || finishingPractice.current || actionSessionRef.current || owned.current?.scope.active) return;
    starting.current = true;
    if (orphanId.current && !await end()) { starting.current = false; return; }
    const current: OwnedSession = { id: null, scope: createAudioLifecycle() };
    owned.current = current;
    const active = () => mounted.current && current.scope.active && owned.current === current;
    const latency = agent === "taylor" ? createPracticeLatencyTracker() : null;
    const log = (stage: string) => console.info(`[VOICE_${stage}]`, { agent, session_id: current.id });
    patch({ ...emptyVoiceConnection, active: true, connecting: true });
    setTranscript([]); setPendingAction(null); showToolResult(null);
    submittedConfirmations.current.clear(); setMuted(false); setConfirming(false);
    confirmationRequest.current = null; confirmationEpoch.current++;
    markActivity();
    try {
      const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
      if (!active()) return;
      // Keep SDK argument dumps (including short-lived join tokens) out of console logs.
      AgoraRTC.setLogLevel(4);
      const microphone = await AgoraRTC.createMicrophoneAudioTrack({ AEC: true, ANS: true, AGC: true });
      if (!current.scope.own(() => { microphone.stop(); microphone.close(); })) return;
      current.microphone = microphone;
      microphone.on("track-ended", () => { if (active()) void end("Your microphone disconnected. Reconnect it, then start a new session."); });
      let credentials: VoiceCredentials;
      try {
        credentials = await voiceAssistantsApi.start(agent, context, practice);
      } catch (err) {
        if (err instanceof ApiError && err.status === 409 && (err.message.includes("active session") || err.message.includes("End it before starting another"))) {
          console.info("[VOICE_RECOVERING_ACTIVE_SESSION]", { agent });
          try { await voiceAssistantsApi.endActive(agent); } catch { /* best effort */ }
          credentials = await voiceAssistantsApi.start(agent, context, practice, true);
        } else {
          throw err;
        }
      }
      current.id = credentials.session_id;
      // A close/unmount while the start request is pending must also stop the late cloud agent.
      if (!active()) {
        try { await voiceAssistantsApi.end(credentials.session_id); } catch { orphanId.current = credentials.session_id; }
        return;
      }
      setSessionId(credentials.session_id);
      if (!credentials.app_id || !credentials.rtc_token || !credentials.channel_name || !credentials.agent_rtc_uid || !Number.isFinite(credentials.rtc_uid)) {
        throw new Error("Invalid connection information");
      }
      const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      current.client = client;
      current.scope.own(async () => { client.removeAllListeners(); await client.leave(); });
      const isAgent = (uid: unknown) => String(uid) === String(credentials.agent_rtc_uid);
      const autoplayFailed = () => { if (active()) patch({ autoplayBlocked: true, playbackStarted: false }); };
      AgoraRTC.on("autoplay-failed", autoplayFailed);
      current.scope.own(() => AgoraRTC.off("autoplay-failed", autoplayFailed));
      const subscriptions = new Set<string>();
      const subscribe = async (remote: IAgoraRTCRemoteUser) => {
        if (!active() || !isAgent(remote.uid) || subscriptions.has(String(remote.uid))) return;
        subscriptions.add(String(remote.uid));
        patch({ agentJoined: true, audioPublished: true }); log("AUDIO_PUBLISHED");
        try {
          await client.subscribe(remote, "audio");
          if (!active()) return;
          const track = remote.audioTrack;
          if (!track) {
            // Track may arrive slightly after subscribe — wait briefly and retry once.
            await new Promise(resolve => setTimeout(resolve, 500));
            if (!active()) return;
          }
          const finalTrack = remote.audioTrack;
          if (!finalTrack) throw new Error("Missing audio track after subscribe");
          if (current.remote && current.remote !== finalTrack) current.remote.stop();
          current.remote = finalTrack;
          current.scope.own(() => finalTrack.stop());
          patch({ audioSubscribed: true }); log("AUDIO_SUBSCRIBED");
          try {
            await play.current(finalTrack);
            if (active()) { patch({ playbackStarted: finalTrack.isPlaying }); log("PLAYBACK_REQUESTED"); }
          } catch { autoplayFailed(); }
        } catch {
          if (active()) void end("The assistant joined, but its audio could not be received. Please reconnect.");
        } finally { subscriptions.delete(String(remote.uid)); }
      };

      client.on("user-joined", remote => {
        if (!active() || !isAgent(remote.uid)) return;
        patch({ agentJoined: true }); log("AGENT_JOINED");
        // Agent may have already published audio before our listener attached.
        if (remote.hasAudio) void subscribe(remote);
      });
      client.on("user-published", (remote, mediaType) => { if (mediaType === "audio") void subscribe(remote); });
      client.on("user-unpublished", (remote, mediaType) => {
        if (active() && isAgent(remote.uid) && mediaType === "audio") {
          current.remote?.stop(); current.remote = undefined;
          patch({ audioPublished: false, audioSubscribed: false, playbackStarted: false, speaking: false }); log("AUDIO_UNPUBLISHED");
        }
      });
      client.on("user-left", remote => { if (active() && isAgent(remote.uid)) void end("The assistant disconnected. Start a new session to reconnect."); });
      client.on("connection-state-change", (state, _previous, reason) => {
        if (!active()) return;
        patch({ connected: state === "CONNECTED", connecting: state === "CONNECTING" || state === "RECONNECTING" });
        if (state === "DISCONNECTED") void end(reason === "UID_BANNED" ? "This voice connection is no longer available. Start a new session." : "The voice connection was lost. Check your network and reconnect.");
      });
      client.on("token-privilege-did-expire", () => { if (active()) void end("This voice session expired. Start a new session to continue."); });
      client.on("token-privilege-will-expire", () => { if (active()) log("TOKEN_EXPIRING"); });
      // RTM remains separate from official interview transcript/evidence endpoints.
      const rtmReady = credentials.rtm_token ? (async () => {
        try {
          const { RTM } = (await import("agora-rtm-sdk")).default;
          if (!active()) return;
          const rtm = new RTM(credentials.app_id, credentials.rtm_user_id || String(credentials.rtc_uid), { logLevel: "none" });
          current.scope.own(() => rtm.logout());
          const pending = new Map<string, VoiceTranscriptEntry>();
          let flushing = false;
          const flush = async () => {
            if (flushing || pending.size === 0) return;
            flushing = true;
            const batch = [...pending.values()].slice(0, 30);
            for (const entry of batch) pending.delete(entry.id!);
            try { await voiceAssistantsApi.transcript(credentials.session_id, batch); }
            catch { if (active()) for (const entry of batch) if (!pending.has(entry.id!)) pending.set(entry.id!, entry); }
            finally { flushing = false; }
          };
          current.flushTranscript = flush;
          rtm.addEventListener("message", event => {
            if (!active()) return;
            const entry = parseVoiceTranscript(event.message, event.publisher, credentials.agent_rtc_uid);
            if (!entry) return;
            const { final, ...row } = entry;
            setTranscript(previous => mergeVoiceTranscript(previous, [row]));
            markActivity();
            if (final) {
              if (row.role === "user") latency?.finalUserTranscript(row.id, performance.now());
              pending.set(row.id, row);
              while (pending.size > 80) pending.delete(pending.keys().next().value!);
              log("TRANSCRIPT_FINAL");
            }
          });
          await rtm.login({ token: credentials.rtm_token! });
          if (!active()) { await rtm.logout().catch(() => {}); return; }
          await rtm.subscribe(credentials.channel_name, { withMessage: true, withPresence: false, withMetadata: false, withLock: false });
          if (!active()) { await rtm.logout().catch(() => {}); return; }
          log("RTM_SUBSCRIBED");
          const flushTimer = setInterval(() => void flush(), 1000);
          current.scope.own(() => clearInterval(flushTimer));
        } catch { if (active()) log("TRANSCRIPT_CONNECTION_UNAVAILABLE"); }
      })() : Promise.resolve();
      // RTM failure cannot block voice, but give captions a short head start.
      let rtmWaitTimer: ReturnType<typeof setTimeout> | undefined;
      await Promise.race([rtmReady, new Promise<void>(resolve => { rtmWaitTimer = setTimeout(resolve, 3000); })]);
      if (rtmWaitTimer) clearTimeout(rtmWaitTimer);
      if (!active()) return;
      await client.join(credentials.app_id, credentials.channel_name, credentials.rtc_token, credentials.rtc_uid);
      if (!active()) { await client.leave(); return; }
      patch({ connected: true, connecting: false }); log("RTC_JOINED");
      await client.publish(microphone);
      if (!active()) return;
      patch({ microphonePublished: true }); log("MIC_PUBLISHED");
      // Scan immediately for agents already in the channel before we joined.
      client.remoteUsers.forEach(remote => {
        if (isAgent(remote.uid)) patch({ agentJoined: true });
        if (remote.hasAudio) void subscribe(remote);
      });
      // Polling fallback: scan every 1s for up to 20s for agents that joined
      // but whose user-published event may have been missed due to timing.
      let audioScanCount = 0;
      const audioScanTimer = setInterval(() => {
        if (!active() || current.remote) { clearInterval(audioScanTimer); return; }
        if (++audioScanCount > 20) { clearInterval(audioScanTimer); return; }
        client.remoteUsers.forEach(remote => {
          if (isAgent(remote.uid) && remote.hasAudio && !current.remote) void subscribe(remote);
        });
      }, 1000);
      current.scope.own(() => clearInterval(audioScanTimer));
      let pollBusy = false;
      let failedPolls = 0;
      const poll = async () => {
        if (!active() || pollBusy) return;
        pollBusy = true;
        const actionEpoch = confirmationEpoch.current;
        try {
          const snapshot = await voiceAssistantsApi.get(credentials.session_id);
          if (!active()) return;
          failedPolls = 0;
          patch({ backendStatus: snapshot.status });
          if (snapshot.transcript) setTranscript(previous => mergeVoiceTranscript(previous, snapshot.transcript || []));
          if (!confirmationRequest.current && actionEpoch === confirmationEpoch.current) {
            if (agent === "morgan") {
              const next = reconcileMorganActionSnapshot(toolResultRef.current, snapshot.last_tool_result, snapshot.pending_action, submittedConfirmations.current);
              setPendingAction(next.pending);
              showToolResult(next.result, next.result === snapshot.last_tool_result);
            } else {
              setPendingAction(snapshot.pending_action || null);
              if (!snapshot.pending_action && snapshot.last_tool_result) showToolResult(snapshot.last_tool_result);
            }
          }
          // Preserve the final action outcome even when the voice session ended.
          if (/^(ended|expired|failed|error|disconnected)$/i.test(snapshot.status)) {
            void end(snapshot.error || (snapshot.status.toLowerCase() === "ended" ? undefined : "The assistant session ended. Start a new session to continue."));
            return;
          }
        } catch (error) {
          if (!active()) return;
          if ((error instanceof ApiError && [401, 403, 404].includes(error.status)) || ++failedPolls >= 3) {
            void end("The assistant service could not be reached. Your microphone has been stopped. Please reconnect.");
          }
        } finally { pollBusy = false; }
      };
      const pollTimer = setInterval(() => void poll(), 2500);
      const heartbeatTimer = setInterval(() => {
        if (!active()) return;
        if (Date.now() - lastActivity.current > 5 * 60_000) { void end("The session ended after five minutes without speech. Start again whenever you are ready."); return; }
        void voiceAssistantsApi.heartbeat(credentials.session_id).catch(() => { /* GET polling handles sustained service failure. */ });
      }, 15_000);
      let microphoneObserved = false;
      let remoteAudioObserved = false;
      const levelTimer = setInterval(() => {
        if (!active()) return;
        const microphoneActive = microphone.enabled && microphone.getVolumeLevel() > 0.03;
        const speaking = Boolean(current.remote && current.remote.getVolumeLevel() > 0.02);
        const responseLatency = latency?.remoteAudio(speaking, performance.now());
        if (responseLatency !== null && responseLatency !== undefined) console.info("[VOICE_RESPONSE_LATENCY]", {
          session_id: current.id, latency_ms: responseLatency, measurement: "final_user_transcript_to_remote_audio",
        });
        if (microphoneActive && !microphoneObserved) { microphoneObserved = true; log("MIC_SIGNAL_DETECTED"); }
        if (speaking && !remoteAudioObserved) { remoteAudioObserved = true; log("REMOTE_AUDIO_SIGNAL"); }
        if (microphoneActive || speaking) markActivity();
        patch({ microphoneActive, speaking, playbackStarted: Boolean(current.remote?.isPlaying) });
        if (credentials.expires_at && Date.parse(credentials.expires_at) <= Date.now()) void end("This voice session expired. Start a new session to continue.");
      }, 300);
      current.scope.own(() => { clearInterval(pollTimer); clearInterval(heartbeatTimer); clearInterval(levelTimer); });
      void poll();
    } catch (error) {
      if (active()) await end(error instanceof ApiError ? error.message : voiceMediaError(error));
    } finally { starting.current = false; }
  }, [agent, end, markActivity, patch, showToolResult]);

  const updateContext = useCallback(async (context: VoiceContext) => {
    const id = owned.current?.id;
    if (!id || !owned.current?.scope.active) return;
    const version = ++contextVersion.current;
    contextQueue.current = contextQueue.current.then(async () => {
      if (version !== contextVersion.current || owned.current?.id !== id) return;
      try { await voiceAssistantsApi.context(id, context); }
      catch { if (owned.current?.id === id) await end("Morgan could not switch to the page you opened. Reconnect before requesting changes here."); }
    });
    await contextQueue.current;
  }, [end]);
  const toggleMute = useCallback(async () => {
    const current = owned.current;
    if (!current?.microphone || !current.scope.active || changingMute.current) return;
    changingMute.current = true;
    try {
      await current.microphone.setEnabled(!current.microphone.enabled);
      if (mounted.current && owned.current === current) { setMuted(!current.microphone.enabled); markActivity(); }
    } catch { if (owned.current === current) await end("Your microphone could not be changed. Reconnect your microphone and start again."); }
    finally { changingMute.current = false; }
  }, [end, markActivity]);
  const unlockAudio = useCallback(async () => {
    const track = owned.current?.remote;
    if (!track) return;
    try { track.play(); patch({ autoplayBlocked: !track.isPlaying, playbackStarted: track.isPlaying }); markActivity(); }
    catch { patch({ autoplayBlocked: true }); }
  }, [markActivity, patch]);
  const confirm = useCallback(async (approved: boolean) => {
    const id = owned.current?.id;
    if (!id || !pendingAction || confirmationRequest.current || submittedConfirmations.current.has(pendingAction.confirmation_id)) return;
    if (approved && pendingAction.expires_at && Date.parse(pendingAction.expires_at) <= Date.now()) {
      showToolResult({ status: "error", message: "This confirmation has expired. Ask Morgan to prepare the request again." });
      return;
    }
    const requestKey = `${id}:${pendingAction.confirmation_id}`;
    confirmationRequest.current = requestKey;
    submittedConfirmations.current.add(pendingAction.confirmation_id);
    const execution = { sessionId: id, confirmationId: pendingAction.confirmation_id, startedAt: Date.now() };
    actionSessionRef.current = execution;
    setActionSession(execution);
    confirmationEpoch.current++;
    setConfirming(true); setPendingAction(null); markActivity();
    showToolResult({ status: "submitting", confirmation_id: pendingAction.confirmation_id, tool: pendingAction.tool, message: approved ? "Sending your confirmation…" : "Declining this request…" });
    try {
      const result = await voiceAssistantsApi.confirm(id, pendingAction.confirmation_id, approved);
      if (mounted.current && owned.current?.id === id) {
        showToolResult(result, true);
        setPendingAction(result.pending_action && !submittedConfirmations.current.has(result.pending_action.confirmation_id) ? result.pending_action : null);
        if (result.status === "executing") patch({ backendStatus: "EXECUTING" });
      }
    } catch (error) {
      if (mounted.current && owned.current?.id === id) {
        const unknown = !(error instanceof ApiError) || error.status >= 500 || error.status === 408;
        if (!unknown) { actionSessionRef.current = null; setActionSession(null); }
        showToolResult({ status: unknown ? "failed" : "error", confirmation_id: pendingAction.confirmation_id, tool: pendingAction.tool, outcome_unknown: unknown, message: error instanceof ApiError ? error.message : "The confirmation response was lost. Checking the saved action status; do not submit it again." });
      }
    } finally {
      if (confirmationRequest.current === requestKey) { confirmationRequest.current = null; confirmationEpoch.current++; }
      if (mounted.current && owned.current?.id === id) setConfirming(false);
    }
  }, [markActivity, pendingAction, patch, showToolResult]);

  // A confirmed write can outlive its voice connection. This loop only reads
  // the persisted result; it never calls confirm or any mutation endpoint.
  useEffect(() => {
    if (agent !== "morgan" || !actionSession) return;
    let disposed = false;
    let busy = false;
    const execution = actionSession;
    const read = async () => {
      if (disposed || busy || actionSessionRef.current !== execution || !mounted.current) return;
      if (Date.now() - execution.startedAt > 5 * 60_000) {
        showToolResult({ status: "failed", confirmation_id: execution.confirmationId, outcome_unknown: true, message: "The final action result could not be retrieved. Check the candidate or connected service before preparing another request." }, true);
        return;
      }
      if (owned.current?.id === execution.sessionId && owned.current.scope.active) return; // Normal session polling owns this case.
      busy = true;
      try {
        const snapshot = await voiceAssistantsApi.get(execution.sessionId);
        if (disposed || actionSessionRef.current !== execution || !mounted.current) return;
        if (snapshot.last_tool_result?.confirmation_id === execution.confirmationId) showToolResult(snapshot.last_tool_result, true);
      } catch (error) {
        if (!disposed && mounted.current && actionSessionRef.current === execution && error instanceof ApiError && [401, 403, 404].includes(error.status)) {
          showToolResult({ status: "failed", confirmation_id: execution.confirmationId, outcome_unknown: true, message: "The saved action result is no longer accessible. Check the candidate or connected service before submitting another request." }, true);
        }
      } finally { busy = false; }
    };
    const timer = setInterval(() => void read(), 2500);
    void read();
    return () => { disposed = true; clearInterval(timer); };
  }, [agent, actionSession, showToolResult]);

  const resetSession = useCallback(async () => {
    try { await voiceAssistantsApi.endActive(agent); } catch { /* best effort */ }
    await end();
  }, [agent, end]);

  useEffect(() => {
    mounted.current = true;
    const leave = () => { void end(); };
    window.addEventListener("pagehide", leave);
    window.addEventListener("beforeunload", leave);
    return () => {
      mounted.current = false;
      window.removeEventListener("pagehide", leave);
      window.removeEventListener("beforeunload", leave);
      void end();
    };
  }, [end]);
  return { connection, actionPending: Boolean(actionSession), state: voiceState(connection), transcript, pendingAction, toolResult, confirming, muted, sessionId, start, end, resetSession, toggleMute, unlockAudio, confirm, markActivity, updateContext, finishPractice };
}
