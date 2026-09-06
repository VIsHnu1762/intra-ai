"use client";

import { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api/client";

export function ResumeDownloadButton({ applicationId, resumeUrl, label = "Download CV" }: {
  applicationId: string; resumeUrl: string; label?: string;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const download = async () => {
    setError(null);
    setBusy(true);
    try {
      // Construct the private path from the application identity. Never attach
      // a bearer token to a URL supplied by a resume record or external host.
      const extension = resumeUrl.match(/\/resume\/(pdf|docx?|txt|rtf)$/i)?.[1]?.toLowerCase();
      if (!extension) {
        const legacy = new URL(resumeUrl);
        if (!["https:", "http:"].includes(legacy.protocol)) throw new Error("Unsupported CV link");
        window.open(legacy.href, "_blank", "noopener,noreferrer");
        return;
      }
      const blob = await apiClient<Blob>(
        `/api/v1/applications/${encodeURIComponent(applicationId)}/resume/${extension}`,
        { responseType: "blob", headers: { Accept: "application/octet-stream" } },
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `CV.${extension}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download your CV. Please retry.");
    } finally {
      setBusy(false);
    }
  };

  return <div className="flex flex-col items-start gap-1">
    <Button variant="secondary" size="sm" disabled={busy} onClick={download}>
      {busy ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Download className="h-4 w-4 mr-1.5" />}
      {busy ? "Downloading…" : label}
    </Button>
    {error && <span role="alert" className="text-xs text-error max-w-64">{error}</span>}
  </div>;
}
