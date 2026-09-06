"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CandidatePerformance } from "@/components/reports/candidate-performance";
import { useCandidatePerformance } from "@/hooks/queries/useReports";
import { candidatePerformanceSummary, performanceStatusMessage } from "@/lib/report-presentation";

export default function CandidateReportPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { data, isLoading, isFetching, error, refetch } = useCandidatePerformance(token);
  const ready = !error && candidatePerformanceSummary(data);
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Link href="/portal" className="inline-flex items-center gap-1.5 text-sm text-text-muted hover:text-text-primary">
        <ArrowLeft className="h-4 w-4" /> Back to Portal
      </Link>
      {ready && data ? <CandidatePerformance performance={data} /> : (
        <section className="rounded-xl border border-border bg-surface p-6" aria-live="polite">
          <h1 className="text-xl font-semibold text-text-primary">Your Interview Performance</h1>
          <p className="mt-3 text-sm text-text-muted">
            {isLoading ? "Loading your feedback…" : error ? "We couldn’t load your feedback. Please check your connection and try again." : performanceStatusMessage(data?.status)}
          </p>
          {!isLoading && (error || data?.status !== "generating") && (
            <Button variant="secondary" size="sm" className="mt-4" loading={isFetching} onClick={() => void refetch()}>
              <RefreshCw className="h-4 w-4" /> Check Again
            </Button>
          )}
        </section>
      )}
    </div>
  );
}
