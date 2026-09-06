"use client";

import { Star } from "lucide-react";
import type { BackendCandidatePerformanceResponse } from "@/types/api";
import { candidatePerformanceSummary, starFillPercentages } from "@/lib/report-presentation";

export function CandidatePerformance({ performance }: { performance: BackendCandidatePerformanceResponse }) {
  const summary = candidatePerformanceSummary(performance);
  if (!summary) return null;
  return (
    <section className="rounded-xl border border-border bg-surface p-6 shadow-sm" aria-labelledby="candidate-performance-title">
      <h2 id="candidate-performance-title" className="text-xl font-semibold text-text-primary">Your Interview Performance</h2>
      <div className="mt-4 flex items-center gap-3">
        <div className="flex gap-1" role="img" aria-label={`${summary.rating.toFixed(1)} out of 5 stars`}>
          {starFillPercentages(summary.rating).map((fill, index) => (
            <span key={index} className="relative block h-6 w-6" aria-hidden="true">
              <Star className="h-6 w-6 text-border" />
              <span className="absolute inset-y-0 left-0 overflow-hidden" style={{ width: `${fill}%` }}>
                <Star className="h-6 w-6 fill-brand text-brand" />
              </span>
            </span>
          ))}
        </div>
        <span className="text-lg font-semibold tabular-nums text-text-primary" aria-hidden="true">{summary.rating.toFixed(1)}/5</span>
      </div>
      <div className="mt-5 space-y-2 text-sm leading-relaxed text-text-primary">
        {summary.feedback.map((line, index) => <p key={index}>{line}</p>)}
      </div>
    </section>
  );
}
