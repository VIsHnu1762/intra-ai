"use client";

import * as React from "react";
import { WifiOff, RefreshCw, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { WebRTCConnectionStatus } from "@/types/intra-ai";

export interface ConnectionBannerProps {
  status: WebRTCConnectionStatus;
  onReconnect?: () => void;
  className?: string;
}

export function ConnectionBanner({
  status,
  onReconnect,
  className,
}: ConnectionBannerProps) {
  if (status === "connected" || status === "idle") {
    return null;
  }

  const isReconnecting = status === "reconnecting" || status === "connecting";
  const isFailed = status === "failed" || status === "disconnected";

  return (
    <div
      role="alert"
      className={cn(
        "flex items-center justify-between px-4 py-2 text-xs font-medium transition-all duration-300 select-none z-50",
        isReconnecting && "bg-amber-950/90 text-amber-200 border-b border-amber-500/30",
        isFailed && "bg-red-950/90 text-red-200 border-b border-red-500/30",
        className
      )}
    >
      <div className="flex items-center gap-2">
        {isReconnecting ? (
          <RefreshCw className="h-3.5 w-3.5 animate-spin text-amber-400 shrink-0" />
        ) : (
          <WifiOff className="h-3.5 w-3.5 text-red-400 shrink-0" />
        )}
        <span>
          {isReconnecting
            ? "Reconnecting audio stream... Please hold on."
            : "Voice audio stream lost. The AI interviewer cannot hear you."}
        </span>
      </div>

      {isFailed && onReconnect && (
        <Button
          variant="secondary"
          size="sm"
          onClick={onReconnect}
          className="h-7 text-[11px] px-3 border-red-400 text-red-200 hover:bg-red-900/40"
        >
          Reconnect
        </Button>
      )}
    </div>
  );
}
