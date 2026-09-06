"use client";

import * as React from "react";
import { MessageSquare, Video } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface MobileStageSwitcherProps {
  activeTab: "stage" | "transcript";
  onTabChange: (tab: "stage" | "transcript") => void;
  unreadTranscriptCount?: number;
  className?: string;
}

export function MobileStageSwitcher({
  activeTab,
  onTabChange,
  unreadTranscriptCount = 0,
  className,
}: MobileStageSwitcherProps) {
  return (
    <div
      className={cn(
        "flex lg:hidden items-center justify-center p-1 rounded-full bg-white/10 border border-white/10 backdrop-blur-md",
        className
      )}
    >
      <Button
        variant={activeTab === "stage" ? "alex" : "ghost"}
        size="sm"
        onClick={() => onTabChange("stage")}
        className={cn(
          "h-7 text-xs px-3 rounded-full gap-1.5",
          activeTab !== "stage" && "text-slate-300 hover:text-white"
        )}
      >
        <Video className="h-3.5 w-3.5" />
        <span>Stage</span>
      </Button>

      <Button
        variant={activeTab === "transcript" ? "alex" : "ghost"}
        size="sm"
        onClick={() => onTabChange("transcript")}
        className={cn(
          "h-7 text-xs px-3 rounded-full gap-1.5 relative",
          activeTab !== "transcript" && "text-slate-300 hover:text-white"
        )}
      >
        <MessageSquare className="h-3.5 w-3.5" />
        <span>Transcript</span>
        {unreadTranscriptCount > 0 && activeTab !== "transcript" && (
          <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-cyan-500 text-[10px] font-bold text-black">
            {unreadTranscriptCount}
          </span>
        )}
      </Button>
    </div>
  );
}
