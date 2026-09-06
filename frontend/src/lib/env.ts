/**
 * Intra AI — Environment Configuration & Validation
 *
 * Validates and provides typed access to public environment variables.
 * Fallbacks are provided for local development convenience.
 */

export interface EnvConfig {
  apiUrl: string;
  agoraAppId: string;
  appEnv: "development" | "staging" | "production";
  isProd: boolean;
  isDev: boolean;
  wsUrl?: string;
}

function normalizeUrl(url: string | undefined, defaultVal: string): string {
  if (!url || typeof url !== "string" || url.trim() === "") {
    return defaultVal;
  }
  return url.trim().replace(/\/+$/, "");
}

function resolveAppEnv(env: string | undefined): "development" | "staging" | "production" {
  if (env === "production" || env === "prod") return "production";
  if (env === "staging") return "staging";
  return "development";
}

const rawApiUrl = process.env.NEXT_PUBLIC_API_URL;
const rawAgoraAppId = process.env.NEXT_PUBLIC_AGORA_APP_ID;
const rawAppEnv = process.env.NEXT_PUBLIC_APP_ENV;
const rawWsUrl = process.env.NEXT_PUBLIC_WS_URL;

export const env: EnvConfig = {
  apiUrl: normalizeUrl(rawApiUrl, "http://localhost:8000"),
  agoraAppId: (rawAgoraAppId || "").trim(),
  appEnv: resolveAppEnv(rawAppEnv),
  isProd: resolveAppEnv(rawAppEnv) === "production",
  isDev: resolveAppEnv(rawAppEnv) === "development",
  wsUrl: rawWsUrl ? normalizeUrl(rawWsUrl, "ws://localhost:8000/ws") : undefined,
};

// Defensive check in production browser console
if (typeof window !== "undefined" && env.isProd) {
  if (!env.agoraAppId) {
    console.warn("[Intra AI] NEXT_PUBLIC_AGORA_APP_ID is not configured. Voice sessions may fail to connect.");
  }
}
