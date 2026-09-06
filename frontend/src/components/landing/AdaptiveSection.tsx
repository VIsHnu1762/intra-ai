"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

export default function AdaptiveSection() {
  const [activeStage, setActiveStage] = useState<1 | 2 | 3>(2);

  return (
    <section id="adaptive" className="relative py-12 md:py-14 bg-white border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Headline */}
        <div className="text-center max-w-3xl mx-auto mb-7">
          <div className="inline-flex items-center gap-2 rounded-full border border-[#B3E8DF] bg-[#E6F7F4] px-3 py-0.5 mb-2.5">
            <span className="text-xs font-semibold text-[#00A88A] uppercase tracking-wider">
              Real-time adaptive questioning
            </span>
          </div>
          <h2 className="text-2xl sm:text-3xl lg:text-[38px] font-bold text-[#0F0F0F] tracking-tight mb-2.5">
            What happens when a candidate gives a vague answer?
          </h2>
          <p className="text-sm sm:text-base text-[#6B6B6A] max-w-2xl mx-auto">
            Intra AI listens to the response and changes the next question.
          </p>
        </div>

        {/* Split Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
          {/* Left: Sticky Perspective */}
          <div className="lg:col-span-5 lg:sticky lg:top-20 space-y-4">
            <div className="rounded-2xl border border-[#EBEBEA] bg-[#FAFAF9] p-5 sm:p-6 relative shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
              <span className="text-4xl font-serif text-[#00A88A]/30 select-none block -mt-2 mb-1">
                &ldquo;
              </span>
              <p className="text-base sm:text-lg font-medium text-[#0F0F0F] leading-snug mb-3">
                When a candidate mentions they &apos;used Redis,&apos; a generic interviewer moves on.
              </p>
              <p className="text-sm sm:text-base font-semibold text-[#00A88A] leading-relaxed">
                Intra AI asks: which eviction policy, and why?
              </p>

              <div className="mt-4 pt-4 border-t border-[#EBEBEA] space-y-2">
                <div className="flex items-center justify-between p-2 rounded-lg bg-[#FFF4F4] border border-[#FED7D7] text-xs">
                  <span className="text-[#C53030] font-medium">Script-based</span>
                  <span className="font-mono text-[#C53030] text-[11px]">Same for all</span>
                </div>
                <div className="flex items-center justify-between p-2 rounded-lg bg-[#E6F7F4] border border-[#B3E8DF] text-xs">
                  <span className="text-[#00A88A] font-semibold">Adaptive</span>
                  <span className="font-mono text-[#00A88A] font-bold text-[11px]">Unique follow-up</span>
                </div>
              </div>
            </div>
          </div>

          {/* Right: Interactive 3-Stage Experience */}
          <div className="lg:col-span-7 space-y-3">
            {/* Stage 1 */}
            <div
              onClick={() => setActiveStage(1)}
              className={`rounded-2xl border transition-all duration-200 p-4 sm:p-4.5 cursor-pointer shadow-[0_1px_4px_rgba(0,0,0,0.03)] ${
                activeStage === 1
                  ? "bg-white border-[#00A88A] ring-1 ring-[#00A88A]/20"
                  : "bg-white border-[#EBEBEA] hover:border-[#D4D4D2]"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono font-semibold uppercase tracking-wider text-[#A0A09E]">
                  Stage 01 · Initial Question
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-[#F9F9F8] text-[#6B6B6A] border border-[#EBEBEA]">
                  Initial Probe
                </span>
              </div>
              <div className="space-y-2">
                <div className="rounded-lg bg-[#F9F9F8] p-2.5 border border-[#EBEBEA]">
                  <p className="text-[11px] text-[#00A88A] font-semibold mb-0.5">Alex asks:</p>
                  <p className="text-xs sm:text-sm font-mono text-[#0F0F0F]">
                    &ldquo;Tell me about a system you designed that needed to scale.&rdquo;
                  </p>
                </div>
                <div className="rounded-lg bg-white p-2.5 border border-[#EBEBEA]">
                  <p className="text-[11px] text-[#6B6B6A] font-semibold mb-0.5">Candidate answers (Voice):</p>
                  <p className="text-xs sm:text-sm text-[#6B6B6A] italic">
                    &ldquo;I built a notification service at my last company...&rdquo;
                  </p>
                </div>
              </div>
            </div>

            {/* Stage 2 */}
            <div
              onClick={() => setActiveStage(2)}
              className={`rounded-2xl border transition-all duration-200 p-4 sm:p-4.5 cursor-pointer shadow-[0_1px_4px_rgba(0,0,0,0.03)] ${
                activeStage === 2
                  ? "bg-white border-[#00A88A] ring-1 ring-[#00A88A]/20"
                  : "bg-white border-[#EBEBEA] hover:border-[#D4D4D2]"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-mono font-semibold uppercase tracking-wider text-[#00A88A]">
                  Stage 02 · Adaptation Detection
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FFF8E6] text-[#92640A] border border-[#F5D87A] font-medium">
                  Adaptive Trigger
                </span>
              </div>

              {/* Alert Badge */}
              <div className="rounded-lg bg-[#FFF8E6] border border-[#F5D87A] p-2.5 my-2 text-xs text-[#92640A] leading-relaxed">
                ⚡ <strong>Gap detected</strong> — consistency model not addressed. Probing deeper.
              </div>

              <div className="rounded-lg bg-[#F9F9F8] p-2.5 border border-[#EBEBEA]">
                <p className="text-[11px] text-[#00A88A] font-semibold mb-0.5">Alex adapts:</p>
                <p className="text-xs sm:text-sm font-mono text-[#0F0F0F] leading-relaxed">
                  &ldquo;You mentioned the notification service — how did you handle message ordering guarantees at scale?&rdquo;
                </p>
              </div>
            </div>

            {/* Stage 3 */}
            <div
              onClick={() => setActiveStage(3)}
              className={`rounded-2xl border transition-all duration-200 p-4 sm:p-4.5 cursor-pointer shadow-[0_1px_4px_rgba(0,0,0,0.03)] ${
                activeStage === 3
                  ? "bg-white border-[#00A88A] ring-1 ring-[#00A88A]/20"
                  : "bg-white border-[#EBEBEA] hover:border-[#D4D4D2]"
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-mono font-semibold uppercase tracking-wider text-[#A0A09E]">
                  Stage 03 · Evidence Captured
                </span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FFF8E6] text-[#92640A] border border-[#F5D87A] font-medium">
                  Confidence: MEDIUM
                </span>
              </div>

              {/* Evidence Mini-Card */}
              <div className="rounded-lg border border-[#B3E8DF] bg-[#E6F7F4] p-3 space-y-2">
                <span className="text-xs font-bold text-[#0F0F0F] block">
                  Distributed Systems → Evidence collected
                </span>

                <div className="space-y-1.5 text-xs">
                  <div className="flex items-start gap-2 text-[#0F0F0F]">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#00A88A] shrink-0 mt-0.5" />
                    <span>Understands fan-out write problem</span>
                  </div>
                  <div className="flex items-start gap-2 text-[#92640A]">
                    <AlertTriangle className="w-3.5 h-3.5 text-[#D4A017] shrink-0 mt-0.5" />
                    <span>Consistency model — unclear, follow-up queued</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Section Footer Callout */}
        <div className="mt-8 text-center max-w-2xl mx-auto rounded-xl border border-[#EBEBEA] bg-[#F9F9F8] p-3.5">
          <p className="text-xs sm:text-sm text-[#6B6B6A] leading-relaxed">
            Unlike fixed questionnaires, Intra AI <span className="text-[#0F0F0F] font-semibold">investigates</span> — it follows gaps,
            probes contradictions, and increases difficulty when the candidate demonstrates depth.
          </p>
        </div>
      </div>
    </section>
  );
}
