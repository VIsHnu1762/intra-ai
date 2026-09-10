"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Loader2 } from "lucide-react";
import CandidateNav from "@/components/layout/candidate-nav";
import { useAuth } from "@/context/AuthContext";
import Link from "next/link";
import { OnboardingNotice } from "@/features/candidate-onboarding/components/onboarding-notice";

export default function CandidateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { isAuthenticated, isLoading, user, role } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const isHr =
    role === "admin" ||
    role === "recruiter" ||
    user?.role === "admin" ||
    user?.role === "recruiter";

  // Interview invitation links are opaque, single-session tokens. The session
  // API intentionally exposes the lobby/start flow without an application
  // login, so an invited candidate must be able to enter `/interview/*` even
  // when their portal session has expired or they have never created an
  // account. Portal and schedule pages remain protected below.
  const isPublicInterview = pathname?.startsWith("/interview/") ?? false;

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !isPublicInterview) {
      const redirectUrl = encodeURIComponent(pathname || "/portal");
      router.replace(`/login?from=${redirectUrl}`);
    } else if (!isLoading && isAuthenticated && isHr && pathname === "/portal") {
      router.replace("/admin/dashboard");
    }
  }, [isLoading, isAuthenticated, isHr, isPublicInterview, router, pathname]);

  if (
    isLoading ||
    (!isLoading && isAuthenticated && isHr && pathname === "/portal")
  ) {
    return (
      <div className="min-h-screen bg-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 text-brand animate-spin" />
          <p className="text-sm text-text-muted">
            {isHr && pathname === "/portal"
              ? "Redirecting to HR dashboard..."
              : "Verifying session..."}
          </p>
        </div>
      </div>
    );
  }

  // Active live interview room has its own fixed dedicated header without tab switching
  const isInterviewRoom =
    pathname?.startsWith("/interview/") &&
    !pathname?.endsWith("/report") &&
    !pathname?.endsWith("/done");

  if (isInterviewRoom) {
    return <>{children}</>;
  }

  return (
    <div className="min-h-screen bg-bg flex flex-col">
      {/* Top bar */}
      <CandidateNav maxWidthClass="max-w-5xl" />

      {/* Page content */}
      <main className="flex-1">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 py-8">
          {!isHr && !isPublicInterview && <nav aria-label="Candidate tools" className="mb-6 flex flex-wrap gap-4 text-sm text-brand">
            <Link href="/portal">Applications</Link><Link href="/profile">My profile</Link>
          </nav>}
          {!isHr && pathname === "/portal" && <OnboardingNotice />}
          {children}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border py-5 mt-auto">
        <div className="mx-auto max-w-5xl px-4 sm:px-6 flex items-center justify-between">
          <p className="text-xs text-text-muted">
            &copy; {new Date().getFullYear()} Intra AI
          </p>
          <p className="text-xs text-text-muted">
            Adaptive Multi-Agent AI Voice Interviews
          </p>
        </div>
      </footer>
    </div>
  );
}
