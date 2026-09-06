"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  FileText,
  Briefcase,
  LogOut,
  Menu,
  X,
  ShieldAlert,
} from "lucide-react";
import { Logo } from "@/components/ui/logo";
import { useAuth } from "@/context/AuthContext";
import { cn, getInitials } from "@/lib/utils";

export interface CandidateNavProps {
  maxWidthClass?: string;
}

export default function CandidateNav({
  maxWidthClass = "max-w-7xl",
}: CandidateNavProps) {
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const displayName = user?.name || "Candidate";
  const displayEmail = user?.email || "";
  const initials = getInitials(displayName);
  const isAdminOrRecruiter =
    user?.role === "admin" || user?.role === "recruiter";

  // Determine active states
  const isJobsActive =
    pathname === "/jobs" || pathname.startsWith("/jobs/");
  const isPortalActive =
    pathname === "/portal" ||
    pathname.startsWith("/schedule") ||
    pathname.startsWith("/interview");

  return (
    <header className="sticky top-0 z-40 bg-surface border-b border-border shadow-2xs">
      <div
        className={cn(
          "mx-auto px-4 sm:px-6 lg:px-8 h-14 flex items-center justify-between",
          maxWidthClass
        )}
      >
        {/* Left: Brand Logo + Primary Nav Links */}
        <div className="flex items-center gap-6">
          <Link
            href={isAuthenticated ? (isAdminOrRecruiter ? "/admin/dashboard" : "/portal") : "/jobs"}
            className="flex items-center gap-2 shrink-0"
          >
            <Logo size="default" withText />
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1.5">
            {isAuthenticated && !isAdminOrRecruiter && (
              <Link
                href="/portal"
                className={cn(
                  "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                  isPortalActive
                    ? "bg-brand/10 text-brand font-semibold"
                    : "text-text-muted hover:text-text-primary hover:bg-bg"
                )}
              >
                <FileText className="h-4 w-4" />
                <span>My Applications</span>
              </Link>
            )}

            <Link
              href="/jobs"
              className={cn(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors",
                isJobsActive
                  ? "bg-brand/10 text-brand font-semibold"
                  : "text-text-muted hover:text-text-primary hover:bg-bg"
              )}
            >
              <Briefcase className="h-4 w-4" />
              <span>Browse Jobs</span>
            </Link>

            {isAdminOrRecruiter && (
              <Link
                href="/admin/dashboard"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-purple-600 hover:bg-purple-50 transition-colors"
              >
                <ShieldAlert className="h-4 w-4" />
                <span>Admin Console</span>
              </Link>
            )}
          </nav>
        </div>

        {/* Right: User identity & actions */}
        <div className="flex items-center gap-3">
          {isAuthenticated && user ? (
            <>
              {/* Desktop User Info */}
              <div className="hidden sm:flex items-center gap-2.5">
                <div className="h-8 w-8 rounded-full bg-brand-light border border-brand/20 flex items-center justify-center shrink-0">
                  <span className="text-xs font-semibold text-brand">
                    {initials}
                  </span>
                </div>
                <div className="flex flex-col leading-none text-left">
                  <span className="text-sm font-medium text-text-primary">
                    {displayName}
                  </span>
                  {displayEmail && (
                    <span className="text-xs text-text-muted mt-0.5 max-w-[180px] truncate">
                      {displayEmail}
                    </span>
                  )}
                </div>
              </div>

              {/* Mobile avatar */}
              <div className="flex sm:hidden items-center">
                <div className="h-8 w-8 rounded-full bg-brand-light border border-brand/20 flex items-center justify-center">
                  <span className="text-xs font-semibold text-brand">
                    {initials}
                  </span>
                </div>
              </div>

              <div className="w-px h-5 bg-border hidden sm:block" />

              {/* Sign out button */}
              <button
                onClick={() => logout("/login")}
                className={cn(
                  "flex items-center gap-1.5 text-sm text-text-muted cursor-pointer",
                  "hover:text-text-primary transition-colors px-2.5 py-1.5 rounded-lg hover:bg-bg"
                )}
                title="Sign out of Intra AI"
              >
                <LogOut className="h-4 w-4" />
                <span className="hidden sm:inline">Sign out</span>
              </button>
            </>
          ) : !isLoading ? (
            <div className="hidden sm:flex items-center gap-2.5">
              <Link
                href="/login"
                className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors px-3 py-1.5 rounded-lg hover:bg-bg"
              >
                Sign In
              </Link>
              <Link
                href="/signup"
                className="inline-flex items-center justify-center rounded-lg bg-brand px-4 py-1.5 text-sm font-semibold text-white hover:bg-brand-hover transition-colors shadow-xs"
              >
                Sign Up
              </Link>
            </div>
          ) : null}

          {/* Mobile hamburger menu toggle */}
          <button
            onClick={() => setMobileOpen((prev) => !prev)}
            className="md:hidden p-1.5 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg transition-colors"
            aria-label="Toggle navigation"
          >
            {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="md:hidden border-t border-border bg-surface px-4 py-3 flex flex-col gap-2">
          {isAuthenticated && !isAdminOrRecruiter && (
            <Link
              href="/portal"
              onClick={() => setMobileOpen(false)}
              className={cn(
                "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium",
                isPortalActive
                  ? "bg-brand/10 text-brand font-semibold"
                  : "text-text-muted hover:bg-bg"
              )}
            >
              <FileText className="h-4 w-4" />
              <span>My Applications</span>
            </Link>
          )}

          <Link
            href="/jobs"
            onClick={() => setMobileOpen(false)}
            className={cn(
              "flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium",
              isJobsActive
                ? "bg-brand/10 text-brand font-semibold"
                : "text-text-muted hover:bg-bg"
            )}
          >
            <Briefcase className="h-4 w-4" />
            <span>Browse Jobs</span>
          </Link>

          {isAdminOrRecruiter && (
            <Link
              href="/admin/dashboard"
              onClick={() => setMobileOpen(false)}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium text-purple-600 hover:bg-purple-50"
            >
              <ShieldAlert className="h-4 w-4" />
              <span>Admin Console</span>
            </Link>
          )}

          {isAuthenticated ? (
            <div className="pt-2 border-t border-border mt-1 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-7 w-7 rounded-full bg-brand-light border border-brand/20 flex items-center justify-center">
                  <span className="text-xs font-semibold text-brand">
                    {initials}
                  </span>
                </div>
                <div className="flex flex-col leading-none">
                  <span className="text-xs font-medium text-text-primary">
                    {displayName}
                  </span>
                  {displayEmail && (
                    <span className="text-[11px] text-text-muted">
                      {displayEmail}
                    </span>
                  )}
                </div>
              </div>

              <button
                onClick={() => {
                  setMobileOpen(false);
                  logout("/login");
                }}
                className="text-xs text-text-muted hover:text-text-primary flex items-center gap-1 p-1 rounded"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign out
              </button>
            </div>
          ) : !isLoading ? (
            <div className="flex flex-col gap-2 pt-2 border-t border-border mt-1">
              <Link
                href="/login"
                onClick={() => setMobileOpen(false)}
                className="px-3 py-2 text-sm font-medium text-text-muted hover:text-text-primary hover:bg-bg rounded-lg"
              >
                Sign In
              </Link>
              <Link
                href="/signup"
                onClick={() => setMobileOpen(false)}
                className="flex items-center justify-center rounded-lg bg-brand px-3 py-2 text-sm font-semibold text-white hover:bg-brand-hover"
              >
                Sign Up
              </Link>
            </div>
          ) : null}
        </div>
      )}
    </header>
  );
}
