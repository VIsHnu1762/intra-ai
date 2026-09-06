"use client";

import { Cpu, Users, FileCheck2, UserCheck } from "lucide-react";

export default function SignalStrip() {
  const pillars = [
    {
      title: "Adapts to every answer",
      desc: "Questions probe contradictions and go deeper where depth is demonstrated.",
      icon: Cpu,
    },
    {
      title: "Alex and Jordan — two specialists",
      desc: "Alex tests technical architecture. Jordan tests product judgment.",
      icon: Users,
    },
    {
      title: "Evidence, not just a score",
      desc: "Concrete verbatim findings and confidence ratings replace arbitrary percentiles.",
      icon: FileCheck2,
    },
    {
      title: "You make the final call",
      desc: "Intra AI surfaces the evidence. The hiring decision always belongs to you.",
      icon: UserCheck,
    },
  ];

  const competencies = [
    "System Design",
    "Product Sense",
    "Communication Depth",
    "Technical Reasoning",
    "Customer Empathy",
    "Distributed Systems",
    "Prioritization",
    "Engineering Excellence",
    "Product Strategy",
    "Behavioral Depth",
    "API Architecture",
    "Root Cause Diagnosis",
  ];

  return (
    <section id="features" className="border-b border-[#EBEBEA] bg-[#F9F9F8] relative overflow-hidden">
      {/* 4 Feature Columns */}
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 sm:py-7">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-6">
          {pillars.map((pillar, i) => {
            const Icon = pillar.icon;
            return (
              <div key={i} className="flex flex-col items-start text-left">
                <Icon className="w-3.5 h-3.5 text-[#00A88A] mb-1.5 stroke-[1.5]" />
                <h3 className="text-xs sm:text-[13px] font-semibold text-[#0F0F0F] mb-0.5">
                  {pillar.title}
                </h3>
                <p className="text-[11px] text-[#6B6B6A] leading-relaxed">
                  {pillar.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>

      {/* Marquee Strip (Calm 60s glide) */}
      <div className="border-t border-[#EBEBEA] bg-white py-2 overflow-hidden select-none">
        <div
          className="animate-marquee flex items-center gap-6 whitespace-nowrap"
          style={{ animationDuration: "60s" }}
        >
          {/* First loop */}
          {competencies.map((comp, i) => (
            <span key={`a-${i}`} className="flex items-center gap-6">
              <span className="text-[10px] font-mono uppercase tracking-widest text-[#A0A09E] font-medium hover:text-[#0F0F0F] transition-colors">
                {comp}
              </span>
              <span className="text-[#D4D4D2] text-[10px]">·</span>
            </span>
          ))}
          {/* Repeated loop for continuous marquee */}
          {competencies.map((comp, i) => (
            <span key={`b-${i}`} className="flex items-center gap-6">
              <span className="text-[10px] font-mono uppercase tracking-widest text-[#A0A09E] font-medium hover:text-[#0F0F0F] transition-colors">
                {comp}
              </span>
              <span className="text-[#D4D4D2] text-[10px]">·</span>
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
