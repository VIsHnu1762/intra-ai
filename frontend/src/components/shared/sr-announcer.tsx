"use client";

import * as React from "react";

export interface ScreenReaderAnnouncerProps {
  message?: string;
  politeness?: "polite" | "assertive";
}

/**
 * ScreenReaderAnnouncer
 * Visually hidden ARIA live region that announces agent state transitions and AI speech
 * to screen readers (VoiceOver, NVDA, JAWS).
 */
export function ScreenReaderAnnouncer({
  message,
  politeness = "polite",
}: ScreenReaderAnnouncerProps) {
  const [announcement, setAnnouncement] = React.useState(message ?? "");

  React.useEffect(() => {
    if (message) {
      setAnnouncement(message);
    }
  }, [message]);

  return (
    <div
      role="status"
      aria-live={politeness}
      aria-atomic="true"
      className="sr-only"
    >
      {announcement}
    </div>
  );
}
