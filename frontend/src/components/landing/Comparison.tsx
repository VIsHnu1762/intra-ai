"use client";

import { Check, X } from "lucide-react";
import BlurHighlight from "@/components/ui/BlurHighlight";

export default function Comparison() {
  const rows = [
    {
      attribute: "Question style",
      traditional: "Same static script for every candidate",
      intra: "Adapts dynamically based on each answer",
    },
    {
      attribute: "Interviewer personas",
      traditional: "Single generic chatbot assistant",
      intra: "Alex (Technical) + Jordan (Product) specialists",
    },
    {
      attribute: "Follow-up depth",
      traditional: "Scripted surface queries or none",
      intra: "Probes architectural gaps and contradictions",
    },
    {
      attribute: "Evaluation output",
      traditional: "Arbitrary score or single percentile number",
      intra: "Competency evidence matrix with confidence ratings",
    },
    {
      attribute: "Explanation depth",
      traditional: 'Opaque score: "82/100"',
      intra: "Verbatim evidence bullets linked to question sources",
    },
    {
      attribute: "Recruiter role",
      traditional: "Blindly trust algorithmic recommendation",
      intra: "Inspect ground-truth evidence, make the final call",
    },
  ];

  return (
    <section id="comparison" className="relative py-12 md:py-16 bg-white border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Headline */}
        <div className="text-center max-w-2xl mx-auto mb-7">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-widest text-[#00A88A] block mb-1.5">
            Architectural Differentiation
          </span>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#0F0F0F] mb-2">
            What makes Intra AI different?
          </h2>
          <p className="text-sm text-[#6B6B6A]">
            Compare how traditional interview platforms operate versus Intra AI&apos;s adaptive multi-agent system.
          </p>
        </div>

        {/* Comparison Table */}
        <div className="max-w-4xl mx-auto rounded-xl border border-[#EBEBEA] bg-white overflow-hidden shadow-[0_2px_12px_rgba(0,0,0,0.03)]">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-[#EBEBEA] bg-[#F9F9F8]">
                  <th className="py-2.5 px-4 font-mono uppercase text-[10px] text-[#A0A09E] w-1/4">
                    Dimension
                  </th>
                  <th className="py-2.5 px-4 font-semibold text-[#6B6B6A] w-3/8 text-xs">
                    Traditional AI Interviews
                  </th>
                  <th className="py-2.5 px-4 font-bold text-[#007A65] w-3/8 bg-[#E6F7F4] border-l border-[#B3E8DF] text-xs">
                    Intra AI Platform
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#EBEBEA]">
                {rows.map((row, idx) => (
                  <tr
                    key={idx}
                    className={`transition-colors hover:bg-[#F5F5F4] ${
                      idx % 2 === 1 ? "bg-[#FAFAF9]" : "bg-white"
                    }`}
                  >
                    <td className="py-2.5 px-4 font-medium text-[#0F0F0F] text-xs">
                      {row.attribute}
                    </td>
                    <td className="py-2.5 px-4 text-[#6B6B6A] text-xs">
                      <div className="flex items-center gap-1.5">
                        <X className="w-3.5 h-3.5 text-[#D4D4D2] shrink-0" />
                        <span>{row.traditional}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-4 text-[#0F0F0F] font-medium bg-[#E6F7F4]/30 border-l border-[#EBEBEA]">
                      <div className="flex items-center gap-1.5 text-xs">
                        <Check className="w-3.5 h-3.5 text-[#00A88A] shrink-0" />
                        <span>{row.intra}</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Large Centered Pullquote */}
        <div className="mt-8 sm:mt-10 max-w-3xl mx-auto text-center p-5 sm:p-6 rounded-xl bg-[#FAFAF9] border border-[#EBEBEA]">
          <div className="flex justify-center mb-1">
            <BlurHighlight
              text="AI surfaces the evidence. Recruiters make the decision."
              highlights={["evidence", "Recruiters"]}
              className="text-xl sm:text-2xl font-semibold justify-center text-center text-[#0F0F0F] max-w-[520px] mx-auto leading-snug"
              highlightClassName="text-[#00A88A]"
              blurDuration={500}
              staggerDelay={50}
            />
          </div>
          <div className="mt-4 pt-3 border-t border-[#EBEBEA] flex flex-wrap items-center justify-center gap-3 sm:gap-4 text-xs text-[#6B6B6A]">
            <span className="inline-flex items-center gap-1.5 font-medium text-[#0F0F0F]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00A88A]" />
              Adaptive questioning
            </span>
            <span className="text-[#D4D4D2]">·</span>
            <span className="inline-flex items-center gap-1.5 font-medium text-[#0F0F0F]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00A88A]" />
              Specialized multi-agent interviewers
            </span>
            <span className="text-[#D4D4D2]">·</span>
            <span className="inline-flex items-center gap-1.5 font-medium text-[#0F0F0F]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#00A88A]" />
              Verifiable competency evidence
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
