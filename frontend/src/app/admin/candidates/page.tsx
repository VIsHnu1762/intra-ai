"use client";

import { useState } from "react";
import Link from "next/link";
import { Search, LayoutGrid, List } from "lucide-react";
import { Avatar } from "@/components/ui/avatar";
import { Card } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ScoreBadge } from "@/components/ui/score-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { cn, formatDate } from "@/lib/utils";
import type { ApplicationStatus } from "@/types";
import { useCandidates } from "@/hooks/queries/useCandidates";

interface CandidateRow {
  id: string;
  name: string;
  email: string;
  job: string;
  status: ApplicationStatus;
  score: number;
  applied: string;
}

type ViewMode = "table" | "kanban";

const KANBAN_COLUMNS: { key: ApplicationStatus; label: string; color: string }[] = [
  { key: "applied", label: "Applied", color: "bg-border" },
  { key: "shortlisted", label: "Shortlisted", color: "bg-brand" },
  { key: "invited", label: "Invited", color: "bg-amber-500" },
  { key: "scheduled", label: "Scheduled", color: "bg-purple-500" },
  { key: "in_progress", label: "In Progress", color: "bg-warning" },
  { key: "completed", label: "Completed", color: "bg-success" },
];

export default function CandidatesPage() {
  const [view, setView] = useState<ViewMode>("table");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ApplicationStatus | "all">("all");

  const { data, isLoading } = useCandidates({
    search: search.trim() || undefined,
  });

  const candidatesList = data?.candidates || [];
  const candidateRows: CandidateRow[] = candidatesList.map((c) => {
    const latestApp = c.applications && c.applications.length > 0 ? c.applications[0] : null;
    return {
      id: c.id,
      name: c.name,
      email: c.email,
      job: latestApp?.job?.title || (c.phone ? `Phone: ${c.phone}` : "Candidate Profile"),
      status: (latestApp?.status || "applied") as ApplicationStatus,
      score: latestApp?.eligibility_score != null ? Math.round(latestApp.eligibility_score) : 0,
      applied: latestApp?.created_at || c.created_at,
    };
  });

  const filtered = candidateRows.filter((c) => {
    const matchSearch =
      search === "" ||
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      c.email.toLowerCase().includes(search.toLowerCase());
    const matchStatus = statusFilter === "all" || c.status === statusFilter;
    return matchSearch && matchStatus;
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Candidates</h1>
        <p className="text-sm text-text-muted mt-0.5">
          {candidateRows.length} candidates registered.
        </p>
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Search */}
        <div className="flex items-center gap-2 h-9 flex-1 min-w-[200px] max-w-sm rounded-full border border-border bg-surface px-3 text-sm text-text-muted focus-within:border-brand focus-within:ring-1 focus-within:ring-brand/20 transition-all duration-100">
          <Search className="h-4 w-4 shrink-0" />
          <input
            type="text"
            placeholder="Search candidates or jobs..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
          />
        </div>

        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ApplicationStatus | "all")}
          className="h-9 rounded-lg border border-border bg-surface px-3 text-sm text-text-muted focus:border-brand focus:outline-none"
        >
          <option value="all">All Statuses</option>
          <option value="applied">Applied</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="invited">Invited</option>
          <option value="scheduled">Scheduled</option>
          <option value="in_progress">In Progress</option>
          <option value="completed">Completed</option>
          <option value="rejected">Rejected</option>
        </select>

        {/* View toggle */}
        <div className="flex rounded-lg border border-border overflow-hidden">
          <button
            onClick={() => setView("table")}
            className={cn(
              "flex h-9 w-9 items-center justify-center transition-colors duration-100",
              view === "table" ? "bg-brand text-white" : "text-text-muted hover:bg-bg"
            )}
            aria-label="Table view"
          >
            <List className="h-4 w-4" />
          </button>
          <button
            onClick={() => setView("kanban")}
            className={cn(
              "flex h-9 w-9 items-center justify-center transition-colors duration-100",
              view === "kanban" ? "bg-brand text-white" : "text-text-muted hover:bg-bg"
            )}
            aria-label="Kanban view"
          >
            <LayoutGrid className="h-4 w-4" />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="py-16 text-center text-sm text-text-muted">
          Loading candidates...
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No candidates found"
          description="Try adjusting your search or filter."
        />
      ) : view === "table" ? (
        /* ── TABLE VIEW ── */
        <>
          <Card className="hidden md:block overflow-hidden">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  {["Candidate", "Email", "Job Applied", "Status", "Score", "Applied"].map((h) => (
                    <th key={h} className="text-left px-5 py-3 text-xs font-medium text-text-muted uppercase tracking-wide">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((c) => (
                  <tr key={c.id} className="hover:bg-bg transition-colors duration-100">
                    <td className="px-5 py-3">
                      <Link href={`/admin/candidates/${c.id}`} prefetch={true} className="flex items-center gap-2.5">
                        <Avatar size="sm" name={c.name} />
                        <span className="text-sm font-medium text-text-primary hover:text-brand transition-colors duration-100">
                          {c.name}
                        </span>
                      </Link>
                    </td>
                    <td className="px-5 py-3 text-sm text-text-muted">{c.email}</td>
                    <td className="px-5 py-3 text-sm text-text-muted">{c.job}</td>
                    <td className="px-5 py-3"><StatusBadge status={c.status} /></td>
                    <td className="px-5 py-3">
                      {c.score > 0 ? <ScoreBadge score={c.score} size="sm" /> : <span className="text-xs text-text-muted">—</span>}
                    </td>
                    <td className="px-5 py-3 text-sm text-text-muted">{formatDate(c.applied)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
          <div className="space-y-3 md:hidden">
            {filtered.map((c) => (
              <Card key={c.id} className="p-4">
                <Link href={`/admin/candidates/${c.id}`} prefetch={true} className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <Avatar size="sm" name={c.name} />
                    <div>
                      <p className="text-sm font-medium text-text-primary">{c.name}</p>
                      <p className="text-xs text-text-muted">{c.job}</p>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <StatusBadge status={c.status} />
                    {c.score > 0 && <ScoreBadge score={c.score} size="sm" />}
                  </div>
                </Link>
              </Card>
            ))}
          </div>
        </>
      ) : (
        /* ── KANBAN VIEW ── */
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {KANBAN_COLUMNS.map((col) => {
              const cards = filtered.filter((c) => c.status === col.key);
              return (
                <div key={col.key} className="w-64 flex flex-col gap-2">
                  {/* Column header */}
                  <div className="flex items-center gap-2 px-1">
                    <span className={`h-2 w-2 rounded-full ${col.color}`} />
                    <span className="text-sm font-semibold text-text-primary">
                      {col.label}
                    </span>
                    <span className="ml-auto text-xs text-text-muted bg-border rounded-full px-2 py-0.5">
                      {cards.length}
                    </span>
                  </div>
                  {/* Cards */}
                  <div className="flex flex-col gap-2">
                    {cards.length === 0 ? (
                      <div className="rounded-lg border-2 border-dashed border-border py-6 text-center">
                        <p className="text-xs text-text-muted">No candidates</p>
                      </div>
                    ) : (
                      cards.map((c) => (
                        <Link key={c.id} href={`/admin/candidates/${c.id}`} prefetch={true}>
                          <Card className="p-3 hover:border-brand/40 hover:bg-bg transition-all duration-100 cursor-pointer">
                            <div className="flex items-start gap-2">
                              <Avatar size="sm" name={c.name} />
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-text-primary truncate">
                                  {c.name}
                                </p>
                                <p className="text-xs text-text-muted truncate mt-0.5">
                                  {c.job}
                                </p>
                              </div>
                              {c.score > 0 && (
                                <ScoreBadge score={c.score} size="sm" />
                              )}
                            </div>
                            <p className="text-xs text-text-muted mt-2">
                              {formatDate(c.applied)}
                            </p>
                          </Card>
                        </Link>
                      ))
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
