import CandidateNav from "@/components/layout/candidate-nav";
import Link from "next/link";
import { Logo } from "@/components/ui/logo";

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-bg flex flex-col">
      <CandidateNav />

      <main className="flex-1">{children}</main>

      {/* Footer */}
      <footer className="border-t border-border bg-surface mt-16">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
            <Link href="/" className="flex items-center gap-2">
              <Logo size="sm" withText />
            </Link>

            <div className="flex items-center gap-6">
              <Link
                href="/jobs"
                className="text-sm text-text-muted hover:text-text-primary transition-colors"
              >
                Open Positions
              </Link>
              <Link
                href="/portal"
                className="text-sm text-text-muted hover:text-text-primary transition-colors"
              >
                Candidate Portal
              </Link>
            </div>

            <p className="text-xs text-text-muted">
              &copy; {new Date().getFullYear()} Intra AI. All rights reserved.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
