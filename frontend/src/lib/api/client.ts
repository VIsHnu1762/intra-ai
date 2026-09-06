/**
 * Intra AI — Centralized Typed HTTP API Client
 *
 * Handles:
 * - Automatic Authorization: Bearer <token> injection from token-storage
 * - Automatic Content-Type & FormData resolution
 * - AbortSignal & request cancellation
 * - Global 401 Unauthorized handling & session cleanup
 * - FastAPI error parsing & structured ApiError exceptions
 */

import { getAuthToken, clearAuthToken } from "@/lib/auth/token-storage";
import { env } from "@/lib/env";

export class ApiError extends Error {
  public status: number;
  public data: unknown;

  constructor(message: string, status: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export interface RequestOptions extends Omit<RequestInit, "headers"> {
  headers?: Record<string, string>;
  params?: Record<string, string | number | boolean | undefined | null>;
  token?: string;
  skipAuth?: boolean;
  responseType?: "json" | "blob";
}

export const API_BASE_URL = env.apiUrl;

// Global listener for 401 unauthorized events (registered by AuthContext)
let unauthorizedListener: (() => void) | null = null;

export function registerUnauthorizedHandler(handler: () => void): () => void {
  unauthorizedListener = handler;
  return () => {
    if (unauthorizedListener === handler) {
      unauthorizedListener = null;
    }
  };
}

export async function apiClient<T>(
  endpoint: string,
  options: RequestOptions = {}
): Promise<T> {
  const { params, headers = {}, token, skipAuth = false, responseType = "json", ...customConfig } = options;

  let url = endpoint.startsWith("http")
    ? endpoint
    : `${API_BASE_URL}${endpoint.startsWith("/") ? "" : "/"}${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (val !== undefined && val !== null) {
        searchParams.append(key, String(val));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      url += (url.includes("?") ? "&" : "?") + queryString;
    }
  }

  const defaultHeaders: Record<string, string> = {
    Accept: "application/json",
  };

  if (!(customConfig.body instanceof FormData)) {
    defaultHeaders["Content-Type"] = "application/json";
  }

  // Inject Bearer token unless explicitly skipped
  if (!skipAuth) {
    const resolvedToken = token || getAuthToken();
    if (resolvedToken && !headers["Authorization"] && !headers["authorization"]) {
      defaultHeaders["Authorization"] = `Bearer ${resolvedToken}`;
    }
  }

  const config: RequestInit = {
    headers: {
      ...defaultHeaders,
      ...headers,
    },
    ...customConfig,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    let errData: unknown;
    try {
      errData = await response.json();
    } catch {
      errData = await response.text();
    }

    const message =
      (errData as { message?: string; detail?: string })?.message ||
      (typeof (errData as { detail?: unknown })?.detail === "string"
        ? ((errData as { detail: string }).detail)
        : null) ||
      `HTTP Error ${response.status}`;

    // Handle 401 Unauthorized globally
    if (response.status === 401) {
      // Don't loop if the 401 came from an explicit login endpoint
      const isLoginRequest = endpoint.includes("/auth/login");
      if (!isLoginRequest) {
        clearAuthToken();
        if (unauthorizedListener) {
          unauthorizedListener();
        }
      }
    }

    throw new ApiError(message, response.status, errData);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (responseType === "blob" ? response.blob() : response.json()) as Promise<T>;
}

// Convenience REST methods
apiClient.get = <T>(endpoint: string, options?: RequestOptions) =>
  apiClient<T>(endpoint, { ...options, method: "GET" });

apiClient.post = <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
  apiClient<T>(endpoint, {
    ...options,
    method: "POST",
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

apiClient.patch = <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
  apiClient<T>(endpoint, {
    ...options,
    method: "PATCH",
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

apiClient.put = <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
  apiClient<T>(endpoint, {
    ...options,
    method: "PUT",
    body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
  });

apiClient.delete = <T>(endpoint: string, options?: RequestOptions) =>
  apiClient<T>(endpoint, { ...options, method: "DELETE" });
