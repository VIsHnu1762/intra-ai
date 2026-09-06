"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X, ArrowRight, LogOut } from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { Logo } from "@/components/ui/logo";
import { useAuth } from "@/context/AuthContext";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Pricing", href: "#pricing" },
];

export default function PublicNav() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, isAuthenticated, isLoading, logout } = useAuth();
  const displayName = user?.name || "Candidate";
  const initials = getInitials(displayName);
  const isHr = user?.role === "admin" || user?.role === "recruiter";
  const dashboardHref = isHr ? "/admin/dashboard" : "/portal";
  const dashboardLabel = isHr ? "HR Dashboard" : "Candidate Portal";

  const handleNavClick = (href: string) => {
    setMobileOpen(false);
    const id = href.replace("#", "");
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <header className="sticky top-0 z-50 bg-surface border-b border-border">
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center shrink-0">
            <Logo size="default" withText />
          </Link>

          {/* Desktop nav links */}
          <ul className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <button
                  onClick={() => handleNavClick(link.href)}
                  className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors duration-100 rounded-full hover:bg-bg cursor-pointer"
                >
                  {link.label}
                </button>
              </li>
            ))}
            <li>
              <Link
                href="/jobs"
                className="px-4 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors duration-100 rounded-full hover:bg-bg inline-block"
              >
                Browse Jobs
              </Link>
            </li>
          </ul>

          {/* Desktop CTA */}
          <div className="hidden md:flex items-center gap-3">
            {isAuthenticated ? (
              <>
                <Link
                  href={dashboardHref}
                  className="inline-flex items-center gap-1.5 justify-center rounded-full bg-brand px-4 py-2 text-sm font-semibold text-white hover:bg-brand-hover transition-colors duration-100 shadow-xs"
                >
                  <span>{dashboardLabel}</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
                <div className="flex items-center gap-2 pl-2 border-l border-border">
                  <div className="h-8 w-8 rounded-full bg-brand-light border border-brand/20 flex items-center justify-center">
                    <span className="text-xs font-semibold text-brand">
                      {initials}
                    </span>
                  </div>
                  <button
                    onClick={() => logout("/login")}
                    className="p-1.5 text-text-muted hover:text-text-primary hover:bg-bg rounded-md transition-colors"
                    title="Sign out"
                  >
                    <LogOut className="h-4 w-4" />
                  </button>
                </div>
              </>
            ) : !isLoading ? (
              <>
                <Link
                  href="/login"
                  className="text-sm font-medium text-text-muted hover:text-text-primary transition-colors duration-100"
                >
                  Sign In
                </Link>
                <Link
                  href="/signup"
                  className="inline-flex items-center justify-center rounded-full bg-brand px-5 py-2 text-sm font-semibold text-white hover:bg-brand-hover transition-colors duration-100"
                >
                  Get Started
                </Link>
              </>
            ) : null}
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen((prev) => !prev)}
            className="md:hidden p-2 rounded-lg text-text-muted hover:text-text-primary hover:bg-bg transition-colors duration-100"
            aria-label="Toggle menu"
          >
            {mobileOpen ? (
              <X className="h-5 w-5" />
            ) : (
              <Menu className="h-5 w-5" />
            )}
          </button>
        </div>

        {/* Mobile slide-down menu */}
        <div
          className={cn(
            "md:hidden overflow-hidden transition-all duration-200",
            mobileOpen ? "max-h-80 pb-4" : "max-h-0"
          )}
        >
          <ul className="flex flex-col gap-1 pt-2">
            {NAV_LINKS.map((link) => (
              <li key={link.href}>
                <button
                  onClick={() => handleNavClick(link.href)}
                  className="w-full text-left px-3 py-2.5 text-sm font-medium text-text-muted hover:text-text-primary hover:bg-bg rounded-lg transition-colors duration-100 cursor-pointer"
                >
                  {link.label}
                </button>
              </li>
            ))}
            <li>
              <Link
                href="/jobs"
                onClick={() => setMobileOpen(false)}
                className="w-full text-left px-3 py-2.5 text-sm font-medium text-text-muted hover:text-text-primary hover:bg-bg rounded-lg transition-colors duration-100 inline-block"
              >
                Browse Jobs
              </Link>
            </li>
          </ul>
          <div className="flex flex-col gap-2 pt-3 border-t border-border mt-2">
            {isAuthenticated ? (
              <>
                <Link
                  href={dashboardHref}
                  onClick={() => setMobileOpen(false)}
                  className="inline-flex items-center justify-center rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-hover transition-colors duration-100"
                >
                  {dashboardLabel}
                </Link>
                <button
                  onClick={() => {
                    setMobileOpen(false);
                    logout("/login");
                  }}
                  className="flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-text-muted hover:text-text-primary transition-colors"
                >
                  <LogOut className="h-4 w-4" />
                  Sign out ({displayName})
                </button>
              </>
            ) : !isLoading ? (
              <>
                <Link
                  href="/login"
                  onClick={() => setMobileOpen(false)}
                  className="px-3 py-2.5 text-sm font-medium text-text-muted hover:text-text-primary transition-colors duration-100"
                >
                  Sign In
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setMobileOpen(false)}
                  className="inline-flex items-center justify-center rounded-full bg-brand px-5 py-2.5 text-sm font-semibold text-white hover:bg-brand-hover transition-colors duration-100"
                >
                  Get Started
                </Link>
              </>
            ) : null}
          </div>
        </div>
      </nav>
    </header>
  );
}
