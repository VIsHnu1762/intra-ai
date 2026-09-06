import * as React from "react";
import { cn } from "@/lib/utils";
import type { ApplicationStatus, JobStatus } from "@/types";

type AnyStatus = ApplicationStatus | JobStatus | string;

interface StatusConfig {
  label: string;
  className: string;
}

const STATUS_MAP: Record<string, StatusConfig> = {
  // Application statuses
  applied: { label: "Applied", className: "bg-border text-text-muted" },
  parsing: { label: "Parsing", className: "bg-border text-text-muted" },
  shortlisted: { label: "Shortlisted", className: "bg-brand-light text-brand" },
  invited: { label: "Invited", className: "bg-brand-light text-brand" },
  scheduled: { label: "Scheduled", className: "bg-purple-100 text-purple-700" },
  in_progress: { label: "In Progress", className: "bg-warning-light text-warning" },
  completed: { label: "Completed", className: "bg-success-light text-success" },
  rejected: { label: "Rejected", className: "bg-error-light text-error" },
  no_show: { label: "No Show", className: "bg-error-light text-error" },
  instant_pending: { label: "Instant Invite Pending", className: "bg-amber-100 text-amber-800" },
  instant_active: { label: "Instant Interview", className: "bg-purple-100 text-purple-700" },
  instant_expired: { label: "Instant Invite Expired", className: "bg-error-light text-error" },
  // Job statuses
  draft: { label: "Draft", className: "bg-border text-text-muted" },
  published: { label: "Published", className: "bg-success-light text-success" },
  closed: { label: "Closed", className: "bg-warning-light text-warning" },
  archived: { label: "Archived", className: "bg-border text-text-muted" },
};

export interface StatusBadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  status: AnyStatus;
}

function StatusBadge({ status, className, ...props }: StatusBadgeProps) {
  const config = STATUS_MAP[status] ?? {
    label: status,
    className: "bg-border text-text-muted",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.className,
        className
      )}
      {...props}
    >
      {config.label}
    </span>
  );
}

export { StatusBadge };
