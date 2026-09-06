"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

export interface StageShellProps {
  header?: React.ReactNode;
  agentStage: React.ReactNode;
  transcriptPanel: React.ReactNode;
  controlsDock: React.ReactNode;
  banner?: React.ReactNode;
  className?: string;
}

export function StageShell({
  header,
  agentStage,
  transcriptPanel,
  controlsDock,
  banner,
  className,
}: StageShellProps) {
  return (
    <div
      className={cn(
        "relative flex h-screen w-full flex-col overflow-hidden bg-obsidian-950 text-obsidian-text select-none",
        className
      )}
    >
      {/* Optional Top Warning / Connection Banner */}
      {banner}

      {/* Top Header Slot */}
      {header && (
        <header className="shrink-0 border-b border-white/10 bg-obsidian-900/60 backdrop-blur-md z-40">
          {header}
        </header>
      )}

      {/* Main Responsive Grid Stage */}
      <main className="relative flex flex-1 overflow-hidden">
        {/* Left / Primary Workspace: Agent Persona & Candidate Stage */}
        <div className="relative flex flex-1 flex-col items-center justify-center p-4 lg:p-8 overflow-y-auto">
          {agentStage}
        </div>

        {/* Right / Sidebar: Live Transcript Stream */}
        <aside className="hidden lg:flex w-84 xl:w-96 flex-col shrink-0 border-l border-white/10 bg-obsidian-900/70 backdrop-blur-xl z-20">
          {transcriptPanel}
        </aside>
      </main>

      {/* Bottom Floating Media Control Dock */}
      <footer className="shrink-0 border-t border-white/10 bg-obsidian-900/80 backdrop-blur-xl px-4 py-3 z-30 flex items-center justify-center">
        {controlsDock}
      </footer>
    </div>
  );
}
