/**
 * Intra AI — TanStack Query Client Configuration
 *
 * Configures caching, retry backoff, and refetch behaviors tailored
 * for high-performance ATS operations and low-overhead voice sessions.
 */

import { QueryClient } from "@tanstack/react-query";

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Data considered fresh for 5 minutes
        staleTime: 5 * 60 * 1000,
        // Inactive cache garbage collected after 10 minutes
        gcTime: 10 * 60 * 1000,
        // Single retry on network failure
        retry: 1,
        // Disable window focus refetching to protect active audio/RTC sessions
        refetchOnWindowFocus: false,
        refetchOnReconnect: "always",
      },
      mutations: {
        retry: 0,
      },
    },
  });
}

let browserQueryClient: QueryClient | undefined = undefined;

export function getQueryClient(): QueryClient {
  if (typeof window === "undefined") {
    // Server: always create a new query client
    return makeQueryClient();
  }
  // Browser: maintain a persistent singleton client
  if (!browserQueryClient) {
    browserQueryClient = makeQueryClient();
  }
  return browserQueryClient;
}
