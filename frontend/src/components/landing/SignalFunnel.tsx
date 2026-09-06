"use client";

import { Filter, UserCheck, Mic, FileText, CheckCircle } from "lucide-react";

export default function SignalFunnel() {
  const stages = [
    {
      step: "01",
      title: "Application",
      volume: "1,000+ candidates",
      desc: "Raw applicant pool from job boards and referrals.",
      signal: "Resume & JD overlap",
      icon: Filter,
      isFinal: false,
    },
    {
      step: "02",
      title: "Screen",
      volume: "~150 eligible",
      desc: "Automated checks verify technical prerequisites.",
      signal: "Hardware & intent verified",
      icon: UserCheck,
      isFinal: false,
    },
    {
      step: "03",
      title: "Interview",
      volume: "~40 interviews",
      desc: "Live adaptive voice rounds with Alex and Jordan.",
      signal: "Conversational proof",
      icon: Mic,
      isFinal: false,
    },
    {
      step: "04",
      title: "Evidence",
      volume: "~8 finalists",
      desc: "Verbatim quotes mapped to competencies with confidence.",
      signal: "Grounded rubric",
      icon: FileText,
      isFinal: false,
    },
    {
      step: "05",
      title: "Decision",
      volume: "Hired",
      desc: "Recruiters inspect facts and make the final offer.",
      signal: "Human decision",
      icon: CheckCircle,
      isFinal: true,
    },
  ];

  return (
    <section className="relative py-10 md:py-12 bg-[#F9F9F8] border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center max-w-2xl mx-auto mb-6">
          <span className="text-xs font-mono font-semibold uppercase tracking-widest text-[#00A88A] block mb-1">
            Hiring Signal Architecture
          </span>
          <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-[#0F0F0F]">
            How does candidate volume turn into verified signal?
          </h2>
        </div>

        {/* Horizontal Pipeline Grid */}
        <div className="max-w-5xl mx-auto grid grid-cols-1 sm:grid-cols-5 gap-2.5 sm:gap-3">
          {stages.map((stage) => {
            const Icon = stage.icon;
            return (
              <div
                key={stage.step}
                className={`p-3 rounded-xl border flex flex-col justify-between transition-all ${
                  stage.isFinal
                    ? "bg-[#E6F7F4] border-[#B3E8DF] shadow-[0_2px_12px_rgba(0,168,138,0.1)]"
                    : "bg-white border-[#EBEBEA]"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <span
                      className={`text-[10px] font-mono font-bold ${
                        stage.isFinal ? "text-[#007A65]" : "text-[#A0A09E]"
                      }`}
                    >
                      STEP {stage.step}
                    </span>
                    <Icon
                      className={`w-3.5 h-3.5 ${
                        stage.isFinal ? "text-[#00A88A]" : "text-[#A0A09E]"
                      }`}
                    />
                  </div>
                  <h4 className="text-xs font-bold text-[#0F0F0F] mb-0.5">
                    {stage.title}
                  </h4>
                  <span className="text-[10px] text-[#00A88A] font-mono block mb-1">
                    {stage.volume}
                  </span>
                  <p className="text-[11px] text-[#6B6B6A] leading-tight">
                    {stage.desc}
                  </p>
                </div>
                <div className="mt-2.5 pt-1.5 border-t border-black/5 text-[10px] font-medium text-[#007A65]">
                  ✓ {stage.signal}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
