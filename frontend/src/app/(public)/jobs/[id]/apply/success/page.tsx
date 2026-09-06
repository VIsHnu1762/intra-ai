"use client";

import { use, Suspense } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2, ArrowRight, Briefcase, FileCheck, Calendar, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { usePublicJob } from "@/hooks/queries/useJobs";

function SuccessContent({ id }: { id: string }) {
  const searchParams = useSearchParams();
  const appId = searchParams.get("app_id");
  const titleParam = searchParams.get("title");

  const { data: job } = usePublicJob(id, { enabled: !titleParam });
  const jobTitle = titleParam || job?.title || "Open Position";

  return (
    <div className="mx-auto max-w-lg px-4 sm:px-6 lg:px-8 py-16">
      <Card>
        <CardContent className="p-8 flex flex-col items-center text-center gap-6">
          {/* Animated checkmark */}
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-brand/10 text-brand animate-[fadeIn_0.4s_ease-out]">
            <CheckCircle2 className="h-10 w-10 text-brand" strokeWidth={2} />
          </div>

          {/* Heading */}
          <div className="flex flex-col gap-2">
            <h1 className="text-2xl font-bold text-text-primary">
              Application Submitted!
            </h1>
            <p className="text-sm text-text-muted leading-relaxed">
              Thank you for applying for{" "}
              <span className="font-semibold text-text-primary">{jobTitle}</span>.
              Your application has been received and registered with Intra AI.
            </p>
          </div>

          {/* Reference ID Badge */}
          {appId && (
            <div className="flex flex-col items-center gap-1 rounded-lg border border-border/80 bg-surface/60 px-4 py-2.5 w-full">
              <span className="text-[11px] text-text-muted uppercase tracking-wider font-medium">
                Application Reference ID
              </span>
              <code className="text-xs font-mono font-semibold text-brand select-all">
                {appId}
              </code>
            </div>
          )}

          {/* Info Box: What Happens Next */}
          <div className="w-full rounded-xl border border-border bg-surface/50 p-5 text-left">
            <p className="text-sm font-semibold text-text-primary mb-3">What happens next?</p>
            <ol className="flex flex-col gap-3">
              {[
                {
                  icon: FileCheck,
                  title: "Resume Intelligence",
                  desc: "Our GPT-4o engine extracts skills, projects, and work history.",
                },
                {
                  icon: Sparkles,
                  title: "Eligibility Scoring",
                  desc: "Qualifications are evaluated against job requirements in the background.",
                },
                {
                  icon: Calendar,
                  title: "Interview Scheduling",
                  desc: "Shortlisted applicants receive an invitation to select a voice interview slot.",
                },
              ].map((step, i) => {
                const Icon = step.icon;
                return (
                  <li key={i} className="flex items-start gap-3 text-xs text-text-muted">
                    <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand font-semibold text-[11px]">
                      {i + 1}
                    </div>
                    <div className="flex-1">
                      <span className="font-medium text-text-primary block">{step.title}</span>
                      <span className="text-text-muted mt-0.5 block">{step.desc}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>

          {/* CTAs */}
          <div className="flex w-full flex-col sm:flex-row gap-3">
            <Button asChild size="lg" className="flex-1">
              <Link href="/portal" className="inline-flex items-center justify-center gap-1.5">
                Go to Candidate Portal
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg" className="flex-1">
              <Link href="/jobs">Browse Positions</Link>
            </Button>
          </div>

          {/* Note */}
          <p className="text-xs text-text-muted">
            You can monitor real-time parsing, eligibility status, and interview scheduling anytime in your Candidate Portal.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function ApplicationSuccessPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);

  return (
    <Suspense fallback={<div className="py-20 text-center text-sm text-text-muted">Loading confirmation...</div>}>
      <SuccessContent id={id} />
    </Suspense>
  );
}
