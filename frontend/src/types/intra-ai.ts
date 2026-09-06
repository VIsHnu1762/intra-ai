/**
 * Intra AI — Frontend & M2 Domain Types
 * Defines the contracts for Multi-Agent AI Personas, Adaptive Voice Turns,
 * Live Transcript Streaming, Evidence Signals, and WebRTC Session State.
 */

export type AgentId = "alex" | "jordan";

export type InterviewTurnState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "handoff"
  | "completed";

export type AdaptiveDifficulty = "easy" | "medium" | "hard" | "expert";

export type AdaptiveActionType =
  | "ask_question"
  | "follow_up"
  | "switch_agent"
  | "increase_difficulty"
  | "decrease_difficulty"
  | "complete";

export interface AgentStyling {
  primaryColor: string;
  glowColor: string;
  surfaceColor: string;
  borderColor: string;
  badgeBg: string;
  voiceName: string;
}

export interface AgentProfile {
  id: AgentId;
  displayName: string;
  role: string;
  department: string;
  focalCompetencies: string[];
  styling: AgentStyling;
}

export interface LiveTranscriptChunk {
  id: string;
  speaker: AgentId | "candidate";
  text: string;
  timestamp: string;
  isFinal: boolean;
  isInterrupted?: boolean;
}

export interface EvidenceSignalItem {
  id: string;
  competency: string;
  signal: string;
  score: number;
  sourceAgentId: AgentId;
  roundId?: string;
  metadata?: Record<string, unknown>;
  isContradiction?: boolean;
}

export type WebRTCConnectionStatus =
  | "idle"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "failed"
  | "disconnected";

export interface DevicePermissions {
  mic: "prompt" | "granted" | "denied";
  camera: "prompt" | "granted" | "denied";
}

export interface AudioDeviceState {
  permissions: DevicePermissions;
  isMicMuted: boolean;
  isCameraOff: boolean;
  micVolumeLevel: number;
  selectedMicDeviceId?: string;
  selectedCameraDeviceId?: string;
}

export interface AgoraTokenResponse {
  app_id: string;
  channel_name: string;
  token: string;
  uid: number;
  role: number;
  expires_in: number;
}
