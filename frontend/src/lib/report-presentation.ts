import type { BackendCandidatePerformanceResponse, ReportGenerationState } from "../types/api";

/** Read-only polling is needed only while the server is generating a report. */
export function reportPollInterval(status?: ReportGenerationState, failedRequest = false): number | false {
  return !failedRequest && status === "generating" ? 3000 : false;
}

export function candidatePerformanceSummary(data?: BackendCandidatePerformanceResponse | null) {
  if (data?.status !== "ready" || typeof data.rating !== "number" || !Number.isFinite(data.rating)
      || data.rating < 1 || data.rating > 5 || !Array.isArray(data.feedback)
      || data.feedback.length !== 3 || data.feedback.some(line => typeof line !== "string" || !line.trim())) return null;
  // Explicit projection keeps any unexpected recruiter fields out of this surface.
  return { rating: data.rating, feedback: data.feedback.map(line => line.trim()) };
}

export function starFillPercentages(rating: number): number[] {
  if (!Number.isFinite(rating) || rating < 1 || rating > 5) return [];
  return Array.from({ length: 5 }, (_, index) => Math.round(Math.max(0, Math.min(1, rating - index)) * 100));
}

export function safeReportPdfUrl(value?: string | null): string | null {
  if (!value?.trim()) return null;
  const url = value.trim();
  if (url.startsWith("/") && !url.startsWith("//") && !url.includes("\\")) return url;
  try {
    const parsed = new URL(url);
    return ["http:", "https:"].includes(parsed.protocol) && !parsed.username && !parsed.password ? url : null;
  } catch { return null; }
}

export function performanceStatusMessage(status?: ReportGenerationState): string {
  switch (status) {
    case "not_completed": return "Your interview has not been marked complete yet.";
    case "not_started": return "Your feedback is not available yet. You can check again later.";
    case "generating": return "Your interview performance feedback is being prepared.";
    case "failed": return "Your feedback could not be prepared. The hiring team can review this and retry.";
    default: return "Your interview performance feedback is currently unavailable.";
  }
}

export function reportLabel(value?: string | null, fallback = "Not recorded"): string {
  if (!value?.trim() || value === "unknown" || /^[a-f0-9-]{32,}$/i.test(value)) return fallback;
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, letter => letter.toUpperCase());
}

export function reportGenerationAction(status?: ReportGenerationState, retryable = false): string | null {
  if (status === "not_started") return "Generate Report";
  if (status === "failed" && retryable) return "Retry Generation";
  return null;
}
