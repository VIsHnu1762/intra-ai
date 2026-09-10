"use client";

import { standardInterviewFetch } from "@/lib/api/standard-interview-fetch";

import { useState, useEffect, useRef, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import {
  Mic,
  MicOff,
  Camera,
  CameraOff,
  PhoneOff,
  User,
  Waves,
  Clock,
  Volume2,
  VolumeX,
  AlertTriangle,
  Radio,
  RefreshCw,
  Users,
  CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { createAgentUidFilter, createAudioLifecycle, createIdempotentAudioPlayer, microphoneDiagnostics, remoteAudioQualityDiagnostics, agentPresenceLabel } from "@/lib/agora-audio-lifecycle";

// ─── Types ────────────────────────────────────────────────────────────────────

type ConnectionState = "idle" | "connecting" | "connected" | "error";
type MicState = "active" | "muted" | "permission_required" | "error";

/** Agent audio state machine — distinguishes each stage of the audio path. */
type AgentAudioState =
  | "waiting"         // Agent not yet in channel
  | "joined"          // Agent joined RTC but no audio track yet
  | "audio_published" // Agent published audio track
  | "subscribed"      // We subscribed to the audio track
  | "playing"         // Audio track is actively playing
  | "subscribe_failed" // RTC subscription failed before playback
  | "play_failed";    // Playback failed; autoplay is a separate browser signal


interface AgentInfo {
  agent_id: string;
  name: string;
  role: string;
  agora_rtc_uid?: number | string | null;
}

interface SessionCredentials {
  interview_id: string;
  channel_name: string;
  agora_app_id: string;
  agora_token: string;
  agora_uid: number;
  rtm_user_id: string;
  selected_agents: AgentInfo[];
  current_agent_id: string;
  agent_ids: string[];
  duration_minutes: number;
  job_title?: string;
  company?: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatSeconds(s: number) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

// ─── WaveformVisualizer ───────────────────────────────────────────────────────

function WaveformVisualizer({ isActive, isAgent, volumeLevel }: { isActive: boolean; isAgent: boolean; volumeLevel: number }) {
  const bases = [4, 8, 14, 22, 16, 28, 18, 12, 24, 15, 8, 5];
  return (
    <div className="flex items-center gap-1 h-10 px-4">
      {bases.map((h, i) => {
        const dh = isActive ? Math.max(6, Math.min(36, h * (volumeLevel / 40 + 0.3))) : 6;
        return (
          <div
            key={i}
            className={cn(
              "w-1 rounded-full transition-all duration-100",
              isActive ? (isAgent ? "bg-brand animate-pulse" : "bg-success animate-pulse") : "bg-border h-1.5"
            )}
            style={{ height: `${dh}px`, animationDelay: `${i * 60}ms`, animationDuration: "400ms" }}
          />
        );
      })}
    </div>
  );
}

// ─── AIAvatarPip ──────────────────────────────────────────────────────────────

function AIAvatarPip({ isSpeaking, audioState, agentName }: { isSpeaking: boolean; audioState: AgentAudioState; agentName: string }) {
  const isConnected = audioState !== "waiting";
  return (
    <div className="relative">
      {isSpeaking && (
        <>
          <span className="absolute -inset-2 rounded-full bg-brand/30 animate-ping" />
          <span className="absolute -inset-1 rounded-full bg-brand/50 animate-pulse" />
        </>
      )}
      <div className={cn(
        "relative h-16 w-16 rounded-full flex flex-col items-center justify-center border-2 transition-all duration-300",
        isSpeaking
          ? "border-brand bg-brand text-text-inverse shadow-sm"
          : isConnected
          ? "border-success/30 bg-success-light text-success shadow-sm"
          : "border-border bg-surface text-text-muted"
      )}>
        <Waves className={cn("h-6 w-6 transition-colors", isSpeaking ? "text-text-inverse" : isConnected ? "text-success" : "text-text-muted")} />
        <span className="text-[10px] font-semibold mt-0.5">{agentName}</span>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function InterviewRoomPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const router = useRouter();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Session credentials (from prep page via sessionStorage, or fetched fresh)
  const [credentials, setCredentials] = useState<SessionCredentials | null>(null);
  const [credentialsLoading, setCredentialsLoading] = useState(true);

  // Connection
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [micState, setMicState] = useState<MicState>("active");
  const [agoraError, setAgoraError] = useState<string | null>(null);
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);

  // Agent audio state machine (never use local mic level to infer agent speaking)
  const [agentAudioState, setAgentAudioState] = useState<AgentAudioState>("waiting");

  // Who's actively speaking (based ONLY on Agora volume-indicator for remote users)
  const [isAISpeaking, setIsAISpeaking] = useState(false);
  const [isCandidateSpeaking, setIsCandidateSpeaking] = useState(false);
  const [currentVolume, setCurrentVolume] = useState(0);
  const [physicalSpeakingAgentId, setPhysicalSpeakingAgentId] = useState<string | null>(null);

  // Active agent (from session, updated by SWITCH_AGENT via RTM)
  const [currentAgentId, setCurrentAgentId] = useState<string>("alex");
  const [currentAgentInfo, setCurrentAgentInfo] = useState<AgentInfo | null>(null);

  // Session
  const [sessionDuration, setSessionDuration] = useState(0);
  const [remoteParticipantCount, setRemoteParticipantCount] = useState(0);
  const [presentAgentUids, setPresentAgentUids] = useState<string[]>([]);
  const [isEnding, setIsEnding] = useState(false);
  const [voiceLifecycleStatus, setVoiceLifecycleStatus] = useState<string | null>(null);

  // Camera
  const [isCameraOn, setIsCameraOn] = useState(true);
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoStreamRef = useRef<MediaStream | null>(null);

  // Agora refs
  const agoraClientRef = useRef<any>(null);
  const agoraRtmRef = useRef<any>(null);
  const localAudioTrackRef = useRef<any>(null);
  const remoteAudioTracksRef = useRef<Map<string | number, any>>(new Map());
  const audioLifecycleRef = useRef<ReturnType<typeof createAudioLifecycle> | null>(null);
  const playRemoteAudioRef = useRef(createIdempotentAudioPlayer());
  const micChangeInFlightRef = useRef(false);
  const wasLocalSpeakingRef = useRef<boolean>(false);
  const authoritativeAgentIdRef = useRef(currentAgentId);
  useEffect(() => { authoritativeAgentIdRef.current = currentAgentId; }, [currentAgentId]);

  // ── Load session credentials ────────────────────────────────────────────────
  useEffect(() => {
    let disposed = false;
    const controller = new AbortController();
    const stored = sessionStorage.getItem(`session_${token}`);
    if (stored) {
      try {
        const creds = JSON.parse(stored) as SessionCredentials;
        setCredentials(creds);
        setCurrentAgentId(creds.current_agent_id);
        setCurrentAgentInfo(creds.selected_agents?.find((a) => a.agent_id === creds.current_agent_id) || null);
        setCredentialsLoading(false);
        console.log("[SESSION_CREDENTIALS_LOADED] channel:", creds.channel_name, "agents:", creds.agent_ids);
        return;
      } catch { /* fall through */ }
    }

    // Fallback: call start again (idempotent)
    console.log("[SESSION_CREDENTIALS_FALLBACK] Calling session start API");
    standardInterviewFetch(`${apiUrl}/api/v1/sessions/${token}/start`, { method: "POST", signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Session start failed (${res.status})`);
        }
        return res.json() as Promise<SessionCredentials>;
      })
      .then((creds) => {
        if (disposed) return;
        setCredentials(creds);
        setCurrentAgentId(creds.current_agent_id);
        setCurrentAgentInfo(creds.selected_agents?.find((a) => a.agent_id === creds.current_agent_id) || null);
        sessionStorage.setItem(`session_${token}`, JSON.stringify(creds));
      })
      .catch((err) => {
        if (disposed) return;
        setAgoraError(err.message || "Failed to load session credentials.");
      })
      .finally(() => { if (!disposed) setCredentialsLoading(false); });
    return () => { disposed = true; controller.abort(); };
  }, [token, apiUrl]);

  // ── Camera stream ───────────────────────────────────────────────────────────
  useEffect(() => {
    let active = true;
    if (!isCameraOn) {
      videoStreamRef.current?.getTracks().forEach((t) => t.stop());
      videoStreamRef.current = null;
      if (videoRef.current) videoRef.current.srcObject = null;
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false })
      .then((stream) => {
        if (!active) { stream.getTracks().forEach((t) => t.stop()); return; }
        videoStreamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      })
      .catch(() => {});
    return () => {
      active = false;
      videoStreamRef.current?.getTracks().forEach((t) => t.stop());
      videoStreamRef.current = null;
    };
  }, [isCameraOn]);

  // ── Session timer ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (connectionState !== "connected") return;
    const id = setInterval(() => setSessionDuration((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [connectionState]);


  // The backend applies a handoff/completion only after Agora speech drains.
  // RTM transcript delivery is not an authoritative completion signal.
  useEffect(() => {
    if (!credentials || connectionState !== "connected" || isEnding) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();
    let previousState = "";
    const poll = async () => {
      try {
        const res = await standardInterviewFetch(`${apiUrl}/api/v1/sessions/${token}`, { signal: controller.signal, cache: "no-store" });
        if (!res.ok) throw new Error(`HTTP_${res.status}`);
        const session = await res.json();
        if (disposed) return;
        const snapshot = `${session.status}:${session.current_agent_id}:${session.voice_lifecycle_status}`;
        if (snapshot !== previousState) {
          console.log("[SESSION_STATE_SYNC]", { interview_id: credentials.interview_id, channel: credentials.channel_name,
            status: session.status, current_agent_id: session.current_agent_id,
            voice_lifecycle_status: session.voice_lifecycle_status ?? null, at: new Date().toISOString() });
          previousState = snapshot;
        }
        setVoiceLifecycleStatus(session.voice_lifecycle_status ?? null);
        if (session.current_agent_id) {
          setCurrentAgentId(session.current_agent_id);
          const agent = credentials.selected_agents.find(a => a.agent_id === session.current_agent_id);
          if (agent) setCurrentAgentInfo(agent);
        }
        if (session.status === "COMPLETED") {
          setIsEnding(true);
          router.push(`/interview/${token}/done`);
          return;
        }
      } catch (err) {
        if (!disposed) console.warn("[SESSION_STATE_SYNC_FAILED]", { interview_id: credentials.interview_id,
          error_type: err instanceof Error ? err.name : "UnknownError" });
      }
      if (!disposed) timer = setTimeout(poll, 2000);
    };
    void poll();
    return () => { disposed = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [apiUrl, token, credentials, connectionState, isEnding, router]);

  // ── Initialize Agora RTC once credentials are available ─────────────────────
  useEffect(() => {
    if (!credentials || credentialsLoading) return;
    const lifecycle = createAudioLifecycle();
    audioLifecycleRef.current?.dispose();
    audioLifecycleRef.current = lifecycle;
    void initAgora(credentials, lifecycle);
    return () => {
      lifecycle.dispose();
      if (audioLifecycleRef.current === lifecycle) audioLifecycleRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [credentials, credentialsLoading]);

  const initAgora = useCallback(async (creds: SessionCredentials, lifecycle: ReturnType<typeof createAudioLifecycle>) => {
    if (typeof window === "undefined") return;
    setConnectionState("connecting");
    setAgoraError(null);
    setPresentAgentUids([]);
    setRemoteParticipantCount(0);

    try {
      const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
      if (!lifecycle.active) return;
      AgoraRTC.setLogLevel(2); // warnings only

      const onAutoplayFailed = () => {
        if (!lifecycle.active) return;
        console.warn("[AGENT_AUDIO_AUTOPLAY_BLOCKED]", { interview_id: creds.interview_id,
          channel: creds.channel_name, at: new Date().toISOString() });
        setAutoplayBlocked(true);
        setAgentAudioState("play_failed");
      };
      AgoraRTC.onAudioAutoplayFailed = onAutoplayFailed;
      lifecycle.own(() => {
        if (AgoraRTC.onAudioAutoplayFailed === onAutoplayFailed) AgoraRTC.onAudioAutoplayFailed = undefined;
      });

      const client = AgoraRTC.createClient({ mode: "rtc", codec: "vp8" });
      agoraClientRef.current = client;
      lifecycle.own(() => {
        client.removeAllListeners();
        if (agoraClientRef.current === client) agoraClientRef.current = null;
        return client.leave();
      });
      const remoteTracks = new Map<string | number, any>();
      remoteAudioTracksRef.current = remoteTracks;
      const playAudio = createIdempotentAudioPlayer();
      playRemoteAudioRef.current = playAudio;
      lifecycle.own(() => {
        for (const track of remoteTracks.values()) track.stop();
        remoteTracks.clear();
      });
      const isAgentUid = createAgentUidFilter(creds.selected_agents);
      const agentUsers = () => client.remoteUsers.filter(user => isAgentUid(user.uid));
      const syncAgentPresence = (excludedUid?: string | number) => {
        const uids = agentUsers().map(user => String(user.uid)).filter(uid => uid !== String(excludedUid));
        setPresentAgentUids(uids);
        setRemoteParticipantCount(uids.length);
      };
      client.enableAudioVolumeIndicator();

      // ── RTC event handlers ──────────────────────────────────────────────────

      client.on("connection-state-change", (cur: string, prev: string, reason: string) => {
        console.log(`[RTC_STATE] ${prev} → ${cur}, reason: ${reason}`);
      });

      client.on("exception", (event: any) => {
        console.warn(`[RTC_EXCEPTION] code=${event.code} msg=${event.msg}`);
      });

      const traceIdentity = { interview_id: creds.interview_id, channel: creds.channel_name };
      const remoteMediaSamples = new Map<string | number, { speaking: boolean; loggedAt: number; bytes: number }>();
      const subscriptionsInFlight = new Set<string | number>();
      let lastMicDiagnosticsAt = 0;
      const safeError = (err: any) => ({
        error_type: typeof err?.name === "string" ? err.name : "UnknownError",
        code: typeof err?.code === "number" || /^[A-Z_0-9-]{1,64}$/.test(String(err?.code ?? "")) ? err.code : undefined,
      });

      // A remote agent can publish audio before the browser finishes joining.
      // Agora exposes that track through client.remoteUsers without replaying a
      // user-published event, so handle both the event and the post-join snapshot.
      const subscribeToAgentAudio = async (user: any, source: string) => {
        if (!lifecycle.active || !user || !isAgentUid(user.uid) || String(user.uid) === String(client.uid) || subscriptionsInFlight.has(String(user.uid))) return;
        if (remoteTracks.get(String(user.uid)) === user.audioTrack && user.audioTrack?.isPlaying) {
          setAgentAudioState("playing");
          return;
        }
        subscriptionsInFlight.add(String(user.uid));
        console.log("[AGENT_AUDIO_DISCOVERED]", { ...traceIdentity, source, uid: user.uid,
          hasAudio: Boolean(user.hasAudio), track: Boolean(user.audioTrack), at: new Date().toISOString() });
        try {
          try {
            await client.subscribe(user, "audio");
          } catch (err) {
            if (!lifecycle.active) return;
            console.warn("[AGENT_AUDIO_SUBSCRIBE_FAILED]", { ...traceIdentity, source, uid: user.uid, ...safeError(err) });
            setAgentAudioState("subscribe_failed");
            return;
          }
          if (!lifecycle.active) { user.audioTrack?.stop(); return; }
          console.log("[AGENT_AUDIO_SUBSCRIBED]", { ...traceIdentity, source, uid: user.uid, at: new Date().toISOString() });
          setAgentAudioState("subscribed");
          const track = user.audioTrack;
          if (!track) {
            console.warn("[AGENT_AUDIO_SUBSCRIBE_EMPTY]", { ...traceIdentity, uid: user.uid });
            setAgentAudioState("subscribe_failed");
            return;
          }
          const previousTrack = remoteTracks.get(String(user.uid));
          if (previousTrack && previousTrack !== track) previousTrack.stop();
          remoteTracks.set(String(user.uid), track);
          try {
            await playAudio(track);
            if (!lifecycle.active) { track.stop(); return; }
            // This proves the SDK play call returned; media counters below prove
            // received/decoded audio independently of this UI state.
            console.log("[AGENT_AUDIO_PLAYING]", { ...traceIdentity, source, uid: user.uid,
              sdk_playing: track.isPlaying, boundary: "sdk_play_call_returned", at: new Date().toISOString() });
            setAgentAudioState("playing");
          } catch (err: any) {
            if (!lifecycle.active) return;
            console.warn("[AGENT_AUDIO_PLAY_FAILED]", { ...traceIdentity, source, uid: user.uid, ...safeError(err) });
            if (err?.name === "NotAllowedError" || err?.code === "AUTOPLAY_FAILED") setAutoplayBlocked(true);
            setAgentAudioState("play_failed");
          }
        } finally {
          subscriptionsInFlight.delete(String(user.uid));
        }
      };

      client.on("user-joined", (user: any) => {
        if (!lifecycle.active) return;
        if (!isAgentUid(user.uid)) {
          console.log("[RTC_NON_AGENT_IGNORED]", { ...traceIdentity, uid: user.uid, source: "user-joined" });
          return;
        }
        console.log(`[AGENT_JOINED] uid=${user.uid}`);
        syncAgentPresence();
        setAgentAudioState("joined");
        if (user.hasAudio || user.audioTrack) {
          void subscribeToAgentAudio(user, "user-joined");
        }
      });

      client.on("user-left", (user: any) => {
        if (!lifecycle.active || !isAgentUid(user.uid)) return;
        console.log(`[AGENT_LEFT] uid=${user.uid}`);
        remoteTracks.get(String(user.uid))?.stop();
        remoteTracks.delete(String(user.uid));
        remoteMediaSamples.delete(String(user.uid));
        syncAgentPresence(user.uid);
        if (agentUsers().length === 0) {
          setAgentAudioState("waiting");
          setIsAISpeaking(false);
        }
      });

      client.on("user-published", async (user: any, mediaType: string) => {
        if (!lifecycle.active || !isAgentUid(user.uid)) return;
        console.log(`[AGENT_AUDIO_PUBLISHED] uid=${user.uid} mediaType=${mediaType}`);
        syncAgentPresence();

        if (mediaType === "audio") {
          setAgentAudioState("audio_published");
          await subscribeToAgentAudio(user, "user-published");
        }
      });

      client.on("user-unpublished", (user: any, mediaType: string) => {
        if (!lifecycle.active || !isAgentUid(user.uid)) return;
        console.log(`[AGENT_AUDIO_UNPUBLISHED] uid=${user.uid} mediaType=${mediaType}`);
        if (mediaType === "audio") {
          remoteTracks.get(String(user.uid))?.stop();
          remoteTracks.delete(String(user.uid));
          remoteMediaSamples.delete(String(user.uid));
          setIsAISpeaking(false);
          setAgentAudioState("joined");
        }
      });

      // ── Volume indicator — ONLY remote audio for agent speaking detection ──
      client.on("volume-indicator", (volumes: any[]) => {
        if (!lifecycle.active) return;
        let remoteSpeaking = false;
        let localSpeaking = false;
        let localVol = 0;
        let remoteVol = 0;
        let maxVol = 0;
        const localUid = client.uid;
        let activePhysicalAgentId: string | null = null;

        for (const vol of volumes) {
          const isLocal = String(vol.uid) === "0" || String(vol.uid) === String(localUid);
          if (!isLocal && !isAgentUid(vol.uid)) continue;
          maxVol = Math.max(maxVol, vol.level);
          if (isLocal) {
            localVol = Math.max(localVol, vol.level);
            if (vol.level > 12) localSpeaking = true;
          } else {
            // Only count as remote-speaking if a remote user with that uid actually exists
            if (agentUsers().some((u: any) => String(u.uid) === String(vol.uid))) {
              remoteVol = Math.max(remoteVol, vol.level);
              if (vol.level > 8) {
                remoteSpeaking = true;
                // Identify which logical agent this physical UID belongs to
                const matchedAgent = creds.selected_agents.find(a => String(a.agora_rtc_uid) === String(vol.uid));
                if (matchedAgent) {
                  activePhysicalAgentId = matchedAgent.agent_id;
                }
              }
            }
          }
        }

        if (localSpeaking && !wasLocalSpeakingRef.current) {
          wasLocalSpeakingRef.current = true;
          console.log(`[MIC_SPEECH_START] level=${localVol}`);
        } else if (!localSpeaking && wasLocalSpeakingRef.current) {
          wasLocalSpeakingRef.current = false;
          console.log("[MIC_SPEECH_END]");
        }

        // Diagnostic log if there's a mismatch between active logical agent and actual speaking agent
        if (remoteSpeaking && activePhysicalAgentId && activePhysicalAgentId !== authoritativeAgentIdRef.current) {
            console.warn(`[AGENT_IDENTITY_MISMATCH] logical=${authoritativeAgentIdRef.current} physical=${activePhysicalAgentId} runtime_uid=${volumes.find(v => isAgentUid(v.uid) && v.level > 8)?.uid}`);
        }

        // SDK metadata only: no recording and no raw audio samples retained.
        const mediaStats = client.getRemoteAudioStats();
        for (const [uid, track] of remoteTracks) {
          const stats = mediaStats[String(uid)];
          const decodedLevel = track.getVolumeLevel();
          const speaking = volumes.some(v => String(v.uid) === String(uid) && v.level > 8);
          const previous = remoteMediaSamples.get(uid);
          const now = Date.now();
          const bytes = stats?.receiveBytes ?? 0;
          if (!previous || previous.speaking !== speaking || now - previous.loggedAt >= 10000) {
            const stage = speaking && !previous?.speaking ? "[AGENT_SPEECH_START]"
              : !speaking && previous?.speaking ? "[AGENT_SPEECH_END]" : "[AGENT_AUDIO_MEDIA]";
            console.log(stage, { ...traceIdentity, uid, at: new Date(now).toISOString(),
              decoded_level: Number(decodedLevel.toFixed(4)), sdk_playing: track.isPlaying,
              stats_ready: Boolean(stats), receive_bytes: stats?.receiveBytes ?? null,
              receive_bytes_delta: previous ? Math.max(0, bytes - previous.bytes) : null,
              receive_packets: stats?.receivePackets ?? null, receive_level: stats?.receiveLevel ?? null,
              receive_bitrate: stats?.receiveBitrate ?? null, ...remoteAudioQualityDiagnostics(stats) });
            remoteMediaSamples.set(uid, { speaking, loggedAt: now, bytes });
          }
        }

        const micTrack = localAudioTrackRef.current;
        if (micTrack && Date.now() - lastMicDiagnosticsAt >= 10000) {
          lastMicDiagnosticsAt = Date.now();
          console.log("[MIC_MEDIA]", { ...traceIdentity, at: new Date().toISOString(),
            ...microphoneDiagnostics(micTrack.getMediaStreamTrack(), client.getLocalAudioStats()) });
        }

        setCurrentVolume(maxVol);
        setIsAISpeaking(remoteSpeaking);
        setIsCandidateSpeaking(localSpeaking);
        setPhysicalSpeakingAgentId(remoteSpeaking ? activePhysicalAgentId : null);
      });

      // ── Join RTC channel ─────────────────────────────────────────────────────
      console.log(`[RTC_JOIN] Joining channel: ${creds.channel_name} (interview: ${creds.interview_id})`);
      const joinedUid = await client.join(creds.agora_app_id, creds.channel_name, creds.agora_token, creds.agora_uid || 0);
      if (!lifecycle.active) { await client.leave().catch(() => {}); return; }
      console.log(`[LOCAL_UID] Joined as uid=${joinedUid ?? client.uid}`);
      setConnectionState("connected");
      syncAgentPresence();

      // Subscribe to any agent that was already present/publishing at the
      // instant of join. This closes the race that otherwise leaves the UI in
      // “joined — waiting for audio” indefinitely.
      for (const remoteUser of agentUsers()) {
        if (remoteUser.hasAudio || remoteUser.audioTrack) {
          void subscribeToAgentAudio(remoteUser, "post-join-snapshot");
        } else {
          console.log(`[AGENT_REMOTE_SNAPSHOT] uid=${remoteUser.uid} hasAudio=false`);
        }
      }

      // ── Publish microphone ───────────────────────────────────────────────────
      micChangeInFlightRef.current = true;
      try {
        const micTrack = await AgoraRTC.createMicrophoneAudioTrack({
          encoderConfig: "high_quality_stereo",
          AEC: true,
          ANS: true,
          AGC: true,
        });
        if (!lifecycle.own(() => {
          micTrack.close();
          if (localAudioTrackRef.current === micTrack) localAudioTrackRef.current = null;
        })) return;
        localAudioTrackRef.current = micTrack;
        await client.publish([micTrack]);
        if (!lifecycle.active) return;
        console.log("[MIC_PUBLISHED] Local microphone active on", creds.channel_name);
        console.log("[MIC_CAPTURE_SETTINGS]", { ...traceIdentity, at: new Date().toISOString(),
          ...microphoneDiagnostics(micTrack.getMediaStreamTrack(), client.getLocalAudioStats()) });
        setMicState("active");
      } catch (micErr: any) {
        if (!lifecycle.active) return;
        localAudioTrackRef.current?.close();
        localAudioTrackRef.current = null;
        console.error("[MIC_ERROR]", micErr.name, micErr.message);
        if (micErr.name === "NotAllowedError" || micErr.code === "PERMISSION_DENIED") {
          setMicState("permission_required");
          setAgoraError("Microphone permission denied. Please allow access in browser settings.");
        } else {
          setMicState("error");
          setAgoraError(`Microphone error: ${micErr.message}`);
        }
      } finally {
        if (audioLifecycleRef.current === lifecycle) micChangeInFlightRef.current = false;
      }

      // ── RTM listener for agent handoff (SWITCH_AGENT) and transcript ─────────
      try {
        const AgoraRTM = (await import("agora-rtm-sdk")).default;
        if (!lifecycle.active) return;
        const { RTM } = AgoraRTM;
        const rtmClient = new RTM(creds.agora_app_id, creds.rtm_user_id);
        agoraRtmRef.current = rtmClient;
        lifecycle.own(() => {
          if (agoraRtmRef.current === rtmClient) agoraRtmRef.current = null;
          return rtmClient.logout();
        });

        const transcriptLogs = new Set<string>();
        rtmClient.addEventListener("message", async (event: any) => {
          if (!lifecycle.active) return;
          let raw = event.message;
          if (raw instanceof Uint8Array) raw = new TextDecoder("utf-8").decode(raw);
          if (typeof raw !== "string") return;
          try {
            const parsed = JSON.parse(raw);

            // A requested handoff can precede the final spoken words. The
            // session poll applies the persona only after the backend transition.
            if (parsed.action === "SWITCH_AGENT" && parsed.target_agent_id) {
              console.log("[AGENT_SWITCH_REQUESTED]", { ...traceIdentity,
                target_agent_id: parsed.target_agent_id, at: new Date().toISOString() });
            }

            // Transcript events
            const hasText = Boolean(parsed.text || parsed.content);
            const isTranscript =
              parsed.event_type === "TRANSCRIPT_UPDATED" ||
              parsed.object === "agent.message" ||
              parsed.object === "assistant.transcription" ||
              parsed.object === "user.transcription" ||
              hasText;

            const eventKind = String(parsed.object ?? parsed.event_type ?? "unknown");
            if (/metric|error/i.test(eventKind)) {
              const numericFields = Object.fromEntries(Object.entries(parsed)
                .filter(([key, value]) => /^(code|turn_id|timestamp|time|duration_ms|latency_ms|ttft_ms|ttfb_ms)$/.test(key)
                  && typeof value === "number" && Number.isFinite(value)));
              console.log(/error/i.test(eventKind) ? "[RTM_AGENT_ERROR]" : "[RTM_AGENT_METRICS]", {
                ...traceIdentity, object: eventKind, uid: event.publisher, ...numericFields, at: new Date().toISOString(),
              });
            }

            if (isTranscript && (parsed.text || parsed.content)?.trim()) {
              const text = (parsed.text || parsed.content).trim();
              const isFinal = parsed.is_final === true || parsed.final === true || parsed.status === "final" || parsed.turn_status === 1;
              
              const stableUid = parsed.uid || event.publisher || "unknown";
              const stableTs = parsed.start_ts ?? parsed.timestamp ?? parsed.time ?? "0";
              const fallbackId = `rtm-${stableUid}-${stableTs}`;
              const turnId = String(parsed.turn_id ?? parsed.id ?? fallbackId);
              
              const role = parsed.role || (parsed.object?.includes("user") ? "user" : "assistant");
              const isCandidate = role === "user" || role === "candidate";
              // Agora uses one turn_id for a candidate answer and its agent
              // response. Namespace by cloud generation/publisher and speaker so
              // progressive updates replace only that speaker's own transcript.
              const generation = String(parsed.agent_id ?? event.publisher ?? "unknown");
              const transcriptId = `rtm:${generation}:${role}:${stableUid}:${turnId}`;
              const logKey = `${transcriptId}:${isFinal ? "final" : "started"}`;
              if (!transcriptLogs.has(logKey)) {
                transcriptLogs.add(logKey);
                console.log(isFinal ? "[RTM_TRANSCRIPT_FINAL]" : "[RTM_TRANSCRIPT_STARTED]", {
                  ...traceIdentity, object: parsed.object, uid: stableUid, turn_id: turnId, role,
                  text_characters: text.length, turn_status: parsed.turn_status, at: new Date().toISOString(),
                });
              }

              // Do not synthesize agent speech in the browser. The interview
              // contract requires Agora audio from the Conversational AI agent;
              // a local speech-synthesis fallback masks missing publication and
              // can feed the agent's own greeting back through the microphone.

              // Store to backend and synchronize active agent
              try {
                const res = await standardInterviewFetch(`${apiUrl}/api/v1/interviews/${token}/transcript-events`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    id: transcriptId,
                    channel: creds.channel_name,
                    speaker_uid: String(stableUid),
                    speaker: isCandidate ? "candidate" : "agent",
                    role,
                    text,
                    timestamp: parsed.time || Date.now(),
                    is_final: isFinal,
                    source: "agora_rtm",
                    metadata: { raw_status: parsed.status, turn_status: parsed.turn_status, publisher: event.publisher,
                      agora_turn_id: turnId, cloud_agent_id: parsed.agent_id ?? null },
                  }),
                });
                if (res.ok && isFinal) console.log("[RTM_TRANSCRIPT_PERSISTED]", {
                  ...traceIdentity, turn_id: turnId, role, at: new Date().toISOString(),
                });
                if (!res.ok) console.warn("[RTM_TRANSCRIPT_PERSIST_FAILED]", { ...traceIdentity, turn_id: turnId, status: res.status });
              } catch (err) { console.warn("[RTM_TRANSCRIPT_PERSIST_FAILED]", { ...traceIdentity, turn_id: turnId, ...safeError(err) }); }
            }
          } catch { /* non-JSON RTM */ }
        });

        rtmClient.addEventListener("status", (event: any) => {
          console.log(`[RTM_STATUS] ${event.state} reason=${event.reason}`);
        });

        await rtmClient.login({ token: creds.agora_token });
        if (!lifecycle.active) { await rtmClient.logout().catch(() => {}); return; }
        await rtmClient.subscribe(creds.channel_name, { withMessage: true, withPresence: true, withMetadata: false, withLock: false });
        if (!lifecycle.active) { await rtmClient.logout().catch(() => {}); return; }
        console.log(`[RTM_SUBSCRIBED] channel=${creds.channel_name}`);
      } catch (rtmErr: any) {
        if (!lifecycle.active) return;
        console.warn("[RTM_ERROR]", rtmErr?.message);
      }

    } catch (err: any) {
      if (!lifecycle.active) return;
      lifecycle.dispose();
      console.error("[AGORA_INIT_ERROR]", err.message);
      setConnectionState("error");
      setAgoraError(err.message || "Failed to connect to Agora voice runtime");
    }
  }, []); // eslint-disable-line

  // ── Cleanup on unmount ──────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      videoStreamRef.current?.getTracks().forEach((t) => t.stop());
      sessionStorage.removeItem(`session_${token}`);
    };
  }, [token]);

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleEnableAudio = useCallback(() => {
    const lifecycle = audioLifecycleRef.current;
    if (!lifecycle?.active || !credentials) return;
    const isAgentUid = createAgentUidFilter(credentials.selected_agents);
    // Clear before play so a new SDK autoplay-failed callback remains visible.
    setAutoplayBlocked(false);
    remoteAudioTracksRef.current.forEach(async (track, uid) => {
      if (!isAgentUid(uid)) return;
      try {
        // SDK isPlaying can mean a play request exists even when browser autoplay
        // was blocked. An explicit user retry replaces that request safely.
        if (autoplayBlocked && track.isPlaying) track.stop();
        await playRemoteAudioRef.current(track);
        if (!lifecycle.active) { track.stop(); return; }
        console.log("[AGENT_AUDIO_PLAY_RETRY]", { uid, interview_id: token,
          sdk_playing: track.isPlaying, at: new Date().toISOString() });
        setAgentAudioState("playing");
      } catch (err) {
        if (!lifecycle.active) return;
        console.warn("[AGENT_AUDIO_PLAY_RETRY_FAILED]", { uid, interview_id: token,
          error_type: err instanceof Error ? err.name : "UnknownError" });
        setAgentAudioState("play_failed");
      }
    });
  }, [token, credentials, autoplayBlocked]);

  const toggleMicrophone = useCallback(async () => {
    const lifecycle = audioLifecycleRef.current;
    const client = agoraClientRef.current;
    if (!lifecycle?.active || !client || connectionState !== "connected" || micChangeInFlightRef.current) return;
    micChangeInFlightRef.current = true;
    let newlyCreatedTrack: any = null;
    try {
      if (!localAudioTrackRef.current) {
        const AgoraRTC = (await import("agora-rtc-sdk-ng")).default;
        if (!lifecycle.active) return;
        const micTrack = await AgoraRTC.createMicrophoneAudioTrack({ encoderConfig: "high_quality_stereo", AEC: true, ANS: true, AGC: true });
        newlyCreatedTrack = micTrack;
        if (!lifecycle.own(() => {
          micTrack.close();
          if (localAudioTrackRef.current === micTrack) localAudioTrackRef.current = null;
        })) return;
        localAudioTrackRef.current = micTrack;
        await client.publish([micTrack]);
        if (!lifecycle.active) return;
        console.log("[MIC_CAPTURE_SETTINGS]", { interview_id: token, at: new Date().toISOString(),
          ...microphoneDiagnostics(micTrack.getMediaStreamTrack(), client.getLocalAudioStats()) });
        setMicState("active");
        setAgoraError(null);
        return;
      }
      const enabled = micState !== "active";
      await localAudioTrackRef.current.setEnabled(enabled);
      if (!lifecycle.active) return;
      setMicState(enabled ? "active" : "muted");
      console.log("[MIC_CAPTURE_SETTINGS]", { interview_id: token, at: new Date().toISOString(),
        ...microphoneDiagnostics(localAudioTrackRef.current.getMediaStreamTrack(), client.getLocalAudioStats()) });
    } catch {
      newlyCreatedTrack?.close();
      if (localAudioTrackRef.current === newlyCreatedTrack) localAudioTrackRef.current = null;
      if (lifecycle.active) {
        setMicState("error");
        setAgoraError("Unable to update the microphone. Check browser microphone access and retry.");
      }
    } finally {
      if (audioLifecycleRef.current === lifecycle) micChangeInFlightRef.current = false;
    }
  }, [micState, connectionState, token]);

  const handleLeaveInterview = useCallback(async () => {
    setIsEnding(true);
    audioLifecycleRef.current?.dispose();
    try {
      await standardInterviewFetch(`${apiUrl}/api/v1/sessions/${token}/stop`, { method: "POST" }).catch(() => {});
    } catch { }
    router.push(`/interview/${token}/done`);
  }, [token, apiUrl, router]);

  // ── Status helpers ──────────────────────────────────────────────────────────

  // Determine the actual UI agent name based on who is physically speaking, 
  // falling back to the logical current agent.
  let activeAgentId = currentAgentId;
  let activeAgentInfo = currentAgentInfo;
  if (physicalSpeakingAgentId && physicalSpeakingAgentId !== currentAgentId) {
      activeAgentId = physicalSpeakingAgentId;
      activeAgentInfo = credentials?.selected_agents?.find(a => a.agent_id === physicalSpeakingAgentId) || null;
  }

  const agentName = activeAgentInfo?.name || (activeAgentId === "jordan" ? "Jordan" : "Alex");
  const agentRole = activeAgentInfo?.role || "";

  const agentStatusLabel = (): string => {
    if (voiceLifecycleStatus === "service_paused") return "Interview paused — service unavailable";
    if (voiceLifecycleStatus === "paused") return "Interview paused";
    switch (agentAudioState) {
      case "waiting": return `Waiting for ${agentName} to join…`;
      case "joined": return `${agentName} joined — waiting for audio…`;
      case "audio_published": return `${agentName} published audio…`;
      case "subscribed": return `Starting ${agentName}'s audio…`;
      case "subscribe_failed": return `Unable to subscribe to ${agentName}'s audio`;
      case "playing": return isAISpeaking ? `${agentName} is speaking…` : isCandidateSpeaking ? "Listening to you…" : `${agentName} is ready · Speak anytime`;
      case "play_failed": return autoplayBlocked ? "Audio blocked — click Enable Audio" : "Audio playback failed";
      default: return "Connecting…";
    }
  };

  const showAllAgents = credentials && credentials.selected_agents.length > 1;

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="fixed inset-0 bg-bg flex flex-col overflow-hidden text-text-primary font-sans">

      {/* ── Top Bar ───────────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-3.5 border-b border-border bg-surface/95 backdrop-blur-md shrink-0 z-20">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand shadow-sm">
            <Radio className="h-4 w-4 text-text-inverse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold tracking-tight">Intra AI</span>
              <span className="text-[10px] font-semibold bg-brand-light text-brand border border-brand/20 px-1.5 py-0.5 rounded">LIVE</span>
            </div>
            <p className="text-[11px] text-text-muted">
              {credentials?.job_title || "Interview Session"} {credentials?.company ? `· ${credentials.company}` : ""}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Connection */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-bg border border-border">
            <span className={cn("h-2 w-2 rounded-full", connectionState === "connected" ? "bg-success animate-pulse" : connectionState === "connecting" ? "bg-warning animate-ping" : "bg-error")} />
            <span className="text-text-primary">
              {connectionState === "connected" ? "Connected" : connectionState === "connecting" ? "Connecting…" : "Disconnected"}
            </span>
          </div>

          {/* Agent audio state */}
          <div className="flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium bg-bg border border-border">
            <span className={cn("h-2 w-2 rounded-full", agentAudioState === "playing" ? "bg-success animate-pulse" : agentAudioState === "waiting" ? "bg-warning animate-pulse" : "bg-brand animate-pulse")} />
            <span className="text-text-primary">
              {agentAudioState === "playing" ? `${agentName}: Audio Active` :
               agentAudioState === "play_failed" ? (autoplayBlocked ? "Audio Blocked" : "Playback Failed") :
               agentAudioState === "subscribe_failed" ? "Audio Subscription Failed" :
               agentAudioState === "waiting" ? `Waiting for ${agentName}` :
               `${agentName}: Connecting`}
            </span>
          </div>

          {/* Timer */}
          <div className="flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-medium bg-bg border border-border text-text-primary">
            <Clock className="h-3.5 w-3.5 text-text-muted" />
            <span>{formatSeconds(sessionDuration)}</span>
          </div>
        </div>

        <button
          id="btn-end-interview"
          onClick={handleLeaveInterview}
          disabled={isEnding}
          className="flex items-center gap-1.5 text-xs font-semibold text-text-inverse bg-error hover:bg-red-800 px-3.5 py-1.5 rounded-full shadow-sm disabled:opacity-50 transition-colors"
        >
          <PhoneOff className="h-3.5 w-3.5" />
          <span>Leave</span>
        </button>
      </header>

      {/* ── Autoplay blocked banner ─────────────────────────────────────────── */}
      {autoplayBlocked && (
        <div className="bg-brand-light border-b border-brand/20 px-6 py-2.5 flex items-center justify-between text-xs text-brand z-10 shrink-0">
          <div className="flex items-center gap-2">
            <Volume2 className="h-4 w-4 text-brand shrink-0 animate-bounce" />
            <span>Interview audio is blocked. Click to enable so you can hear {agentName}.</span>
          </div>
          <button
            id="btn-enable-audio"
            onClick={handleEnableAudio}
            className="flex items-center gap-1 px-3 py-1 rounded-full bg-brand hover:bg-brand-hover text-text-inverse font-semibold transition-colors shadow-sm"
          >
            <Volume2 className="h-3 w-3" />
            Enable Interview Audio
          </button>
        </div>
      )}

      {/* ── Permission / Error banner ───────────────────────────────────────── */}
      {agoraError && (
        <div className="bg-warning-light border-b border-warning/20 px-6 py-2.5 flex items-center justify-between text-xs text-warning z-10 shrink-0">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-warning shrink-0" />
            <span>{agoraError}</span>
          </div>
          <button
            onClick={toggleMicrophone}
            className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-surface hover:bg-warning-light border border-warning/30 font-medium text-warning transition-colors"
          >
            <RefreshCw className="h-3 w-3" />
            Retry
          </button>
        </div>
      )}

      {/* ── Main content ───────────────────────────────────────────────────── */}
      <div className="flex-1 flex min-h-0">

        {/* Left: Camera + Controls */}
        <div className="flex-1 flex flex-col min-h-0 bg-bg p-5">
          <div className="relative flex-1 rounded-2xl overflow-hidden bg-surface border border-border flex flex-col items-center justify-center min-h-0 shadow-sm">

            {/* Camera feed */}
            {isCameraOn ? (
              <video ref={videoRef} autoPlay playsInline muted className="absolute inset-0 w-full h-full object-cover scale-x-[-1]" />
            ) : (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-bg">
                <div className="h-20 w-20 rounded-full bg-bg border border-border flex items-center justify-center">
                  <User className="h-10 w-10 text-text-muted" />
                </div>
                <p className="text-xs text-text-muted">Camera off</p>
              </div>
            )}

            {/* Vignette */}
            <div className="absolute inset-0 bg-gradient-to-t from-bg/80 via-transparent to-bg/20 pointer-events-none" />

            {/* AI Avatar pip (top right) */}
            <div className="absolute top-5 right-5 z-10">
              <AIAvatarPip isSpeaking={isAISpeaking} audioState={agentAudioState} agentName={agentName} />
            </div>

            {/* Multi-agent indicator (top left) if both agents */}
            {showAllAgents && (
              <div className="absolute top-5 left-5 z-10">
                <div className="bg-surface/95 backdrop-blur-md border border-border rounded-full px-3 py-1.5 flex items-center gap-2">
                  <Users className="h-3.5 w-3.5 text-text-muted" />
                  <span className="text-xs text-text-primary">
                    {credentials.selected_agents.map((a) => a.name).join(" + ")}
                  </span>
                </div>
              </div>
            )}

            {/* Agent connecting overlay (waiting state) */}
            {agentAudioState === "waiting" && connectionState === "connected" && (
              <div className="absolute inset-0 flex items-center justify-center bg-bg/40 backdrop-blur-sm">
                <div className="bg-surface/95 border border-border rounded-2xl px-8 py-6 flex flex-col items-center gap-3">
                  <div className="relative h-14 w-14 rounded-full bg-brand-light border border-brand/20 flex items-center justify-center">
                    <Waves className="h-6 w-6 text-brand animate-pulse" />
                    <span className="absolute -bottom-0.5 -right-0.5 h-3.5 w-3.5 rounded-full bg-warning/80 border-2 border-surface" />
                  </div>
                  <p className="text-sm font-semibold text-text-primary">Connecting to your AI interviewer…</p>
                  <p className="text-xs text-text-muted">{agentName} is joining the channel</p>
                </div>
              </div>
            )}

            {/* Audio state progress (subscribed but not yet playing) */}
            {(agentAudioState === "audio_published" || agentAudioState === "subscribed") && (
              <div className="absolute bottom-24 inset-x-6 flex justify-center">
                <div className="bg-brand-light border border-brand/20 rounded-full px-4 py-1.5 text-xs text-brand flex items-center gap-2">
                  <RefreshCw className="h-3 w-3 animate-spin" />
                  Setting up {agentName}&apos;s audio stream…
                </div>
              </div>
            )}

            {/* Audio playing confirmation */}
            {agentAudioState === "playing" && !isAISpeaking && remoteParticipantCount > 0 && (
              <div className="absolute top-5 left-1/2 -translate-x-1/2 z-10">
                <div className="bg-success-light border border-success/30 rounded-full px-3 py-1 text-[11px] text-success flex items-center gap-1.5">
                  <CheckCircle2 className="h-3 w-3" />
                  {agentName} is ready
                </div>
              </div>
            )}

            {/* Bottom status + controls */}
            <div className="absolute bottom-6 inset-x-6 flex flex-col items-center gap-3 z-10">
              <div className="bg-surface/95 backdrop-blur-md border border-border px-6 py-3 rounded-2xl shadow-sm flex items-center gap-4 max-w-md w-full justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <div className={cn(
                    "h-3 w-3 rounded-full shrink-0",
                    isAISpeaking ? "bg-brand animate-ping" :
                    isCandidateSpeaking ? "bg-success animate-pulse" :
                    agentAudioState === "playing" ? "bg-success" :
                    "bg-warning animate-pulse"
                  )} />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold truncate">{agentStatusLabel()}</p>
                    <p className="text-[10px] text-text-muted truncate">
                      {agentAudioState === "playing"
                        ? isAISpeaking ? "Agent audio playing" : isCandidateSpeaking ? "Transmitting via Agora ASR" : "Agora Voice Channel Active"
                        : `Channel: ${credentials?.channel_name || token}`}
                    </p>
                  </div>
                </div>
                <WaveformVisualizer isActive={isAISpeaking || isCandidateSpeaking} isAgent={isAISpeaking} volumeLevel={currentVolume} />
              </div>

              <div className="flex items-center gap-3 bg-surface/95 backdrop-blur-md border border-border p-2 rounded-full shadow-sm">
                <button
                  id="btn-toggle-mic"
                  onClick={toggleMicrophone}
                  className={cn(
                    "h-12 w-12 rounded-full flex items-center justify-center transition-all duration-200 shadow-sm",
                    micState === "active" ? "bg-brand text-text-inverse hover:bg-brand-hover hover:scale-105" :
                    micState === "muted" ? "bg-warning-light text-warning border border-warning/30 hover:bg-warning/10" :
                    "bg-error text-text-inverse hover:bg-red-800 animate-pulse"
                  )}
                >
                  {micState === "active" ? <Mic className="h-5 w-5" /> : <MicOff className="h-5 w-5" />}
                </button>
                <button
                  id="btn-toggle-camera"
                  onClick={() => setIsCameraOn((v) => !v)}
                  className={cn("h-12 w-12 rounded-full flex items-center justify-center transition-all duration-200 shadow-sm", isCameraOn ? "bg-brand-light text-brand hover:bg-brand/10" : "bg-bg text-text-muted border border-border")}
                >
                  {isCameraOn ? <Camera className="h-5 w-5" /> : <CameraOff className="h-5 w-5" />}
                </button>
                {autoplayBlocked && (
                  <button
                    onClick={handleEnableAudio}
                    className="h-12 w-12 rounded-full bg-brand hover:bg-brand-hover text-text-inverse flex items-center justify-center shadow-sm transition-colors"
                    title="Enable audio"
                  >
                    <Volume2 className="h-5 w-5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Right: Session info */}
        <div className="w-80 flex flex-col border-l border-border bg-surface shrink-0">
          {/* Agent info */}
          <div className="px-4 pt-4 pb-3 shrink-0">
            <div className="flex items-center gap-3">
              <div className={cn(
                "h-10 w-10 rounded-full flex items-center justify-center border-2 shrink-0",
                agentAudioState === "playing" ? "border-success/30 bg-success-light" : "border-border bg-bg"
              )}>
                <span className="text-sm font-bold text-text-primary">{agentName[0]}</span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-text-primary truncate">{agentName}</p>
                <p className="text-xs text-text-muted truncate">{agentRole || "AI Interviewer"}</p>
              </div>
              <div className={cn(
                "ml-auto h-2.5 w-2.5 rounded-full shrink-0",
                agentAudioState === "playing" ? "bg-success animate-pulse" :
                agentAudioState === "waiting" ? "bg-warning animate-pulse" :
                "bg-brand animate-pulse"
              )} />
            </div>

            {/* If multiple agents, show all */}
            {showAllAgents && credentials && (
              <div className="mt-3 space-y-1.5">
                <p className="text-[10px] text-text-muted px-2">Interview team</p>
                {credentials.selected_agents.map((a) => (
                  <div key={a.agent_id} className={cn(
                    "flex items-center gap-2 px-2 py-1 rounded-lg text-xs",
                    a.agent_id === currentAgentId ? "bg-brand-light border border-brand/20" : "text-text-muted"
                  )}>
                    <span className={cn("font-medium", a.agent_id === currentAgentId ? "text-brand" : "text-text-muted")}>{a.name}</span>
                    <span className="text-text-muted">{a.role}</span>
                    <span className="ml-auto text-[10px] whitespace-nowrap">
                      {agentPresenceLabel(presentAgentUids.includes(String(a.agora_rtc_uid)),
                        a.agent_id === currentAgentId, isAISpeaking && a.agent_id === physicalSpeakingAgentId)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
