"use client";

import React, { useState, createContext, useContext, useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Menu, Loader2 } from "lucide-react";
import Sidebar from "./sidebar";
import Header from "./header";
import { MorganAssistant } from "@/components/voice/morgan-assistant";
import { cn } from "@/lib/utils";
import { useAuth } from "@/context/AuthContext";

interface SidebarContextType {
  collapsed: boolean;
  setCollapsed: React.Dispatch<React.SetStateAction<boolean>>;
  toggleSidebar: () => void;
}

const SidebarContext = createContext<SidebarContextType>({
  collapsed: false,
  setCollapsed: () => {},
  toggleSidebar: () => {},
});

export const useSidebar = () => useContext(SidebarContext);

interface AdminLayoutProps {
  children: React.ReactNode;
  title?: string;
}

export default function AdminLayout({ children, title }: AdminLayoutProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const { user, role, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  const isCandidate =
    (role === "candidate" || user?.role === "candidate") &&
    role !== "admin" &&
    role !== "recruiter" &&
    user?.role !== "admin" &&
    user?.role !== "recruiter";

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      const redirectUrl = encodeURIComponent(pathname || "/admin/dashboard");
      router.replace(`/login?from=${redirectUrl}`);
    } else if (!isLoading && isAuthenticated && isCandidate) {
      router.replace("/portal");
    }
  }, [isLoading, isAuthenticated, isCandidate, router, pathname]);

  const toggleSidebar = () => setCollapsed((prev) => !prev);

  if (isLoading || (!isLoading && isAuthenticated && isCandidate)) {
    return (
      <div className="h-screen bg-bg flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <Loader2 className="h-8 w-8 text-brand animate-spin" />
          <p className="text-sm text-text-muted">
            {isCandidate
              ? "Redirecting to candidate portal..."
              : "Verifying admin access..."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <SidebarContext.Provider value={{ collapsed, setCollapsed, toggleSidebar }}>
      <div className="flex h-screen overflow-hidden bg-bg">
        {/* Mobile overlay */}
        {mobileSidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-black/40 md:hidden"
            onClick={() => setMobileSidebarOpen(false)}
          />
        )}

        {/* Sidebar — hidden on mobile unless toggled */}
        <div
          className={cn(
            "fixed inset-y-0 left-0 z-40 md:relative md:flex md:z-auto transition-transform duration-200",
            mobileSidebarOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
          )}
        >
          <Sidebar
            collapsed={collapsed}
            onToggle={toggleSidebar}
          />
        </div>

      {/* Main content area */}
      <div className="flex flex-1 flex-col overflow-hidden min-w-0">
        {/* Header row — mobile burger + header */}
        <div className="flex items-center md:block">
          {/* Mobile menu trigger */}
          <button
            onClick={() => setMobileSidebarOpen(true)}
            className="md:hidden flex h-16 w-16 shrink-0 items-center justify-center text-text-muted hover:text-text-primary border-b border-border bg-surface"
            aria-label="Open sidebar"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex-1">
            <Header title={title} />
          </div>
        </div>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
      <MorganAssistant />
    </SidebarContext.Provider>
  );
}
