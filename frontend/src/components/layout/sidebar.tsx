"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  Users,
  Video,
  FileText,
  Settings,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn, getInitials } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";
import { Logo } from "@/components/ui/logo";

const NAV_ITEMS = [
  { label: "Dashboard", href: "/admin/dashboard", icon: LayoutDashboard },
  { label: "Jobs", href: "/admin/jobs", icon: Briefcase },
  { label: "Candidates", href: "/admin/candidates", icon: Users },
  { label: "Interviews", href: "/admin/interviews", icon: Video },
  { label: "Reports", href: "/admin/reports", icon: FileText },
  { label: "Settings", href: "/admin/settings", icon: Settings },
];

const DEFAULT_USER = {
  name: "Intra AI User",
  email: "recruiter@intra-ai.com",
  role: "Recruiter",
};

interface SidebarProps {
  collapsed?: boolean;
  onToggle?: () => void;
}

export default function Sidebar({ collapsed = false, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const currentUser = user || DEFAULT_USER;

  return (
    <aside
      className={cn(
        "relative flex flex-col bg-surface border-r border-border transition-all duration-200 shrink-0",
        collapsed ? "w-16" : "w-60"
      )}
    >
      {/* Logo */}
      <div
        className={cn(
          "flex items-center h-16 border-b border-border px-4",
          collapsed ? "justify-center" : "gap-2.5 px-5"
        )}
      >
        <Logo size="default" withText={!collapsed} />
      </div>

      {/* Collapse toggle */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-[68px] z-10 flex h-6 w-6 items-center justify-center rounded-full bg-surface border border-border text-text-muted hover:text-text-primary hover:border-brand transition-colors duration-100 shadow-sm"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5" />
        ) : (
          <ChevronLeft className="h-3.5 w-3.5" />
        )}
      </button>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <ul className="flex flex-col gap-0.5">
          {NAV_ITEMS.map(({ label, href, icon: Icon }) => {
            const isActive = pathname === href || pathname.startsWith(href + "/");
            return (
              <li key={href}>
                <Link
                  href={href}
                  prefetch={true}
                  title={collapsed ? label : undefined}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-100",
                    collapsed && "justify-center px-2",
                    isActive
                      ? "bg-brand-light text-brand"
                      : "text-text-muted hover:bg-bg hover:text-text-primary"
                  )}
                >
                  <Icon
                    className={cn(
                      "h-4 w-4 shrink-0",
                      isActive ? "text-brand" : "text-text-muted"
                    )}
                  />
                  {!collapsed && <span>{label}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User profile */}
      <div className="border-t border-border p-3">
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg px-2 py-2",
            collapsed && "justify-center"
          )}
        >
          {/* Avatar */}
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-white text-xs font-semibold">
            {getInitials(currentUser.name)}
          </div>
          {!collapsed && (
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">
                {currentUser.name}
              </p>
              <p className="text-xs text-text-muted truncate capitalize">
                {currentUser.role || currentUser.email}
              </p>
            </div>
          )}
          {!collapsed && (
            <button
              onClick={() => logout("/login")}
              className="text-text-muted hover:text-error transition-colors duration-100 p-1 rounded-md hover:bg-bg cursor-pointer"
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
        {collapsed && (
          <button
            onClick={() => logout("/login")}
            className="mt-1 flex w-full items-center justify-center p-2 text-text-muted hover:text-error rounded-lg hover:bg-bg transition-colors duration-100 cursor-pointer"
            aria-label="Sign out"
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  );
}
