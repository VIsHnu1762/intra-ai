/**
 * Intra AI — Authentication API Client Endpoints
 *
 * Verifiably mapped to FastAPI routes:
 * - POST /api/v1/auth/login   (EXISTING)
 * - POST /api/v1/auth/signup  (EXISTING)
 * - POST /api/v1/auth/refresh (EXISTING)
 */

import { apiClient } from "./client";
import type {
  LoginCredentials,
  SignupPayload,
  AuthTokenResponse,
} from "@/types/api";

/**
 * Authenticate with email and password.
 * Backend: POST /api/v1/auth/login
 */
export async function loginApi(credentials: LoginCredentials): Promise<AuthTokenResponse> {
  return apiClient<AuthTokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(credentials),
    skipAuth: true,
  });
}

/**
 * Register a new user account.
 * Backend: POST /api/v1/auth/signup
 */
export async function signupApi(payload: SignupPayload): Promise<AuthTokenResponse> {
  return apiClient<AuthTokenResponse>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
    skipAuth: true,
  });
}

/**
 * Refresh current access token.
 * Backend: POST /api/v1/auth/refresh (Requires Bearer token)
 */
export async function refreshTokenApi(): Promise<AuthTokenResponse> {
  return apiClient<AuthTokenResponse>("/api/v1/auth/refresh", {
    method: "POST",
  });
}
