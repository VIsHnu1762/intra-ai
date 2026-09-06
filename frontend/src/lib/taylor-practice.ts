export type PracticeExperience = "intern" | "junior" | "mid" | "senior";
export type TaylorPracticeOptions = {
  target_role?: string;
  experience_level: PracticeExperience;
};
export type TaylorPracticeFeedback = {
  status: "requesting_feedback" | "ready" | "insufficient_evidence" | "unavailable";
  indicative_score?: number | null;
  summary?: string;
  areas_to_improve?: string[];
  better_answers?: Array<{ question: string; example: string; explanation?: string; answer_excerpt?: string; example_kind?: "template" | "suggested_answer" }>;
  message?: string;
  answered_questions?: number;
  reviewed_answers?: number;
  strengths?: string[];
  criteria?: Array<{ name: string; score: number; reason: string }>;
};

/** Never turn missing or invalid feedback into a candidate score. */
export function practiceScore(feedback: TaylorPracticeFeedback): number | null {
  const score = feedback.indicative_score;
  return feedback.status === "ready" && typeof score === "number" && Number.isFinite(score) && score >= 0 && score <= 100 ? Math.round(score) : null;
}

export function practiceOptions(targetRole: string, experienceLevel: PracticeExperience, appliedRole?: string | null): TaylorPracticeOptions {
  const role = targetRole.trim() || appliedRole?.trim();
  return { experience_level: experienceLevel, ...(role ? { target_role: role.slice(0, 160) } : {}) };
}

/** An observed browser proxy, not actual end-of-speech or model processing time. */
export function createPracticeLatencyTracker() {
  const finalTurns = new Set<string>();
  let waitingSince: number | null = null;
  let wasSpeaking = false;
  return {
    finalUserTranscript(turnId: string, at: number) {
      if (finalTurns.has(turnId)) return;
      finalTurns.add(turnId);
      while (finalTurns.size > 80) finalTurns.delete(finalTurns.values().next().value!);
      waitingSince = at;
    },
    remoteAudio(speaking: boolean, at: number): number | null {
      const started = speaking && !wasSpeaking;
      wasSpeaking = speaking;
      if (!started || waitingSince === null) return null;
      const latency = Math.max(0, Math.round(at - waitingSince));
      waitingSince = null;
      return latency;
    },
  };
}

type PracticeAudioSource = { getMediaStreamTrack(): { stop(): void } };
/** Close the SDK resources and stop browser tracks even if an SDK teardown fails. */
export function releasePracticeAudio(scope: { dispose(): void }, sources: Array<PracticeAudioSource | undefined>): void {
  const nativeTracks = sources.flatMap(source => {
    try { return source ? [source.getMediaStreamTrack()] : []; } catch { return []; }
  });
  try { scope.dispose(); } catch { /* Native stop below still releases capture/playback. */ }
  finally { for (const track of nativeTracks) { try { track.stop(); } catch { /* Already stopped. */ } } }
}

/** Finish ordering is important: local audio off → history/feedback → cloud stop. */
export async function completePracticeFeedback(options: {
  releaseLocal(): void;
  flushTranscript?: () => Promise<void>;
  requestFeedback(): Promise<TaylorPracticeFeedback>;
  closeCloud(): Promise<unknown>;
  isCancelled(): boolean;
  errorMessage(error: unknown): string;
}): Promise<{ feedback: TaylorPracticeFeedback; cloudClosed: boolean; awaitingFeedback?: boolean }> {
  let localReleased = true;
  try { options.releaseLocal(); } catch { localReleased = false; }
  if (localReleased) { try { await options.flushTranscript?.(); } catch { /* Cloud history is authoritative. */ } }
  let feedback: TaylorPracticeFeedback;
  if (!localReleased) {
    feedback = { status: "unavailable", indicative_score: null, message: "Practice could not finish cleanly, so no feedback was requested." };
  } else if (options.isCancelled()) {
    feedback = { status: "unavailable", indicative_score: null, message: "Practice ended before feedback was requested." };
  } else {
    try { feedback = await options.requestFeedback(); }
    catch (error) { feedback = { status: "unavailable", indicative_score: null, message: options.errorMessage(error) }; }
  }
  // A concurrent/idempotent request can return progress before the original
  // feedback operation finishes. Preserve the cloud agent for GET-only polling.
  if (feedback.status === "requesting_feedback" && !options.isCancelled()) {
    return { feedback, cloudClosed: false, awaitingFeedback: true };
  }
  // Also verify cleanup after an HTTP-success response: feedback can be ready
  // even if the server's first attempt to stop the cloud agent failed.
  try { await options.closeCloud(); return { feedback, cloudClosed: true }; }
  catch { return { feedback, cloudClosed: false }; }
}

/** Report how many answers were actually reviewed, rather than all captured answers. */
export function practiceAnswerCount(feedback: TaylorPracticeFeedback): string | null {
  const total = feedback.answered_questions;
  const reviewed = feedback.reviewed_answers;
  const valid = (value: number | undefined): value is number => typeof value === "number" && Number.isInteger(value) && value >= 0;
  if (valid(reviewed) && valid(total) && reviewed <= total) {
    return reviewed < total ? `Feedback based on ${reviewed} of ${total} practice answers.` : `Feedback based on ${reviewed} practice ${reviewed === 1 ? "answer" : "answers"}.`;
  }
  return valid(total) ? `${total} practice ${total === 1 ? "answer" : "answers"} recorded.` : null;
}
