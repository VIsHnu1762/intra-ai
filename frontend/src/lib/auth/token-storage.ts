/**
 * Intra AI — Auth Token Persistence & Session Lifecycle Manager
 *
 * Persists JWT tokens in browser cookies (for Edge middleware accessibility)
 * and localStorage (for cross-tab synchronization).
 */

import type { UserRole } from "@/types";

export const AUTH_COOKIE_NAME = "intra_auth_token";
export const ROLE_COOKIE_NAME = "intra_user_role";
export const AUTH_STORAGE_KEY = "intra_ai_auth_token";
export const AUTH_USER_KEY = "intra_ai_auth_user";

export interface DecodedJwtPayload {
  sub: string;
  role: UserRole;
  exp: number;
  iat?: number;
  [key: string]: unknown;
}

/**
 * Parses client cookies safely in browser environments.
 */
function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Sets a client cookie with standard security attributes.
 */
function setCookie(name: string, value: string, maxAgeSeconds: number = 3600): void {
  if (typeof document === "undefined") return;
  const isSecure = typeof window !== "undefined" && window.location.protocol === "https:";
  const secureAttr = isSecure ? "; Secure" : "";
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax${secureAttr}`;
}

/**
 * Removes a client cookie.
 */
function removeCookie(name: string): void {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`;
}

/**
 * Safely decodes base64url strings in modern browser/runtimes.
 */
function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, "+").replace(/_/g, "/");
  while (base64.length % 4) {
    base64 += "=";
  }
  if (typeof atob === "function") {
    return decodeURIComponent(
      Array.prototype.map
        .call(atob(base64), (c: string) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join("")
    );
  }
  return Buffer.from(base64, "base64").toString("utf-8");
}

/**
 * Decodes the JWT payload without verifying signature (verification is done by backend).
 */
export function decodeAuthToken(tokenString?: string): DecodedJwtPayload | null {
  const token = tokenString || getAuthToken();
  if (!token || typeof token !== "string") return null;

  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const jsonStr = base64UrlDecode(parts[1]);
    return JSON.parse(jsonStr) as DecodedJwtPayload;
  } catch {
    return null;
  }
}

/**
 * Checks whether the stored or provided JWT token has passed its expiration timestamp.
 */
export function isTokenExpired(tokenString?: string): boolean {
  const payload = decodeAuthToken(tokenString);
  if (!payload || !payload.exp) return true;
  // Exp is in seconds; subtract a 30s buffer for network clock skew
  const nowInSeconds = Math.floor(Date.now() / 1000);
  return payload.exp <= nowInSeconds + 30;
}

/**
 * Returns remaining milliseconds until token expiration (or 0 if expired).
 */
export function getTokenRemainingMs(tokenString?: string): number {
  const payload = decodeAuthToken(tokenString);
  if (!payload || !payload.exp) return 0;
  const diffMs = payload.exp * 1000 - Date.now();
  return Math.max(0, diffMs);
}

/**
 * Retrieves the stored JWT authentication token.
 * Checks cookie first (SSR/Middleware sync), then localStorage.
 */
export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null;

  const cookieToken = getCookie(AUTH_COOKIE_NAME);
  if (cookieToken) return cookieToken;

  try {
    return localStorage.getItem(AUTH_STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Persists JWT authentication token and associated user role in cookies and localStorage.
 */
export function setAuthToken(token: string, role?: UserRole): void {
  if (typeof window === "undefined") return;

  const payload = decodeAuthToken(token);
  const resolvedRole = role || payload?.role;
  const maxAge = payload?.exp
    ? Math.max(60, payload.exp - Math.floor(Date.now() / 1000))
    : 3600;

  // Persist to cookie (accessible to Next.js middleware)
  setCookie(AUTH_COOKIE_NAME, token, maxAge);
  if (resolvedRole) {
    setCookie(ROLE_COOKIE_NAME, resolvedRole, maxAge);
  }

  // Persist to localStorage for cross-tab sync
  try {
    localStorage.setItem(AUTH_STORAGE_KEY, token);
    if (resolvedRole) {
      localStorage.setItem(ROLE_COOKIE_NAME, resolvedRole);
    }
  } catch {
    // localStorage might be unavailable in private browsing
  }
}

/**
 * Clears authentication token and role from cookies and localStorage.
 */
export function clearAuthToken(): void {
  if (typeof window === "undefined") return;

  removeCookie(AUTH_COOKIE_NAME);
  removeCookie(ROLE_COOKIE_NAME);

  try {
    localStorage.removeItem(AUTH_STORAGE_KEY);
    localStorage.removeItem(ROLE_COOKIE_NAME);
    localStorage.removeItem(AUTH_USER_KEY);
  } catch {
    // Ignore
  }
}

/**
 * Retrieves the user role from token claims or cookie.
 */
export function getUserRole(): UserRole | null {
  if (typeof window === "undefined") return null;

  const payload = decodeAuthToken();
  if (payload?.role) return payload.role;

  const cookieRole = getCookie(ROLE_COOKIE_NAME);
  if (cookieRole === "admin" || cookieRole === "recruiter" || cookieRole === "candidate") {
    return cookieRole;
  }

  try {
    const localRole = localStorage.getItem(ROLE_COOKIE_NAME);
    if (localRole === "admin" || localRole === "recruiter" || localRole === "candidate") {
      return localRole;
    }
  } catch {
    // Ignore
  }

  return null;
}
