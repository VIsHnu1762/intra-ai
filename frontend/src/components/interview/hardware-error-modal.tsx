"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Camera,
  Mic,
  AlertTriangle,
  RefreshCw,
  ArrowLeft,
  ExternalLink,
  ShieldAlert,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface HardwareErrorModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  failedType?: "camera" | "microphone" | "both" | "network" | null;
  onRetry: () => void;
}

type BrowserTab = "chrome" | "safari" | "firefox";

export function HardwareErrorModal({
  open,
  onOpenChange,
  failedType = "both",
  onRetry,
}: HardwareErrorModalProps) {
  const [selectedBrowser, setSelectedBrowser] = useState<BrowserTab>("chrome");

  const isCamera = failedType === "camera" || failedType === "both";
  const isMic = failedType === "microphone" || failedType === "both";
  const isNetwork = failedType === "network";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md p-6 bg-surface border-border sm:max-w-lg">
        <DialogHeader>
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-error-light text-error flex items-center justify-center shrink-0">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold text-text-primary">
                {isNetwork
                  ? "Network Connection Issue"
                  : isCamera && isMic
                  ? "Camera & Microphone Access Required"
                  : isCamera
                  ? "Camera Access Denied"
                  : "Microphone Access Denied"}
              </DialogTitle>
              <DialogDescription className="text-xs text-text-muted mt-0.5">
                {isNetwork
                  ? "Unable to establish low-latency connection with the interview server."
                  : "Your browser or operating system has blocked device access for this session."}
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {isNetwork ? (
          <div className="space-y-3 py-2 text-sm text-text-muted">
            <div className="p-3.5 rounded-lg bg-surface-muted border border-border space-y-2">
              <p className="font-medium text-text-primary text-xs">
                To participate in adaptive voice interviews:
              </p>
              <ul className="list-disc pl-4 space-y-1 text-xs text-text-muted">
                <li>Ensure you are connected to a stable Wi-Fi or wired connection.</li>
                <li>Disable active VPNs, proxies, or ad-blocking extensions that may block WebRTC or API pings.</li>
                <li>Check your firewall settings to allow outbound HTTPS/WSS traffic.</li>
              </ul>
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-1">
            {/* Browser Selector Tabs */}
            <div className="flex rounded-lg bg-surface-muted p-1 border border-border">
              {(
                [
                  { id: "chrome", label: "Google Chrome / Brave" },
                  { id: "safari", label: "Apple Safari" },
                  { id: "firefox", label: "Mozilla Firefox / Edge" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setSelectedBrowser(tab.id)}
                  className={cn(
                    "flex-1 text-xs py-1.5 font-medium rounded-md transition-all cursor-pointer",
                    selectedBrowser === tab.id
                      ? "bg-surface text-brand font-semibold shadow-2xs border border-border"
                      : "text-text-muted hover:text-text-primary"
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Step-by-step instructions */}
            <div className="p-3.5 rounded-lg bg-surface-muted border border-border space-y-2.5 text-xs text-text-muted">
              {selectedBrowser === "chrome" && (
                <ol className="list-decimal pl-4 space-y-1.5 leading-relaxed">
                  <li>
                    Look at the left side of your browser address bar and click the{" "}
                    <span className="font-semibold text-text-primary">tune / lock icon</span>.
                  </li>
                  <li>
                    Ensure{" "}
                    {isCamera && <span className="font-medium text-text-primary">Camera</span>}
                    {isCamera && isMic && " and "}
                    {isMic && <span className="font-medium text-text-primary">Microphone</span>} are set to{" "}
                    <span className="font-semibold text-success">Allow</span>.
                  </li>
                  <li>
                    If toggles are grayed out, open{" "}
                    <span className="font-semibold text-text-primary">Site settings</span> and reset permissions.
                  </li>
                </ol>
              )}

              {selectedBrowser === "safari" && (
                <ol className="list-decimal pl-4 space-y-1.5 leading-relaxed">
                  <li>
                    In the top menu bar, click{" "}
                    <span className="font-semibold text-text-primary">Safari</span> &gt;{" "}
                    <span className="font-semibold text-text-primary">Settings for This Website</span>.
                  </li>
                  <li>
                    Find{" "}
                    {isCamera && <span className="font-medium text-text-primary">Camera</span>}
                    {isCamera && isMic && " & "}
                    {isMic && <span className="font-medium text-text-primary">Microphone</span>} and select{" "}
                    <span className="font-semibold text-success">Allow</span>.
                  </li>
                  <li>
                    On macOS, also check <span className="font-semibold text-text-primary">System Settings &gt; Privacy & Security</span> to verify Safari has OS-level permission.
                  </li>
                </ol>
              )}

              {selectedBrowser === "firefox" && (
                <ol className="list-decimal pl-4 space-y-1.5 leading-relaxed">
                  <li>
                    Click the <span className="font-semibold text-text-primary">camera / shield icon</span> next to the address bar URL.
                  </li>
                  <li>
                    Clear any blocked permissions for Camera or Microphone by clicking the &ldquo;X&rdquo; next to &ldquo;Blocked Temporarily&rdquo;.
                  </li>
                  <li>
                    Click the &ldquo;Retry Check&rdquo; button below to prompt for access again.
                  </li>
                </ol>
              )}
            </div>

            {/* Note about OS permissions */}
            <div className="flex items-start gap-2 text-[11px] text-text-muted bg-warning-light/40 border border-warning/30 p-2.5 rounded-lg">
              <AlertTriangle className="h-4 w-4 text-warning shrink-0 mt-0.5" />
              <span>
                Operating system permissions: If permissions are already allowed in your browser, check your operating system (macOS or Windows) privacy settings to ensure your browser is permitted to access the camera and microphone.
              </span>
            </div>
          </div>
        )}

        <DialogFooter className="flex-col sm:flex-row gap-2 mt-4">
          <Button asChild variant="secondary" size="sm" className="w-full sm:w-auto">
            <Link href="/portal" className="flex items-center justify-center gap-1.5">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to Portal
            </Link>
          </Button>
          <Button
            onClick={() => {
              onRetry();
              onOpenChange(false);
            }}
            size="sm"
            className="w-full sm:w-auto flex items-center justify-center gap-1.5 bg-brand hover:bg-brand-hover text-white"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry Hardware Check
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
