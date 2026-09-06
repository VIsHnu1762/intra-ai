import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(date));
}

export function formatTime(date: string | Date): string {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(new Date(date));
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m > 0 ? `${h}h ${m}m` : `${h}h`;
}

export function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

export function getScoreColor(score: number): string {
  if (score >= 85) return "text-success";
  if (score >= 70) return "text-brand";
  if (score >= 55) return "text-warning";
  return "text-error";
}

export function getScoreBg(score: number): string {
  if (score >= 85) return "bg-success-light text-success";
  if (score >= 70) return "bg-brand-light text-brand";
  if (score >= 55) return "bg-warning-light text-warning";
  return "bg-error-light text-error";
}

export function getRecommendationLabel(rec: string): string {
  const labels: Record<string, string> = {
    strong_hire: "Strong Hire",
    hire: "Hire",
    maybe: "Maybe",
    no_hire: "No Hire",
  };
  return labels[rec] ?? rec;
}
