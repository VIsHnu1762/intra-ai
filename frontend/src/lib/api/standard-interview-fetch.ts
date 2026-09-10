import { getAuthToken } from "@/lib/auth/token-storage";

// Preserve the existing streaming/raw Response handling in the interview UI.
// Authentication reuses the application's token store, not a second client.
export function standardInterviewFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const backend = new URL(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
  const target = new URL(url);
  if (target.origin !== backend.origin || !target.pathname.startsWith("/api/v1/")) {
    throw new Error("Interview credentials may only be sent to the configured API");
  }
  const headers = new Headers(options.headers);
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(url, { ...options, headers });
}
