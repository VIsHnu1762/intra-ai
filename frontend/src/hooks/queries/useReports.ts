/** Read-only report queries and explicit generation, with candidate data isolated. */
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getReport, getReports, getReportStatus, getCandidatePerformance, generateReport, type ReportListParams } from "@/lib/api/reports";
import { reportPollInterval } from "@/lib/report-presentation";
import type { BackendReportResponse, BackendReportListResponse, BackendReportStatusResponse, BackendCandidatePerformanceResponse } from "@/types/api";

export const REPORT_QUERY_KEYS = {
  all: ["reports"] as const,
  list: (params?: ReportListParams) => [...REPORT_QUERY_KEYS.all, "list", params] as const,
  byInterview: (interviewId: string) => [...REPORT_QUERY_KEYS.all, interviewId] as const,
  status: (id: string) => [...REPORT_QUERY_KEYS.all, "status", id] as const,
  performance: (id: string) => ["candidate-performance", id] as const,
};

export function useReports(params?: ReportListParams, options?: { enabled?: boolean }) {
  return useQuery<BackendReportListResponse, Error>({
    queryKey: REPORT_QUERY_KEYS.list(params), queryFn: () => getReports(params),
    enabled: options?.enabled ?? true,
  });
}

export function useReport(interviewId: string, options?: { enabled?: boolean; refetchInterval?: number | false }) {
  return useQuery<BackendReportResponse, Error>({
    queryKey: REPORT_QUERY_KEYS.byInterview(interviewId), queryFn: () => getReport(interviewId),
    enabled: Boolean(interviewId) && (options?.enabled ?? true), refetchInterval: options?.refetchInterval,
  });
}

export function useReportStatus(id: string) {
  return useQuery<BackendReportStatusResponse, Error>({
    queryKey: REPORT_QUERY_KEYS.status(id), queryFn: () => getReportStatus(id), enabled: Boolean(id),
    retry: false,
    refetchInterval: query => reportPollInterval(query.state.data?.status, query.state.status === "error"),
  });
}

export function useCandidatePerformance(id: string) {
  return useQuery<BackendCandidatePerformanceResponse, Error>({
    queryKey: REPORT_QUERY_KEYS.performance(id), queryFn: () => getCandidatePerformance(id), enabled: Boolean(id),
    retry: false,
    refetchInterval: query => reportPollInterval(query.state.data?.status, query.state.status === "error"),
  });
}

export function useGenerateReport() {
  const queryClient = useQueryClient();
  return useMutation<BackendReportStatusResponse, Error, string>({
    mutationFn: generateReport,
    onSuccess: (data, interviewId) => {
      queryClient.setQueryData(REPORT_QUERY_KEYS.status(interviewId), data);
      queryClient.invalidateQueries({ queryKey: REPORT_QUERY_KEYS.all });
      queryClient.invalidateQueries({ queryKey: REPORT_QUERY_KEYS.performance(interviewId) });
    },
  });
}
