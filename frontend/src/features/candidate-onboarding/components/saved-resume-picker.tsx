"use client";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@/context/AuthContext";
import { onboardingApi, type ResumeVersion } from "../api";

export function SavedResumePicker({ selected, onSelect }: { selected: boolean; onSelect: (resume: ResumeVersion | null) => void }) {
  const { user } = useAuth();
  const query = useQuery({ queryKey: ["onboarding", user?.id], queryFn: onboardingApi.status, enabled: user?.role === "candidate", retry: false });
  const resume = query.data?.current;
  if (!resume) return null;
  return <label className="flex items-start gap-3 rounded-lg border border-brand/20 bg-brand-light p-4 text-sm">
    <input type="checkbox" className="mt-1" checked={selected} onChange={e => onSelect(e.target.checked ? resume : null)} />
    <span>Use my saved resume: <strong>{resume.filename}</strong> (v{resume.version})<span className="mt-1 block text-text-muted">This uses your signed-in profile and its parsed facts.</span></span>
  </label>;
}
