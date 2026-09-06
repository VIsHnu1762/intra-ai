"use client";

import * as React from "react";
import { MicOff, CameraOff, AlertCircle, RefreshCw } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface MediaPermissionModalProps {
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  type?: "microphone" | "camera" | "both";
  onRetry?: () => void;
}

export function MediaPermissionModal({
  open,
  onOpenChange,
  type = "microphone",
  onRetry,
}: MediaPermissionModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md bg-obsidian-900 border-obsidian-border text-obsidian-text">
        <DialogHeader className="gap-2">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-red-950/80 border border-red-500/30 text-red-400 mx-auto sm:mx-0">
            {type === "camera" ? (
              <CameraOff className="h-6 w-6" />
            ) : (
              <MicOff className="h-6 w-6" />
            )}
          </div>
          <DialogTitle className="text-lg font-bold text-white">
            {type === "camera"
              ? "Camera Access Blocked"
              : type === "both"
              ? "Microphone & Camera Access Blocked"
              : "Microphone Access Blocked"}
          </DialogTitle>
          <DialogDescription className="text-sm text-slate-400">
            Intra AI relies on natural speech-to-speech interaction. The AI interviewers
            cannot hear your answers until you enable microphone permissions in your browser.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg bg-obsidian-850 p-4 text-xs text-slate-300 space-y-2 border border-white/5">
          <div className="font-semibold text-white flex items-center gap-1.5">
            <AlertCircle className="h-3.5 w-3.5 text-cyan-400" />
            How to unblock permissions:
          </div>
          <ol className="list-decimal list-inside space-y-1 pl-1 text-slate-400">
            <li>Click the lock or camera icon in your browser address bar (top-left).</li>
            <li>Toggle <strong>Microphone</strong> and <strong>Camera</strong> to <em>Allow</em>.</li>
            <li>Click the <strong>Retry Connection</strong> button below.</li>
          </ol>
        </div>

        <DialogFooter className="gap-2 sm:gap-0 mt-4">
          <Button
            variant="obsidian"
            onClick={() => onOpenChange?.(false)}
            className="w-full sm:w-auto"
          >
            Dismiss
          </Button>
          <Button
            variant="alex"
            onClick={() => {
              if (onRetry) onRetry();
              else window.location.reload();
            }}
            className="w-full sm:w-auto inline-flex items-center gap-2"
          >
            <RefreshCw className="h-4 w-4" />
            Retry Connection
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
