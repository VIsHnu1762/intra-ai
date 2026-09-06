"use client";

import { useState } from "react";
import Link from "next/link";
import { Bell, Search } from "lucide-react";
import { cn, formatDate } from "@/lib/utils";
import { useInterviews } from "@/hooks/queries/useScheduling";

interface HeaderProps {
  title?: string;
}

export default function Header({ title = "Dashboard" }: HeaderProps) {
  const [notifOpen, setNotifOpen] = useState(false);
  const { data } = useInterviews({ per_page: 5 });

  const interviews = data?.interviews ?? [];
  const notifications = interviews.map((iv) => {
    const candName = iv.candidate?.name || "Candidate";
    let text = `Interview scheduled for ${candName}`;
    if (iv.status === "completed") {
      text = `Interview completed — ${candName}`;
    } else if (iv.status === "in_progress") {
      text = `Interview currently in progress: ${candName}`;
    }
    const timeStr = iv.scheduled_at ? formatDate(iv.scheduled_at) : "Recently";
    return {
      id: iv.id,
      text,
      time: timeStr,
      unread: iv.status === "scheduled" || iv.status === "in_progress",
      link: `/admin/candidates/${iv.candidate?.id || iv.id}`,
    };
  });

  const unreadCount = notifications.filter((n) => n.unread).length;

  return (
    <header className="flex h-16 items-center gap-4 bg-surface border-b border-border px-6 shrink-0">
      {/* Page title */}
      <h1 className="text-lg font-semibold text-text-primary mr-auto">{title}</h1>

      {/* Search */}
      <div className="hidden md:flex items-center gap-2 h-9 w-64 rounded-full border border-border bg-bg px-3 text-sm text-text-muted focus-within:border-brand focus-within:ring-1 focus-within:ring-brand/20 transition-all duration-100">
        <Search className="h-4 w-4 shrink-0" />
        <input
          type="text"
          placeholder="Search candidates, jobs..."
          className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted focus:outline-none"
        />
      </div>

      {/* Notifications */}
      <div className="relative">
        <button
          onClick={() => setNotifOpen((prev) => !prev)}
          className="relative flex h-9 w-9 items-center justify-center rounded-full text-text-muted hover:bg-bg hover:text-text-primary transition-colors duration-100"
          aria-label="Notifications"
        >
          <Bell className="h-5 w-5" />
          {unreadCount > 0 && (
            <span className="absolute top-1.5 right-1.5 flex h-2 w-2 rounded-full bg-brand" />
          )}
        </button>

        {notifOpen && (
          <>
            <div
              className="fixed inset-0 z-10"
              onClick={() => setNotifOpen(false)}
            />
            <div className="absolute right-0 top-11 z-20 w-80 rounded-lg border border-border bg-surface shadow-lg">
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <span className="text-sm font-semibold text-text-primary">
                  Recent Activity
                </span>
                {unreadCount > 0 && (
                  <span className="text-xs text-brand font-medium">
                    {unreadCount} active
                  </span>
                )}
              </div>
              {notifications.length === 0 ? (
                <div className="p-6 text-center text-xs text-text-muted">
                  No recent activity or notifications.
                </div>
              ) : (
                <ul className="divide-y divide-border max-h-64 overflow-y-auto">
                  {notifications.map((n) => (
                    <li key={n.id}>
                      <Link
                        href={n.link}
                        onClick={() => setNotifOpen(false)}
                        className={cn(
                          "flex items-start gap-3 px-4 py-3 hover:bg-bg transition-colors duration-100 cursor-pointer block",
                          n.unread && "bg-brand-light/30"
                        )}
                      >
                        {n.unread ? (
                          <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-brand" />
                        ) : (
                          <span className="mt-1.5 h-2 w-2 shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-text-primary">{n.text}</p>
                          <p className="text-xs text-text-muted mt-0.5">{n.time}</p>
                        </div>
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
              <div className="px-4 py-2.5 border-t border-border">
                <Link
                  href="/admin/interviews"
                  onClick={() => setNotifOpen(false)}
                  className="text-sm text-brand hover:text-brand-hover font-medium transition-colors duration-100"
                >
                  View all interviews
                </Link>
              </div>
            </div>
          </>
        )}
      </div>
    </header>
  );
}
