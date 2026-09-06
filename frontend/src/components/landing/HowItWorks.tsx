"use client";

import { useState } from "react";
import { Briefcase, UserCheck, Mic, FileCheck, Award, ChevronRight } from "lucide-react";

export default function HowItWorks() {
  const [activeStep, setActiveStep] = useState(0);

  const steps = [
    {
      num: "01",
      title: "Post a Job",
      desc: "Describe the role. Intra AI parses your JD, extracts required competencies, and configures the interview structure automatically.",
      icon: Briefcase,
      mockTitle: "JD Parsing & Round Sequencing",
      mockDetail: "Extracted 6 competencies (System Design, Distributed Systems, Prioritization). Configured Alex (Tech) & Jordan (Product).",
      tag: "Configuration",
    },
    {
      num: "02",
      title: "Candidates Apply & Screen",
      desc: "Candidates apply and resumes are parsed in seconds. Qualified profiles are automatically invited to self-schedule their voice interview.",
      icon: UserCheck,
      mockTitle: "Automated Screening & Shortlisting",
      mockDetail: "142 resumes parsed. 18 qualified candidates invited directly to self-schedule voice interviews.",
      tag: "Screening",
    },
    {
      num: "03",
      title: "Alex and Jordan conduct the interview",
      desc: "Shortlisted candidates enter an adaptive voice interview with Alex and Jordan. Questions adapt dynamically as technical depth and product thinking are verified.",
      icon: Mic,
      mockTitle: "Multi-Agent Voice Room",
      mockDetail: "Alex investigates technical depth. Jordan tests product judgment. Questions adapt dynamically to candidate answers.",
      tag: "Live Execution",
    },
    {
      num: "04",
      title: "Evidence Aggregated",
      desc: "Every response is analyzed and mapped to competencies with honest confidence ratings. Gaps are surfaced clearly, not hidden behind generic scores.",
      icon: FileCheck,
      mockTitle: "Evidence Synthesis",
      mockDetail: "Verbatim quotes linked to competencies with HIGH / MEDIUM / INSUFFICIENT confidence indicators.",
      tag: "Analysis",
    },
    {
      num: "05",
      title: "Recruiter decides",
      desc: "Review structured competency evidence and verbatim quotes for every candidate. The final hiring decision always belongs to your team.",
      icon: Award,
      mockTitle: "Human Decision View",
      mockDetail: "Clear comparative view of shortlisted candidates with strengths, gaps, and grounded conversational proof.",
      tag: "Outcome",
    },
  ];

  return (
    <section id="how-it-works" className="relative py-12 md:py-14 bg-white border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Headline */}
        <div className="text-center max-w-3xl mx-auto mb-7">
          <span className="text-xs font-mono font-semibold uppercase tracking-widest text-[#00A88A] block mb-2">
            Workflow Architecture
          </span>
          <h2 className="text-2xl sm:text-3xl lg:text-[38px] font-bold tracking-tight text-[#0F0F0F] mb-2">
            How does an interview turn into a hiring decision?
          </h2>
          <p className="text-sm sm:text-base text-[#6B6B6A]">
            From your job description to an evidence-backed shortlist in five steps.
          </p>
        </div>

        {/* Timeline + Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8 items-start">
          {/* Left Timeline */}
          <div className="lg:col-span-5 space-y-2">
            {steps.map((step, idx) => {
              const Icon = step.icon;
              const isActive = activeStep === idx;
              return (
                <button
                  key={step.num}
                  onClick={() => setActiveStep(idx)}
                  className={`w-full text-left p-3 sm:p-3.5 rounded-xl border transition-all duration-200 cursor-pointer relative ${
                    isActive
                      ? "bg-white border-[#00A88A] shadow-[0_2px_12px_rgba(0,168,138,0.06)]"
                      : "bg-[#FAFAF9] border-[#EBEBEA] hover:bg-[#F5F5F4] hover:border-[#D4D4D2]"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 border ${
                        isActive
                          ? "bg-[#E6F7F4] border-[#B3E8DF] text-[#00A88A]"
                          : "bg-[#F0F0F0] border-[#E5E5E4] text-[#A0A09E]"
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between mb-0.5">
                        <span
                          className={`text-[11px] font-mono font-bold ${
                            isActive ? "text-[#00A88A]" : "text-[#A0A09E]"
                          }`}
                        >
                          STEP {step.num}
                        </span>
                        <span className="text-[9px] text-[#A0A09E] uppercase tracking-wider">
                          {step.tag}
                        </span>
                      </div>
                      <h3
                        className={`text-sm font-semibold mb-0.5 ${
                          isActive ? "text-[#0F0F0F]" : "text-[#6B6B6A]"
                        }`}
                      >
                        {step.title}
                      </h3>
                      <p className={`text-[11px] leading-relaxed max-w-[320px] line-clamp-2 ${
                        isActive ? "text-[#6B6B6A]" : "text-[#A0A09E]"
                      }`}>
                        {step.desc}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          {/* Right Visual Mockup of the Active Step */}
          <div className="lg:col-span-7 sticky top-20">
            <div className="rounded-2xl border border-[#EBEBEA] bg-white p-4 sm:p-5 lg:p-6 shadow-[0_4px_24px_rgba(0,0,0,0.04)] min-h-[360px] flex flex-col justify-between">
              <div>
                {/* Header of Mockup */}
                <div className="flex items-center justify-between border-b border-[#EBEBEA] pb-3 mb-4">
                  <div className="flex items-center gap-2.5">
                    <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-[#E6F7F4] text-[#007A65] border border-[#B3E8DF] font-semibold">
                      STEP {steps[activeStep].num}
                    </span>
                    <h4 className="text-xs sm:text-sm font-bold text-[#0F0F0F]">
                      {steps[activeStep].mockTitle}
                    </h4>
                  </div>
                  <span className="text-[11px] text-[#A0A09E] flex items-center gap-1">
                    State: <span className="text-[#00A88A] font-medium">Active</span>
                  </span>
                </div>

                {/* Body Details */}
                {activeStep === 4 ? (
                  <div className="space-y-3">
                    <div className="rounded-xl bg-[#FAFAF9] p-3 border border-[#EBEBEA]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#00A88A] block mb-0.5">
                        Evidence-Backed Human Decision
                      </span>
                      <p className="text-xs text-[#6B6B6A] leading-relaxed">
                        {steps[4].desc}
                      </p>
                    </div>

                    {/* Two-candidate comparison card mock */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                      {/* Candidate A */}
                      <div className="rounded-xl border border-[#00A88A] bg-white p-3 shadow-sm flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <div>
                              <h5 className="text-xs font-bold text-[#0F0F0F]">Rahul Sharma</h5>
                              <span className="text-[9px] text-[#6B6B6A]">Sr. Backend Engineer</span>
                            </div>
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-[#E6F7F4] text-[#007A65] border border-[#B3E8DF]">
                              Top Signal
                            </span>
                          </div>
                          <ul className="space-y-1 text-[10px] text-[#6B6B6A] mb-2">
                            <li className="flex items-start gap-1">
                              <span className="text-[#00A88A]">✓</span> Verified horizontal partitioning
                            </li>
                            <li className="flex items-start gap-1">
                              <span className="text-[#00A88A]">✓</span> Architecture for high-throughput scaling
                            </li>
                          </ul>
                        </div>
                        <button className="w-full py-1 rounded-lg bg-[#00A88A] text-white text-[11px] font-semibold hover:bg-[#009678] transition-colors cursor-pointer">
                          Invite
                        </button>
                      </div>

                      {/* Candidate B */}
                      <div className="rounded-xl border border-[#EBEBEA] bg-[#FAFAF9] p-3 shadow-sm flex flex-col justify-between">
                        <div>
                          <div className="flex items-center justify-between mb-1.5">
                            <div>
                              <h5 className="text-xs font-bold text-[#0F0F0F]">Elena Rostova</h5>
                              <span className="text-[9px] text-[#6B6B6A]">Sr. Backend Engineer</span>
                            </div>
                            <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-[#F0F0F0] text-[#6B6B6A] border border-[#EBEBEA]">
                              Qualified
                            </span>
                          </div>
                          <ul className="space-y-1 text-[10px] text-[#6B6B6A] mb-2">
                            <li className="flex items-start gap-1">
                              <span className="text-[#00A88A]">✓</span> Strong distributed consensus models
                            </li>
                            <li className="flex items-start gap-1">
                              <span className="text-[#D97706]">•</span> Gap flagged on cache eviction
                            </li>
                          </ul>
                        </div>
                        <button className="w-full py-1 rounded-lg border border-[#D4D4D2] bg-white text-[#0F0F0F] text-[11px] font-medium hover:bg-[#F5F5F4] transition-colors cursor-pointer">
                          Invite
                        </button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-3">
                    <div className="rounded-xl bg-[#FAFAF9] p-3.5 border border-[#EBEBEA]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#00A88A] block mb-1">
                        Operational Mechanism
                      </span>
                      <p className="text-xs sm:text-sm text-[#0F0F0F] leading-relaxed">
                        {steps[activeStep].desc}
                      </p>
                    </div>

                    <div className="rounded-xl bg-[#F9F9F8] p-3.5 border border-[#EBEBEA]">
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-[#6B6B6A] block mb-1">
                        Live Telemetry Output
                      </span>
                      <p className="text-xs font-mono text-[#6B6B6A] leading-relaxed">
                        {steps[activeStep].mockDetail}
                      </p>
                    </div>
                  </div>
                )}
              </div>

              {/* Progress Tracker */}
              <div className="mt-4 pt-3 border-t border-[#EBEBEA] flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  {steps.map((_, i) => (
                    <span
                      key={i}
                      className={`h-1 rounded-full transition-all duration-300 ${
                        activeStep === i
                          ? "w-6 bg-[#00A88A]"
                          : "w-1.5 bg-[#EBEBEA]"
                      }`}
                    />
                  ))}
                </div>
                <button
                  onClick={() => setActiveStep((prev) => (prev + 1) % steps.length)}
                  className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#00A88A] hover:text-[#0F0F0F] transition-colors cursor-pointer"
                >
                  <span>Next Step</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
