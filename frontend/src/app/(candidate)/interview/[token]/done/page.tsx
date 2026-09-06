"use client";

import { use } from "react";
import Link from "next/link";
import { CheckCircle2, ArrowLeft, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { CandidatePerformance } from "@/components/reports/candidate-performance";
import { useCandidatePerformance } from "@/hooks/queries/useReports";
import { candidatePerformanceSummary, performanceStatusMessage } from "@/lib/report-presentation";

export default function InterviewDonePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = use(params);
  const { data, isLoading, isFetching, error, refetch } = useCandidatePerformance(token);
  const completed = data && data.status !== "not_completed";
  const ready = !error && candidatePerformanceSummary(data);
  return (
    <div className="mx-auto max-w-2xl space-y-6 py-8">
      <div className="text-center">
        {completed && <CheckCircle2 className="mx-auto mb-4 h-14 w-14 text-success" />}
        <h1 className="text-3xl font-bold text-text-primary">{completed ? "Interview Complete" : "Interview Session"}</h1>
        <p className="mt-3 text-text-muted">{completed ? "Thank you for taking the time to interview with us." : "Checking your interview status."}</p>
      </div>
      {ready && data ? <CandidatePerformance performance={data} /> : (
        <Card>
          <CardContent className="p-6" aria-live="polite">
            <h2 className="text-base font-semibold text-text-primary">Interview Feedback</h2>
            <p className="mt-2 text-sm text-text-muted">
              {isLoading ? "Checking for your saved feedback…" : error ? "We couldn’t load your interview status. Please check again." : performanceStatusMessage(data?.status)}
            </p>
            {!isLoading && (error || data?.status !== "generating") && (
              <Button variant="secondary" size="sm" className="mt-4" loading={isFetching} onClick={() => void refetch()}>
                <RefreshCw className="h-4 w-4" /> Check Again
              </Button>
            )}
          </CardContent>
        </Card>
      )}
      <div className="text-center">
        <Link href="/portal" className="inline-flex items-center gap-1.5 text-sm text-brand hover:text-brand-hover">
          <ArrowLeft className="h-4 w-4" /> Return to Portal
        </Link>
      </div>
    </div>
  );
}
