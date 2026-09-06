/**
 * Intra AI — Centralized API Error Handling Pipeline
 *
 * Normalizes HTTP status codes and FastAPI validation errors into
 * actionable, human-readable error descriptions.
 */

import { ApiError } from "./client";
import type { ApiErrorResponse, ApiErrorDetail } from "@/types/api";

export interface NormalizedApiError {
  status: number;
  message: string;
  fieldErrors?: Record<string, string>;
  raw?: unknown;
}

/**
 * Extracts a friendly message from a FastAPI error response.
 */
export function formatApiErrorMessage(error: unknown, fallback: string = "An unexpected error occurred."): string {
  if (!error) return fallback;

  if (error instanceof ApiError) {
    // Check if error.data is FastAPI validation error (HTTP 422)
    if (error.status === 422 && typeof error.data === "object" && error.data !== null) {
      const pydanticData = error.data as { detail?: ApiErrorDetail[] | string };
      if (Array.isArray(pydanticData.detail) && pydanticData.detail.length > 0) {
        const first = pydanticData.detail[0];
        const field = first.loc && first.loc.length > 0 ? first.loc[first.loc.length - 1] : "Field";
        return `${field}: ${first.msg}`;
      }
    }

    if (error.status === 401) {
      return "Your session has expired. Please sign in again.";
    }

    if (error.status === 403) {
      return "You do not have permission to perform this action.";
    }

    if (error.status === 404) {
      return error.message || "Requested resource was not found.";
    }

    if (error.status >= 500) {
      return "Server error occurred. Please try again shortly.";
    }

    return error.message || fallback;
  }

  if (error instanceof Error) {
    if (error.name === "AbortError") {
      return "Request was cancelled.";
    }
    return error.message || fallback;
  }

  return fallback;
}

/**
 * Normalizes any error caught from an API call into a structured object.
 */
export function normalizeApiError(error: unknown): NormalizedApiError {
  if (error instanceof ApiError) {
    const fieldErrors: Record<string, string> = {};

    if (error.status === 422 && typeof error.data === "object" && error.data !== null) {
      const pydanticData = error.data as { detail?: ApiErrorDetail[] };
      if (Array.isArray(pydanticData.detail)) {
        for (const item of pydanticData.detail) {
          if (item.loc && item.loc.length > 0) {
            const key = String(item.loc[item.loc.length - 1]);
            fieldErrors[key] = item.msg;
          }
        }
      }
    }

    return {
      status: error.status,
      message: formatApiErrorMessage(error),
      fieldErrors: Object.keys(fieldErrors).length > 0 ? fieldErrors : undefined,
      raw: error.data,
    };
  }

  return {
    status: 0,
    message: formatApiErrorMessage(error),
  };
}

export function isUnauthorizedError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function isForbiddenError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 403;
}
