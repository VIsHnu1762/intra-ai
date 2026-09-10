"use client";

import { standardInterviewFetch } from "@/lib/api/standard-interview-fetch";

import { useState, useEffect, useRef, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import {
  Camera,
  CameraOff,
  Mic,
  MicOff,
  Volume2,
  CheckCircle2,
  XCircle,
  Loader2,
  Calendar,
  Clock,
  Users,
  ChevronRight,
  AlertCircle,
  RefreshCw,
  Radio,
  Sparkles,
  ShieldCheck,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─── Types ────────────────────────────────────────────────────────────────────

interface AgentInfo {
  agent_id: string;
  name: string;
  role: string;
  description: string;
  focal_competencies: string[];
}

interface SessionInfo {
  interview_id: string;
  channel_name: string;
  status: string;
  agent_ids: string[];
  current_agent_id: string;
  selected_agents: AgentInfo[];
  scheduled_start: string | null;
  duration_minutes: number;
  job_title: string | null;
  company: string | null;
}

type DeviceState = "idle" | "checking" | "ready" | "denied" | "error";

interface DeviceStatus {
  mic: DeviceState;
  camera: DeviceState;
  speaker: DeviceState;
  micLabel: string;
  cameraLabel: string;
  micLevel: number;     // 0–100 real audio level
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatScheduledTime(iso: string | null): { date: string; time: string } | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return null;
  return {
    date: d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }),
    time: d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true }),
  };
}

function isSessionOpen(scheduledStart: string | null, windowMinutes = 10): boolean {
  if (!scheduledStart) return true;
  const open = new Date(new Date(scheduledStart).getTime() - windowMinutes * 60 * 1000);
  return new Date() >= open;
}

function timeUntilOpen(scheduledStart: string | null, windowMinutes = 10): string | null {
  if (!scheduledStart) return null;
  const open = new Date(new Date(scheduledStart).getTime() - windowMinutes * 60 * 1000);
  const diff = open.getTime() - Date.now();
  if (diff <= 0) return null;
  const mins = Math.floor(diff / 60000);
  const secs = Math.floor((diff % 60000) / 1000);
  return `${mins}m ${secs}s`;
}

// ─── Main ─────────────────────────────────────────────────────────────────────

export default function PrepPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const router = useRouter();
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Interview session info
  const [sessionInfo, setSessionInfo] = useState<SessionInfo | null>(null);
  const [sessionLoading, setSessionLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Device checks
  const [devices, setDevices] = useState<DeviceStatus>({
    mic: "idle",
    camera: "idle",
    speaker: "idle",
    micLabel: "",
    cameraLabel: "",
    micLevel: 0,
  });

  // Camera preview
  const videoRef = useRef<HTMLVideoElement>(null);
  const videoStreamRef = useRef<MediaStream | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const micLevelRafRef = useRef<number | null>(null);

  // Entering interview
  const [isEntering, setIsEntering] = useState(false);
  const [enterError, setEnterError] = useState<string | null>(null);

  // Schedule countdown
  const [countdown, setCountdown] = useState<string | null>(null);

  // ── Fetch session info ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!token) return;
    setSessionLoading(true);

    standardInterviewFetch(`${apiUrl}/api/v1/sessions/${token}`)
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Session not found (${res.status})`);
        }
        return res.json() as Promise<SessionInfo>;
      })
      .then((data) => {
        setSessionInfo(data);
        setSessionError(null);
      })
      .catch((err) => {
        setSessionError(err.message || "Failed to load interview information.");
      })
      .finally(() => setSessionLoading(false));
  }, [token, apiUrl]);

  // ── Countdown ticker ────────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionInfo?.scheduled_start) return;
    const tick = () => {
      const remaining = timeUntilOpen(sessionInfo.scheduled_start, 10);
      setCountdown(remaining);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sessionInfo?.scheduled_start]);

  // ── Device checks ───────────────────────────────────────────────────────────
  const checkMicrophone = useCallback(async () => {
    setDevices((d) => ({ ...d, mic: "checking", micLevel: 0 }));
    // Stop any existing mic stream
    if (micStreamRef.current) {
      micStreamRef.current.getTracks().forEach((t) => t.stop());
      micStreamRef.current = null;
    }
    if (micLevelRafRef.current) {
      cancelAnimationFrame(micLevelRafRef.current);
      micLevelRafRef.current = null;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
      micStreamRef.current = stream;
      const label = stream.getAudioTracks()[0]?.label || "Microphone";

      // Real-time audio level via Web Audio API
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const dataArr = new Uint8Array(analyser.frequencyBinCount);
      const measureLevel = () => {
        analyser.getByteTimeDomainData(dataArr);
        let sum = 0;
        for (const v of dataArr) sum += Math.abs(v - 128);
        const level = Math.min(100, (sum / dataArr.length) * 4);
        setDevices((d) => ({ ...d, micLevel: level }));
        micLevelRafRef.current = requestAnimationFrame(measureLevel);
      };
      measureLevel();

      setDevices((d) => ({ ...d, mic: "ready", micLabel: label }));

      console.log("[PREP_MIC_READY] Microphone permission granted:", label);
    } catch (err: any) {
      const isDenied = err.name === "NotAllowedError" || err.name === "PermissionDeniedError";
      setDevices((d) => ({ ...d, mic: isDenied ? "denied" : "error", micLevel: 0 }));
      console.warn("[PREP_MIC_FAILED]", err.name, err.message);
    }
  }, []);

  const checkCamera = useCallback(async () => {
    setDevices((d) => ({ ...d, camera: "checking" }));
    if (videoStreamRef.current) {
      videoStreamRef.current.getTracks().forEach((t) => t.stop());
      videoStreamRef.current = null;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" }, audio: false });
      videoStreamRef.current = stream;
      const label = stream.getVideoTracks()[0]?.label || "Camera";
      if (videoRef.current) videoRef.current.srcObject = stream;
      setDevices((d) => ({ ...d, camera: "ready", cameraLabel: label }));
      console.log("[PREP_CAMERA_READY]", label);
    } catch (err: any) {
      const isDenied = err.name === "NotAllowedError" || err.name === "PermissionDeniedError";
      setDevices((d) => ({ ...d, camera: isDenied ? "denied" : "error" }));
      console.warn("[PREP_CAMERA_FAILED]", err.name);
    }
  }, []);

  const checkSpeaker = useCallback(async () => {
    setDevices((d) => ({ ...d, speaker: "checking" }));
    // Speaker check: creating an AudioContext is enough to verify that the
    // browser exposes an output device. A context may remain suspended until
    // the Enter button gesture, so never await resume/close here.
    try {
      const ctx = new AudioContext();
      const state = ctx.state;
      void ctx.close().catch(() => undefined);
      setDevices((d) => ({ ...d, speaker: "ready" }));
      console.log(`[PREP_SPEAKER_READY] Audio context state=${state}`);
    } catch (err) {
      setDevices((d) => ({ ...d, speaker: "error" }));
      console.warn("[PREP_SPEAKER_FAILED]", err);
    }
  }, []);

  // Auto-run all checks on mount
  useEffect(() => {
    const run = async () => {
      await checkMicrophone();
      await checkCamera();
      await checkSpeaker();
    };
    run();
    return () => {
      // Cleanup streams
      if (micStreamRef.current) micStreamRef.current.getTracks().forEach((t) => t.stop());
      if (videoStreamRef.current) videoStreamRef.current.getTracks().forEach((t) => t.stop());
      if (micLevelRafRef.current) cancelAnimationFrame(micLevelRafRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Enter interview ─────────────────────────────────────────────────────────
  const handleEnterInterview = useCallback(async () => {
    if (isEntering) return;
    setIsEntering(true);
    setEnterError(null);

    // Stop preview streams to free device for Agora
    if (micStreamRef.current) { micStreamRef.current.getTracks().forEach((t) => t.stop()); micStreamRef.current = null; }
    if (videoStreamRef.current) { videoStreamRef.current.getTracks().forEach((t) => t.stop()); videoStreamRef.current = null; }
    if (micLevelRafRef.current) { cancelAnimationFrame(micLevelRafRef.current); micLevelRafRef.current = null; }

    try {
      const res = await standardInterviewFetch(`${apiUrl}/api/v1/sessions/${token}/start`, { method: "POST" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Failed to start session (${res.status})`);
      }
      const startData = await res.json();
      console.log("[SESSION_START_SUCCESS] channel:", startData.channel_name, "agents:", startData.agent_ids);

      // Navigate to room page, passing session credentials via sessionStorage
      sessionStorage.setItem(`session_${token}`, JSON.stringify(startData));
      window.location.href = `/interview/${token}`;
    } catch (err: any) {
      setEnterError(err.message || "Failed to start interview session.");
      setIsEntering(false);
    }
  }, [token, apiUrl, router, isEntering]);

  // ── Computed states ─────────────────────────────────────────────────────────
  const micReady = devices.mic === "ready";
  const cameraReady = devices.camera === "ready";
  const speakerReady = devices.speaker === "ready";
  const allDevicesReady = micReady && speakerReady; // camera optional
  const sessionOpen = sessionInfo ? isSessionOpen(sessionInfo.scheduled_start, 10) : false;
  const canEnter = allDevicesReady && sessionOpen && !isEntering;

  const scheduledTime = sessionInfo ? formatScheduledTime(sessionInfo.scheduled_start) : null;

  // ── Render ─────────────────────────────────────────────────────────────────
  if (sessionLoading) {
    return (
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-white/60">
          <Loader2 className="h-8 w-8 animate-spin text-brand" />
          <p className="text-sm">Loading interview details…</p>
        </div>
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="fixed inset-0 bg-gray-950 flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-gray-900 border border-red-500/30 rounded-2xl p-8 text-center">
          <XCircle className="h-12 w-12 text-red-400 mx-auto mb-4" />
          <h1 className="text-xl font-bold text-white mb-2">Interview Not Found</h1>
          <p className="text-sm text-white/60 mb-6">{sessionError}</p>
          <p className="text-xs text-white/40">Token: {token}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-gray-950 overflow-y-auto">
      <div className="min-h-full flex items-start justify-center p-4 py-8">
        <div className="w-full max-w-2xl space-y-4">

          {/* ── Header ────────────────────────────────────────── */}
          <div className="flex items-center gap-3 mb-2">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-brand to-blue-600 flex items-center justify-center shadow-md shadow-brand/20">
              <Radio className="h-4 w-4 text-white" />
            </div>
            <div>
              <span className="text-sm font-bold text-white">Intra AI Interview</span>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-[11px] text-white/50">Pre-interview setup</span>
              </div>
            </div>
          </div>

          {/* ── Interview Info ────────────────────────────────── */}
          <div className="bg-gray-900/80 border border-white/10 rounded-2xl p-6 backdrop-blur-md">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div>
                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-brand/10 border border-brand/20 text-brand text-xs font-semibold mb-3">
                  <Sparkles className="h-3 w-3" />
                  AI Interview
                </div>
                <h1 className="text-xl font-bold text-white">
                  {sessionInfo?.job_title || "Interview Session"}
                </h1>
                {sessionInfo?.company && (
                  <p className="text-sm text-white/60 mt-0.5">{sessionInfo.company}</p>
                )}
              </div>
              <div className="flex flex-col items-end gap-1.5 shrink-0 text-right">
                {scheduledTime ? (
                  <>
                    <div className="flex items-center gap-1.5 text-xs text-white/60">
                      <Calendar className="h-3.5 w-3.5" />
                      <span>{scheduledTime.date}</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-xs text-white/60">
                      <Clock className="h-3.5 w-3.5" />
                      <span>{scheduledTime.time}</span>
                    </div>
                  </>
                ) : (
                  <span className="text-xs text-emerald-400 font-medium">On-demand session</span>
                )}
                {sessionInfo?.duration_minutes && (
                  <span className="text-xs text-white/40">{sessionInfo.duration_minutes} min</span>
                )}
              </div>
            </div>

            {/* Interviewers */}
            {sessionInfo?.selected_agents && sessionInfo.selected_agents.length > 0 && (
              <div className="mt-4 pt-4 border-t border-white/8">
                <p className="text-xs text-white/40 mb-2 flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  {sessionInfo.selected_agents.length === 1 ? "Interviewer" : "Interviewers"}
                </p>
                <div className="flex flex-col gap-2">
                  {sessionInfo.selected_agents.map((agent) => (
                    <div key={agent.agent_id} className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-gradient-to-br from-brand/40 to-blue-600/40 border border-brand/30 flex items-center justify-center shrink-0">
                        <span className="text-xs font-bold text-brand">{agent.name[0]}</span>
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-white">{agent.name}</p>
                        <p className="text-xs text-white/50">{agent.role}</p>
                      </div>
                      {agent.agent_id === sessionInfo.current_agent_id && (
                        <span className="ml-auto text-[10px] bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded-full font-medium">First</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* ── Not-yet-open banner ───────────────────────────── */}
          {scheduledTime && countdown && (
            <div className="bg-amber-500/10 border border-amber-500/25 rounded-xl px-4 py-3 flex items-center gap-3">
              <Clock className="h-4 w-4 text-amber-400 shrink-0" />
              <div>
                <p className="text-sm font-medium text-amber-300">Interview hasn&apos;t started yet</p>
                <p className="text-xs text-amber-400/70 mt-0.5">Opens in {countdown}</p>
              </div>
            </div>
          )}

          {/* ── Camera Preview ────────────────────────────────── */}
          <div className="bg-gray-900/80 border border-white/10 rounded-2xl overflow-hidden">
            <div className="relative h-52 bg-gray-950 flex items-center justify-center">
              {devices.camera === "ready" ? (
                <video
                  ref={videoRef}
                  autoPlay
                  playsInline
                  muted
                  className="w-full h-full object-cover scale-x-[-1]"
                />
              ) : devices.camera === "denied" ? (
                <div className="flex flex-col items-center gap-2 text-white/30">
                  <CameraOff className="h-8 w-8" />
                  <span className="text-xs">Camera permission denied</span>
                </div>
              ) : devices.camera === "checking" ? (
                <div className="flex flex-col items-center gap-2 text-white/40">
                  <Loader2 className="h-7 w-7 animate-spin text-brand/60" />
                  <span className="text-xs">Requesting camera…</span>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 text-white/20">
                  <Camera className="h-8 w-8" />
                  <span className="text-xs">Camera preview</span>
                </div>
              )}
              {/* Camera status overlay */}
              <div className="absolute bottom-3 left-3">
                <DevicePill
                  ready={devices.camera === "ready"}
                  denied={devices.camera === "denied"}
                  checking={devices.camera === "checking"}
                  label="Camera"
                />
              </div>
            </div>
          </div>

          {/* ── Device Checks ─────────────────────────────────── */}
          <div className="bg-gray-900/80 border border-white/10 rounded-2xl p-5 space-y-4">
            <h2 className="text-sm font-semibold text-white/80">Device Check</h2>

            {/* Microphone */}
            <div className="flex items-center gap-4">
              <DeviceIcon state={devices.mic} icon={devices.mic === "ready" ? Mic : MicOff} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-white">Microphone</span>
                  <DeviceStatusChip state={devices.mic} />
                </div>
                {devices.mic === "ready" && (
                  <div className="flex items-end gap-0.5 h-5">
                    {Array.from({ length: 28 }).map((_, i) => {
                      const threshold = (i / 28) * 100;
                      const active = devices.micLevel > threshold;
                      return (
                        <div
                          key={i}
                          className={cn(
                            "flex-1 rounded-sm transition-all duration-75",
                            active ? (i > 21 ? "bg-red-500" : i > 14 ? "bg-amber-400" : "bg-emerald-400") : "bg-white/10"
                          )}
                          style={{ height: `${Math.min(100, 25 + (i / 28) * 75)}%` }}
                        />
                      );
                    })}
                  </div>
                )}
                {devices.mic === "denied" && (
                  <p className="text-xs text-red-400 mt-0.5">Allow microphone in browser settings, then <button onClick={checkMicrophone} className="underline">retry</button></p>
                )}
                {devices.mic === "error" && (
                  <button onClick={checkMicrophone} className="text-xs text-white/50 hover:text-white flex items-center gap-1 mt-0.5">
                    <RefreshCw className="h-3 w-3" /> Retry
                  </button>
                )}
              </div>
            </div>

            <div className="h-px bg-white/5" />

            {/* Camera */}
            <div className="flex items-center gap-4">
              <DeviceIcon state={devices.camera} icon={devices.camera === "ready" ? Camera : CameraOff} />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-white">Camera</span>
                  <DeviceStatusChip state={devices.camera} />
                </div>
                {devices.camera === "ready" && devices.cameraLabel && (
                  <p className="text-xs text-white/40 mt-0.5 truncate">{devices.cameraLabel}</p>
                )}
                {devices.camera === "denied" && (
                  <button onClick={checkCamera} className="text-xs text-white/50 hover:text-white flex items-center gap-1 mt-0.5">
                    <RefreshCw className="h-3 w-3" /> Retry
                  </button>
                )}
              </div>
            </div>

            <div className="h-px bg-white/5" />

            {/* Speaker */}
            <div className="flex items-center gap-4">
              <DeviceIcon state={devices.speaker} icon={Volume2} />
              <div className="flex-1">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-white">Speaker / Audio</span>
                  <DeviceStatusChip state={devices.speaker} />
                </div>
                {devices.speaker !== "ready" && devices.speaker !== "checking" && (
                  <button onClick={checkSpeaker} className="text-xs text-white/50 hover:text-white flex items-center gap-1 mt-0.5">
                    <RefreshCw className="h-3 w-3" /> Retry
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* ── Checklist ─────────────────────────────────────── */}
          <div className="bg-white/3 border border-white/8 rounded-xl px-4 py-3 text-xs space-y-1.5">
            <ChecklistItem ok={micReady} label="Microphone ready — AI interviewer can hear you" />
            <ChecklistItem ok={cameraReady} label="Camera ready — You'll be visible during the interview" optional />
            <ChecklistItem ok={speakerReady} label="Audio unlocked — You'll hear the AI interviewer" />
            <ChecklistItem ok={true} label="Groq M1 Intelligence active (~1.3s analysis)" />
          </div>

          {/* ── Enter error ───────────────────────────────────── */}
          {enterError && (
            <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-xl px-4 py-3">
              <AlertCircle className="h-4 w-4 text-red-400 shrink-0 mt-0.5" />
              <p className="text-xs text-red-300">{enterError}</p>
            </div>
          )}

          {/* ── Enter button ──────────────────────────────────── */}
          <button
            id="btn-enter-interview"
            onClick={handleEnterInterview}
            disabled={!canEnter}
            className={cn(
              "w-full py-4 px-6 rounded-xl font-semibold text-base flex items-center justify-center gap-2.5 transition-all duration-200",
              canEnter
                ? "bg-gradient-to-r from-brand to-blue-600 hover:from-brand/90 hover:to-blue-500 text-white shadow-lg shadow-brand/25 hover:shadow-brand/40 hover:scale-[1.01] active:scale-[0.99] cursor-pointer"
                : "bg-white/5 text-white/30 border border-white/10 cursor-not-allowed"
            )}
          >
            {isEntering ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                <span>Starting session…</span>
              </>
            ) : !sessionOpen && countdown ? (
              <>
                <Clock className="h-5 w-5" />
                <span>Opens in {countdown}</span>
              </>
            ) : !allDevicesReady ? (
              <>
                <ShieldCheck className="h-5 w-5" />
                <span>Complete device checks to continue</span>
              </>
            ) : (
              <>
                <Radio className="h-5 w-5" />
                <span>Enter Interview</span>
                <ChevronRight className="h-5 w-5" />
              </>
            )}
          </button>

          <p className="text-center text-xs text-white/30 pb-4">
            Microphone and speaker must be ready before entering
          </p>
        </div>
      </div>
    </div>
  );
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function DeviceIcon({ state, icon: Icon }: { state: DeviceState; icon: any }) {
  return (
    <div className={cn(
      "h-10 w-10 rounded-full flex items-center justify-center shrink-0 transition-colors",
      state === "ready" ? "bg-emerald-500/15" :
      state === "denied" || state === "error" ? "bg-red-500/15" :
      state === "checking" ? "bg-brand/15" :
      "bg-white/5"
    )}>
      <Icon className={cn(
        "h-4.5 w-4.5",
        state === "ready" ? "text-emerald-400" :
        state === "denied" || state === "error" ? "text-red-400" :
        state === "checking" ? "text-brand" :
        "text-white/30"
      )} />
    </div>
  );
}

function DeviceStatusChip({ state }: { state: DeviceState }) {
  if (state === "idle") return <span className="text-xs text-white/30">—</span>;
  if (state === "checking") return (
    <span className="inline-flex items-center gap-1 text-xs text-brand bg-brand/10 px-2 py-0.5 rounded-full">
      <Loader2 className="h-3 w-3 animate-spin" /> Checking
    </span>
  );
  if (state === "ready") return (
    <span className="inline-flex items-center gap-1 text-xs text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full">
      <CheckCircle2 className="h-3 w-3" /> Ready
    </span>
  );
  if (state === "denied") return (
    <span className="inline-flex items-center gap-1 text-xs text-red-400 bg-red-500/10 px-2 py-0.5 rounded-full">
      <XCircle className="h-3 w-3" /> Denied
    </span>
  );
  return (
    <span className="inline-flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded-full">
      <AlertCircle className="h-3 w-3" /> Error
    </span>
  );
}

function DevicePill({ ready, denied, checking, label }: { ready: boolean; denied: boolean; checking: boolean; label: string }) {
  const bg = ready ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" :
             denied ? "bg-red-500/20 text-red-300 border-red-500/30" :
             checking ? "bg-brand/20 text-brand border-brand/30" :
             "bg-black/50 text-white/40 border-white/10";
  return (
    <span className={cn("text-[10px] font-medium px-2 py-0.5 rounded-full border backdrop-blur-sm", bg)}>
      {ready ? "✓ " : ""}{label}
    </span>
  );
}

function ChecklistItem({ ok, label, optional }: { ok: boolean; label: string; optional?: boolean }) {
  return (
    <div className="flex items-center gap-2">
      {ok
        ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />
        : optional
          ? <div className="h-3.5 w-3.5 rounded-full border border-white/20 shrink-0" />
          : <div className="h-3.5 w-3.5 rounded-full border border-red-500/40 shrink-0" />
      }
      <span className={cn("truncate", ok ? "text-white/70" : optional ? "text-white/30" : "text-white/40")}>
        {label}{optional ? " (optional)" : ""}
      </span>
    </div>
  );
}
