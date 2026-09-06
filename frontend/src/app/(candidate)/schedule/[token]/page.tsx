"use client";

import { useState, useMemo, use, useEffect } from "react";
import Link from "next/link";
import {
  Clock,
  Calendar,
  Video,
  Layers,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ArrowRight,
  RefreshCw,
  Globe,
  ShieldAlert,
} from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useApplication } from "@/hooks/queries/useApplications";
import { useInterviewSlots, useBookInterviewSlot } from "@/hooks/queries/useScheduling";
import { decodeAuthToken } from "@/lib/auth/token-storage";
import type { BackendInterviewSlotResponse, BackendScheduledInterviewResponse } from "@/types/api";

const SUPPORTED_TIMEZONES = [
  { value: "Asia/Kolkata", label: "India Standard Time (IST · UTC+5:30)" },
  { value: "UTC", label: "Coordinated Universal Time (UTC)" },
  { value: "America/New_York", label: "US Eastern (EST/EDT · New York)" },
  { value: "America/Chicago", label: "US Central (CST/CDT · Chicago)" },
  { value: "America/Los_Angeles", label: "US Pacific (PST/PDT · San Francisco)" },
  { value: "Europe/London", label: "UK / London (GMT/BST)" },
  { value: "Europe/Berlin", label: "Central European Time (CET · Berlin/Paris)" },
  { value: "Asia/Singapore", label: "Singapore Time (SGT · UTC+8)" },
  { value: "Asia/Tokyo", label: "Japan Standard Time (JST · Tokyo)" },
  { value: "Australia/Sydney", label: "Australian Eastern (AEST · Sydney)" },
];

/**
 * Parses UTC slot date & time into a Date object.
 */
function parseSlotUtcDate(dateStr: string, timeStr: string): Date {
  const [year, month, day] = dateStr.split("-").map(Number);
  const [hour, minute] = timeStr.split(":").map(Number);
  return new Date(Date.UTC(year, month - 1, day, hour, minute, 0));
}

/**
 * Formats a Date object in the target timezone for day grouping.
 */
function getLocalDateKey(d: Date, timeZone: string): string {
  try {
    const formatter = new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    return formatter.format(d); // Returns YYYY-MM-DD
  } catch {
    return d.toISOString().split("T")[0];
  }
}

/**
 * Formats a Date object in the target timezone for human display.
 */
function formatLocalDateDisplay(dateKey: string, timeZone: string): {
  weekday: string;
  day: string;
  month: string;
  full: string;
} {
  try {
    const [year, month, day] = dateKey.split("-").map(Number);
    // Anchor in noon UTC of that date to format cleanly
    const d = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
    const weekday = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone }).format(d);
    const dayStr = new Intl.DateTimeFormat("en-US", { day: "numeric", timeZone }).format(d);
    const monthStr = new Intl.DateTimeFormat("en-US", { month: "short", timeZone }).format(d);
    const full = new Intl.DateTimeFormat("en-US", {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone,
    }).format(d);
    return { weekday, day: dayStr, month: monthStr, full };
  } catch {
    return { weekday: "Day", day: dateKey, month: "", full: dateKey };
  }
}

/**
 * Formats a time string in the target timezone.
 */
function formatSlotTimeInTimezone(d: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
      timeZone,
    }).format(d);
  } catch {
    return d.toISOString().slice(11, 16);
  }
}

export default function SchedulePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token: applicationId } = use(params);

  // Timezone selection with browser detection default
  const [selectedTimeZone, setSelectedTimeZone] = useState<string>("UTC");
  useEffect(() => {
    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (detected) setSelectedTimeZone(detected);
    } catch {
      setSelectedTimeZone("UTC");
    }
  }, []);

  const {
    data: application,
    isLoading: appLoading,
    isError: appError,
    error: appErr,
    refetch: refetchApp,
  } = useApplication(applicationId);

  const jobId = application?.job_id ?? "";
  const {
    data: slots = [],
    isLoading: slotsLoading,
    refetch: refetchSlots,
  } = useInterviewSlots(jobId, { enabled: Boolean(jobId) });

  const bookMutation = useBookInterviewSlot();

  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [confirmedBooking, setConfirmedBooking] = useState<BackendScheduledInterviewResponse | null>(null);
  const [bookingError, setBookingError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Candidate Ownership Verification (P5-015)
  const isUnauthorized = useMemo(() => {
    if (!application?.candidate?.email) return false;
    const tokenPayload = decodeAuthToken();
    if (!tokenPayload) return false;
    // Admins and recruiters are allowed to view any candidate's link
    if (tokenPayload.role === "admin" || tokenPayload.role === "recruiter") {
      return false;
    }
    const candidateEmail = application.candidate.email.trim().toLowerCase();
    const tokenSub = (tokenPayload.sub || "").trim().toLowerCase();
    const tokenEmail = ((tokenPayload.email as string) || "").trim().toLowerCase();
    return tokenEmail !== candidateEmail && tokenSub !== candidateEmail;
  }, [application]);

  // Group unbooked slots localized to the selected timezone
  const localizedSlotsByDate = useMemo(() => {
    const map: Record<
      string,
      Array<{
        rawSlot: BackendInterviewSlotResponse;
        startDate: Date;
        endDate: Date;
        formattedStart: string;
        formattedEnd: string;
      }>
    > = {};

    for (const slot of slots) {
      if (!slot.is_booked) {
        const startUtc = parseSlotUtcDate(slot.date, slot.start_time);
        const endUtc = parseSlotUtcDate(slot.date, slot.end_time);
        const dateKey = getLocalDateKey(startUtc, selectedTimeZone);

        if (!map[dateKey]) {
          map[dateKey] = [];
        }

        map[dateKey].push({
          rawSlot: slot,
          startDate: startUtc,
          endDate: endUtc,
          formattedStart: formatSlotTimeInTimezone(startUtc, selectedTimeZone),
          formattedEnd: formatSlotTimeInTimezone(endUtc, selectedTimeZone),
        });
      }
    }

    // Sort slots within each date chronologically
    for (const d in map) {
      map[d].sort((a, b) => a.startDate.getTime() - b.startDate.getTime());
    }

    return map;
  }, [slots, selectedTimeZone]);

  const uniqueDateKeys = useMemo(
    () => Object.keys(localizedSlotsByDate).sort(),
    [localizedSlotsByDate]
  );

  // If selectedDateKey is not yet chosen or not in available dates, default to first available
  const activeDateKey =
    selectedDateKey && localizedSlotsByDate[selectedDateKey]
      ? selectedDateKey
      : uniqueDateKeys.length > 0
      ? uniqueDateKeys[0]
      : null;

  const availableSlotsForDate = activeDateKey ? localizedSlotsByDate[activeDateKey] ?? [] : [];

  const handleDaySelect = (dateKey: string) => {
    setSelectedDateKey(dateKey);
    setSelectedSlotId(null);
    setBookingError(null);
  };

  // P5-002 / P5-003: Confirm booking with double-click debounce and 409 conflict handling
  const handleConfirm = async () => {
    if (!selectedSlotId || isSubmitting || bookMutation.isPending) return;
    setIsSubmitting(true);
    setBookingError(null);

    try {
      const result = await bookMutation.mutateAsync({
        applicationId,
        slotId: selectedSlotId,
      });
      setConfirmedBooking(result);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to book interview slot";
      // P5-002: Stale Slot Defensive Handling & 409 Conflict Toast
      if (message.toLowerCase().includes("already booked") || message.includes("409")) {
        setBookingError("This slot was just booked by another candidate. Please select another available time slot.");
        setSelectedSlotId(null);
        // Refresh slots from server to remove the stale slot
        refetchSlots();
      } else {
        setBookingError(message);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // ─── Loading State ───
  if (appLoading) {
    return (
      <div className="max-w-3xl mx-auto py-16 flex flex-col items-center justify-center">
        <Loader2 className="h-8 w-8 text-brand animate-spin mb-3" />
        <p className="text-sm text-text-muted">Loading application details...</p>
      </div>
    );
  }

  // ─── Unauthorized Cross-Candidate Access Guard (P5-015) ───
  if (isUnauthorized) {
    return (
      <div className="max-w-lg mx-auto py-16 text-center">
        <div className="h-16 w-16 rounded-full bg-error-light text-error flex items-center justify-center mx-auto mb-4">
          <ShieldAlert className="h-8 w-8" />
        </div>
        <h2 className="text-xl font-bold text-text-primary mb-2">
          Access Restricted
        </h2>
        <p className="text-sm text-text-muted mb-6">
          This interview invitation is associated with a different candidate account. Please sign in with the invited email address to proceed.
        </p>
        <Button asChild>
          <Link href="/portal">Back to My Portal</Link>
        </Button>
      </div>
    );
  }

  // ─── Application Error State ───
  if (appError || !application) {
    const recruiterManagedSchedule = appErr?.message?.toLowerCase().includes("not authorized");
    return (
      <div className="max-w-lg mx-auto py-16 text-center">
        <div className="h-14 w-14 rounded-full bg-error-light text-error flex items-center justify-center mx-auto mb-4">
          <AlertCircle className="h-7 w-7" />
        </div>
        <h2 className="text-xl font-bold text-text-primary mb-2">
          {recruiterManagedSchedule ? "Recruiter Scheduling" : "Unable to Load Application"}
        </h2>
        <p className="text-sm text-text-muted mb-6">
          {recruiterManagedSchedule
            ? "The hiring team selects and reschedules interview times. Your candidate portal will show the confirmed time once it is scheduled."
            : appErr?.message || "The interview invitation link could not be verified or has expired."}
        </p>
        <div className="flex gap-3 justify-center">
          <Button variant="secondary" onClick={() => refetchApp()}>
            <RefreshCw className="h-4 w-4 mr-1.5" />
            Retry
          </Button>
          <Button asChild>
            <Link href="/portal">Go to Portal</Link>
          </Button>
        </div>
      </div>
    );
  }

  // ─── Already Scheduled State (P5-004) ───
  if (application.status === "scheduled" && !confirmedBooking) {
    const interviewId = application.interview_id || application.id;
    const scheduledDateObj = application.scheduled_at
      ? new Date(application.scheduled_at)
      : null;

    return (
      <div className="max-w-lg mx-auto py-12 text-center">
        <div className="h-16 w-16 rounded-full bg-success-light text-success flex items-center justify-center mx-auto mb-4">
          <CheckCircle2 className="h-8 w-8" />
        </div>
        <h2 className="text-2xl font-bold text-text-primary mb-2">
          Interview Already Confirmed
        </h2>
        <p className="text-sm text-text-muted mb-6">
          Your interview session for{" "}
          <span className="font-semibold text-text-primary">
            {application.job?.title || "this position"}
          </span>{" "}
          has been scheduled.
        </p>

        {scheduledDateObj && (
          <Card className="mb-6 text-left border-brand/20 bg-surface">
            <CardContent className="p-4 space-y-2.5">
              <div className="flex items-center gap-3">
                <Calendar className="h-4 w-4 text-brand shrink-0" />
                <span className="text-sm font-medium text-text-primary">
                  {formatLocalDateDisplay(getLocalDateKey(scheduledDateObj, selectedTimeZone), selectedTimeZone).full}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-brand shrink-0" />
                <span className="text-sm font-medium text-text-primary">
                  {formatSlotTimeInTimezone(scheduledDateObj, selectedTimeZone)} ({selectedTimeZone})
                </span>
              </div>
            </CardContent>
          </Card>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button asChild size="lg" className="bg-brand hover:bg-brand-hover text-white">
            <Link href={`/interview/${interviewId}/prep`} className="flex items-center gap-2">
              Proceed to System Check
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/portal">Candidate Portal</Link>
          </Button>
        </div>
      </div>
    );
  }

  // ─── Confirmation Success Screen ───
  if (confirmedBooking) {
    const jobTitle = confirmedBooking.job?.title || application.job?.title || "Role";
    const company = "Intra AI Hiring Team";
    const duration = confirmedBooking.duration_minutes || 60;
    const interviewId = confirmedBooking.id;
    const bookingDate = new Date(confirmedBooking.scheduled_at);

    return (
      <div className="max-w-lg mx-auto text-center py-12">
        <div className="flex justify-center mb-6">
          <div className="h-20 w-20 rounded-full bg-success-light flex items-center justify-center">
            <CheckCircle2 className="h-10 w-10 text-success" />
          </div>
        </div>
        <h1 className="text-2xl font-bold text-text-primary mb-2">
          Interview Confirmed!
        </h1>
        <p className="text-sm text-text-muted mb-6">
          Your interview for{" "}
          <span className="font-semibold text-text-primary">{jobTitle}</span>{" "}
          with {company} has been scheduled successfully.
        </p>

        <Card className="mb-6 text-left border-brand/20 bg-surface">
          <CardContent className="p-5 space-y-3">
            <div className="flex items-center gap-3">
              <Calendar className="h-4 w-4 text-brand shrink-0" />
              <span className="text-sm font-medium text-text-primary">
                {formatLocalDateDisplay(getLocalDateKey(bookingDate, selectedTimeZone), selectedTimeZone).full}
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Clock className="h-4 w-4 text-brand shrink-0" />
              <span className="text-sm font-medium text-text-primary">
                {formatSlotTimeInTimezone(bookingDate, selectedTimeZone)} ({selectedTimeZone}) · ~{duration} minutes
              </span>
            </div>
            <div className="flex items-center gap-3">
              <Video className="h-4 w-4 text-brand shrink-0" />
              <span className="text-sm text-text-muted">
                Intra AI Multi-Agent Adaptive Voice Interview
              </span>
            </div>
          </CardContent>
        </Card>

        <p className="text-xs text-text-muted mb-6">
          Please complete your camera, microphone, and network check in advance of the live session.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Button asChild size="lg" className="bg-brand hover:bg-brand-hover text-white">
            <Link href={`/interview/${interviewId}/prep`} className="flex items-center gap-2">
              Proceed to System Check
              <ArrowRight className="h-4 w-4" />
            </Link>
          </Button>
          <Button asChild variant="secondary" size="lg">
            <Link href="/portal">Candidate Portal</Link>
          </Button>
        </div>
      </div>
    );
  }

  const job = application.job;
  const jobTitle = job?.title || "Interview Session";
  const department = job?.department || "Engineering";
  const location = job?.location || "Remote";
  const rounds = job?.interview_rounds || [];
  const totalDuration = rounds.length > 0
    ? rounds.reduce((sum, r) => sum + (r.duration_minutes || 15), 0)
    : 60;

  const selectedSlotWrapper = availableSlotsForDate.find((s) => s.rawSlot.id === selectedSlotId);

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-0 py-4">
      {/* Header & Timezone selector */}
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">
            Schedule Your Interview
          </h1>
          <p className="text-sm text-text-muted mt-1">
            Select an available time slot for your adaptive voice interview session
          </p>
        </div>

        {/* P5-001: Timezone Selector Dropdown */}
        <div className="flex items-center gap-2 bg-surface border border-border rounded-lg px-3 py-1.5 shadow-2xs">
          <Globe className="h-4 w-4 text-brand shrink-0" />
          <div className="flex flex-col">
            <span className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">Timezone</span>
            <select
              value={selectedTimeZone}
              onChange={(e) => {
                setSelectedTimeZone(e.target.value);
                setSelectedSlotId(null);
              }}
              className="bg-transparent text-xs font-medium text-text-primary focus:outline-none cursor-pointer pr-1"
            >
              {SUPPORTED_TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value} className="bg-surface text-text-primary">
                  {tz.label}
                </option>
              ))}
              {!SUPPORTED_TIMEZONES.some((tz) => tz.value === selectedTimeZone) && (
                <option value={selectedTimeZone} className="bg-surface text-text-primary">
                  {selectedTimeZone} (Local)
                </option>
              )}
            </select>
          </div>
        </div>
      </div>

      {/* Booking Error / 409 Conflict Banner (P5-002) */}
      {bookingError && (
        <div className="mb-6 p-4 rounded-xl border border-error/30 bg-error-light flex items-center justify-between text-sm text-error">
          <div className="flex items-center gap-2.5">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span className="font-medium">{bookingError}</span>
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setBookingError(null)}
            className="border-error/30 text-error hover:bg-error-light shrink-0 ml-3"
          >
            Dismiss
          </Button>
        </div>
      )}

      {/* Job info card */}
      <Card className="mb-6">
        <CardContent className="p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-base font-semibold text-text-primary">
                {jobTitle}
              </h2>
              <p className="text-sm text-text-muted mt-0.5">
                {department} · {location}
              </p>
            </div>
            <div className="flex flex-col items-end gap-1.5 shrink-0">
              <div className="flex items-center gap-1.5 text-xs text-text-muted">
                <Clock className="h-3.5 w-3.5" />
                {totalDuration} min total
              </div>
              {rounds.length > 0 && (
                <div className="flex items-center gap-1.5 text-xs text-text-muted">
                  <Layers className="h-3.5 w-3.5" />
                  {rounds.length} rounds
                </div>
              )}
            </div>
          </div>

          {/* Round breakdown */}
          {rounds.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {rounds.map((r, i) => (
                <span
                  key={r.id || i}
                  className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium bg-brand-light text-brand border border-brand/20"
                >
                  Round {i + 1}: {r.type.replace("_", " ")} · {r.duration_minutes}m
                </span>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {slotsLoading ? (
        <Card className="p-8 text-center animate-pulse">
          <Loader2 className="h-6 w-6 text-brand animate-spin mx-auto mb-2" />
          <p className="text-sm text-text-muted">Fetching open interview slots in {selectedTimeZone}...</p>
        </Card>
      ) : uniqueDateKeys.length === 0 ? (
        <Card className="p-8 text-center">
          <div className="h-12 w-12 rounded-full bg-warning-light text-warning flex items-center justify-center mx-auto mb-3">
            <Calendar className="h-6 w-6" />
          </div>
          <h3 className="text-base font-semibold text-text-primary mb-1">
            No Slots Available
          </h3>
          <p className="text-sm text-text-muted max-w-md mx-auto mb-4">
            There are currently no open interview slots for this position. The hiring team has been notified to add interview windows.
          </p>
          <Button variant="secondary" onClick={() => refetchSlots()}>
            <RefreshCw className="h-3.5 w-3.5 mr-1.5" />
            Check Again
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-5">
          {/* Left: Date selector */}
          <div className="lg:col-span-3 space-y-5">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center justify-between text-base">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4 text-brand" />
                    Select Date
                  </div>
                  <span className="text-xs font-normal text-text-muted">
                    Times shown in {selectedTimeZone}
                  </span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-3 sm:grid-cols-4 gap-2">
                  {uniqueDateKeys.map((dateKey) => {
                    const isSelected = activeDateKey === dateKey;
                    const dateInfo = formatLocalDateDisplay(dateKey, selectedTimeZone);
                    const count = localizedSlotsByDate[dateKey]?.length ?? 0;

                    return (
                      <button
                        key={dateKey}
                        onClick={() => handleDaySelect(dateKey)}
                        className={cn(
                          "flex flex-col items-center p-3 rounded-lg border text-center transition-all cursor-pointer",
                          isSelected
                            ? "border-brand bg-brand text-white shadow-xs"
                            : "border-border bg-surface hover:border-brand/40 hover:bg-brand-light/20"
                        )}
                      >
                        <span
                          className={cn(
                            "text-[10px] font-semibold uppercase tracking-wider",
                            isSelected ? "text-white/80" : "text-text-muted"
                          )}
                        >
                          {dateInfo.weekday}
                        </span>
                        <span
                          className={cn(
                            "text-base font-bold my-0.5",
                            isSelected ? "text-white" : "text-text-primary"
                          )}
                        >
                          {dateInfo.day}
                        </span>
                        <span
                          className={cn(
                            "text-[10px]",
                            isSelected ? "text-white/70" : "text-text-muted"
                          )}
                        >
                          {dateInfo.month} · {count} {count === 1 ? "slot" : "slots"}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </CardContent>
            </Card>

            {/* Time slots */}
            {activeDateKey && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Clock className="h-4 w-4 text-brand" />
                    Available Times — {formatLocalDateDisplay(activeDateKey, selectedTimeZone).full}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {availableSlotsForDate.length === 0 ? (
                    <p className="text-sm text-text-muted py-3 text-center">
                      No open slots on this date.
                    </p>
                  ) : (
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {availableSlotsForDate.map((wrapper) => {
                        const isSelected = selectedSlotId === wrapper.rawSlot.id;
                        return (
                          <button
                            key={wrapper.rawSlot.id}
                            onClick={() => setSelectedSlotId(wrapper.rawSlot.id)}
                            className={cn(
                              "px-3 py-2.5 rounded-lg border text-sm font-medium transition-all cursor-pointer text-center",
                              isSelected
                                ? "border-brand bg-brand text-white shadow-xs font-semibold"
                                : "border-border bg-surface hover:border-brand/40 hover:bg-brand-light/20 text-text-primary"
                            )}
                          >
                            {wrapper.formattedStart}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>

          {/* Right: Summary + Confirm */}
          <div className="lg:col-span-2">
            <Card className="sticky top-20">
              <CardHeader>
                <CardTitle className="text-base">Booking Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-xs text-text-muted">Selected Role</p>
                  <p className="text-sm font-medium text-text-primary mt-0.5">
                    {jobTitle}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-text-muted">Date</p>
                  <p className="text-sm font-medium text-text-primary mt-0.5">
                    {activeDateKey
                      ? formatLocalDateDisplay(activeDateKey, selectedTimeZone).full
                      : "None selected"}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-text-muted">Time</p>
                  <p className="text-sm font-medium text-text-primary mt-0.5">
                    {selectedSlotWrapper
                      ? `${selectedSlotWrapper.formattedStart} (${selectedTimeZone})`
                      : "None selected"}
                  </p>
                </div>

                <div>
                  <p className="text-xs text-text-muted">Duration</p>
                  <p className="text-sm font-medium text-text-primary mt-0.5">
                    ~{totalDuration} minutes
                  </p>
                </div>

                <div className="pt-2">
                  <Button
                    onClick={handleConfirm}
                    disabled={!selectedSlotId || isSubmitting || bookMutation.isPending}
                    size="lg"
                    className="w-full bg-brand hover:bg-brand-hover text-white cursor-pointer disabled:cursor-not-allowed"
                  >
                    {isSubmitting || bookMutation.isPending ? (
                      <span className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Confirming Interview...
                      </span>
                    ) : (
                      "Confirm Interview"
                    )}
                  </Button>
                </div>

                <p className="text-[11px] text-text-muted text-center leading-tight">
                  By confirming, you reserve this time slot for your multi-agent AI interview.
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
