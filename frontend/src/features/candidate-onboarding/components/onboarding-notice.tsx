"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { onboardingApi } from "../api";

export function OnboardingNotice() {
  const { user, isAuthenticated } = useAuth();
  const query = useQuery({ queryKey: ["onboarding", user?.id], queryFn: onboardingApi.status,
    enabled: isAuthenticated && user?.role === "candidate", retry: false, staleTime: 60_000 });
  if (!query.data?.needs_onboarding) return null;
  return <aside className="mb-6 rounded-xl border border-brand/20 bg-brand-light p-4 text-sm">
    <p className="font-semibold text-text-primary">Set up your candidate profile</p>
    <p className="mt-1 text-text-muted">Upload your resume once, then reuse it for applications and practice.</p>
    <Link className="mt-2 inline-block font-medium text-brand underline" href="/profile">Add your resume</Link>
  </aside>;
}
