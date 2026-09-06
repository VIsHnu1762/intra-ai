"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowLeft, GraduationCap, ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useMyApplications } from "@/hooks/queries/useCandidates";
import { useVoiceAssistant } from "@/hooks/use-voice-assistant";
import { VoiceAssistantPanel } from "@/components/voice/voice-assistant-panel";
import { TaylorPracticeFeedbackPanel } from "@/components/voice/taylor-practice-feedback";
import { voiceAssistantsApi } from "@/lib/api/voice-assistants";
import { practiceOptions, type PracticeExperience, type TaylorPracticeFeedback } from "@/lib/taylor-practice";

function TaylorTraining() {
  const assistant = useVoiceAssistant("taylor");
  const [applicationId, setApplicationId] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [experienceLevel, setExperienceLevel] = useState<PracticeExperience>("intern");
  const [feedback, setFeedback] = useState<TaylorPracticeFeedback | null>(null);
  const feedbackSession = useRef<string | null>(null);
  const feedbackRequest = useRef(false);
  const feedbackPolls = useRef(0);
  const feedbackView = useRef<HTMLDivElement>(null);
  const mounted = useRef(true);
  const { data, isLoading, isError } = useMyApplications();
  const applications = data?.applications || [];
  const selectedApplication = applications.find(application => application.id === applicationId);
  const appliedRole = selectedApplication?.job?.title || selectedApplication?.jobs?.title || selectedApplication?.current_role;
  const preparingFeedback = feedback?.status === "requesting_feedback";
  const setupDisabled = assistant.connection.active || preparingFeedback;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (preparingFeedback) feedbackView.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }, [preparingFeedback]);

  const finish = async () => {
    const id = assistant.sessionId;
    if (feedbackRequest.current) return;
    if (!id) { await assistant.end(); return; }
    feedbackRequest.current = true;
    feedbackSession.current = id;
    feedbackPolls.current = 0;
    setFeedback({ status: "requesting_feedback" });
    const result = await assistant.finishPractice();
    if (mounted.current) setFeedback(result || { status: "unavailable", indicative_score: null, message: "This session could not be finished. Use Check Saved Feedback to check for saved feedback." });
    feedbackRequest.current = false;
  };
  const closePractice = assistant.end;
  const retryFeedback = useCallback(async () => {
    const id = feedbackSession.current;
    if (!id || feedbackRequest.current) return;
    feedbackRequest.current = true;
    setFeedback({ status: "requesting_feedback" });
    try {
      const saved = await voiceAssistantsApi.practiceFeedback(id);
      if (saved.status !== "requesting_feedback") await closePractice();
      if (mounted.current && feedbackSession.current === id) {
        if (saved.status === "requesting_feedback" && ++feedbackPolls.current >= 15) {
          feedbackPolls.current = 0;
          setFeedback({ status: "unavailable", indicative_score: null, message: "Feedback is still being prepared. Try checking the saved result again shortly." });
        } else setFeedback(saved);
      }
    } catch {
      if (mounted.current && feedbackSession.current === id) setFeedback({ status: "unavailable", indicative_score: null, message: "Saved feedback could not be retrieved. No new assessment was requested." });
    } finally { feedbackRequest.current = false; }
  }, [closePractice]);
  // A feedback request can survive a lost response. Poll only the saved result;
  // never re-run generation or create additional assessments automatically.
  useEffect(() => {
    if (!preparingFeedback || !feedbackSession.current) return;
    const timer = setInterval(() => { if (!feedbackRequest.current) void retryFeedback(); }, 4000);
    return () => clearInterval(timer);
  }, [preparingFeedback, retryFeedback]);

  const start = () => {
    if (feedbackRequest.current || preparingFeedback) return;
    feedbackSession.current = null;
    setFeedback(null);
    void assistant.start(selectedApplication ? { application_id: selectedApplication.id, job_id: selectedApplication.job_id } : {}, practiceOptions(targetRole, experienceLevel, appliedRole));
  };

  return <div className="mx-auto max-w-3xl">
    <Link href="/portal" className="mb-6 inline-flex items-center gap-2 text-sm text-brand hover:underline"><ArrowLeft className="h-4 w-4" />Back to My Applications</Link>
    <div className="mb-6"><div className="inline-flex items-center gap-2 rounded-full bg-brand-light px-3 py-1 text-xs font-semibold text-brand mb-3"><GraduationCap className="h-4 w-4" />AI Interview Training</div><h1 className="text-3xl font-bold text-text-primary">Practice with Taylor</h1><p className="mt-2 text-text-muted">Practice clear, focused questions at your level, then get feedback on how to improve your answers.</p></div>
    <div className="mb-6 flex gap-3 rounded-xl bg-brand-light p-4 border border-brand/20"><ShieldCheck className="h-5 w-5 text-brand shrink-0" /><p className="text-sm text-text-primary">This is a practice session. Feedback and indicative practice scores do not affect your official interview score or application status.</p></div>
    <section className="rounded-2xl border border-border bg-surface p-5 sm:p-8 shadow-sm" aria-label="Taylor training room">
      <div className="mb-6 space-y-4">
        <div><label htmlFor="training-application" className="block text-sm font-medium text-text-primary mb-2">Practice for an application</label><select id="training-application" value={applicationId} onChange={event => setApplicationId(event.target.value)} disabled={setupDisabled || isLoading} className="w-full rounded-xl border border-border bg-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand disabled:opacity-60"><option value="">General interview practice</option>{applications.map(application => <option key={application.id} value={application.id}>{application.job?.title || application.jobs?.title || application.current_role || "Applied role"}</option>)}</select><p className="mt-2 text-xs text-text-muted">{isError ? "Your applications could not be loaded. You can still start general practice." : "Optional. Select an application to use its job description as background."}</p></div>
        <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="training-target-role" className="block text-sm font-medium text-text-primary mb-2">Target role</label><input id="training-target-role" value={targetRole} onChange={event => setTargetRole(event.target.value)} disabled={setupDisabled} maxLength={160} placeholder={appliedRole || "e.g. Software developer intern"} className="w-full rounded-xl border border-border bg-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand disabled:opacity-60" /><p className="mt-1.5 text-xs text-text-muted">{appliedRole ? "Leave blank to use your selected job title." : "Optional. Tell Taylor the role you want to practice for."}</p></div><div><label htmlFor="training-experience-level" className="block text-sm font-medium text-text-primary mb-2">Experience level</label><select id="training-experience-level" value={experienceLevel} onChange={event => setExperienceLevel(event.target.value as PracticeExperience)} disabled={setupDisabled} className="w-full rounded-xl border border-border bg-bg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-brand disabled:opacity-60"><option value="intern">Intern / first role</option><option value="junior">Junior</option><option value="mid">Mid-level</option><option value="senior">Senior</option></select><p className="mt-1.5 text-xs text-text-muted">Choose the level you want to practice at.</p></div></div>
        <p className="text-xs leading-relaxed text-text-muted">Taylor can use your saved CV as background. Answer a few questions, then choose Finish &amp; Get Feedback. Use headphones for clearer audio.</p>
      </div>
      <VoiceAssistantPanel assistant={assistant} name="Taylor" onStart={start} onEnd={() => void finish()} endLabel="Finish & Get Feedback" startDisabled={preparingFeedback} />
    </section>
    {feedback && <div ref={feedbackView} className="scroll-mt-20"><TaylorPracticeFeedbackPanel feedback={feedback} onRetry={() => void retryFeedback()} /></div>}
  </div>;
}

export default function TrainingPage() {
  const { isAuthenticated, isLoading, role, user } = useAuth();
  if (isLoading) return <p className="text-sm text-text-muted">Checking your account…</p>;
  if (!isAuthenticated) return <p className="text-sm text-text-muted">Sign in to your candidate account to train with Taylor.</p>;
  if ((role || user?.role) !== "candidate") return <div className="rounded-xl border border-border p-6"><h1 className="font-semibold">Candidate training</h1><p className="mt-2 text-sm text-text-muted">Sign in with a candidate account to practice with Taylor.</p><Link href="/admin/dashboard" className="inline-block mt-3 text-sm text-brand">Back to dashboard</Link></div>;
  return <TaylorTraining />;
}
