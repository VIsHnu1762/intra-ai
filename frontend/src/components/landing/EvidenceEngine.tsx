"use client";

import { useState } from "react";
import { CheckCircle2, AlertCircle, FileText } from "lucide-react";

interface CompetencyData {
  id: string;
  name: string;
  scorePercent: number;
  confidence: "HIGH" | "MEDIUM" | "INSUFFICIENT";
  source: string;
  evidence: string[];
}

const COMPETENCY_LIST: CompetencyData[] = [
  {
    id: "system-design",
    name: "System Design",
    scorePercent: 88,
    confidence: "HIGH",
    source: "Round 1 (Alex) — Q3 & Q5 follow-up",
    evidence: [
      "Correctly identified horizontal vs vertical scaling trade-offs at 10M DAU",
      "Proposed multi-tier Redis caching with TTL eviction for read-heavy workload",
      "Described database sharding strategy using consistent hashing",
      "Acknowledged CAP theorem constraints and eventual consistency trade-offs",
    ],
  },
  {
    id: "distributed-systems",
    name: "Distributed Systems",
    scorePercent: 68,
    confidence: "MEDIUM",
    source: "Round 1 (Alex) — Q4",
    evidence: [
      "Articulated broker-based architecture using Kafka partitions",
      "Addressed backpressure and message dead-letter queues",
      "Did not detail split-brain consensus handling during network splits",
    ],
  },
  {
    id: "database-arch",
    name: "Database Architecture",
    scorePercent: 55,
    confidence: "MEDIUM",
    source: "Round 1 (Alex) — Q6",
    evidence: [
      "Competent index optimization on PostgreSQL B-tree indices",
      "Identified write amplification in secondary indexing under heavy ingest",
      "Limited depth on zero-downtime table migration lock contention",
    ],
  },
  {
    id: "code-quality",
    name: "Code Quality & Patterns",
    scorePercent: 90,
    confidence: "HIGH",
    source: "Round 1 (Alex) — Q2",
    evidence: [
      "Clean separation of business logic from infrastructure adapters",
      "Demonstrated idiomatic TypeScript and comprehensive error boundary handling",
      "Strong adherence to dependency inversion principle",
    ],
  },
  {
    id: "product-impact",
    name: "Product & Impact",
    scorePercent: 92,
    confidence: "HIGH",
    source: "Round 2 (Jordan) — Q1 & Q3",
    evidence: [
      "Walked through backlog reprioritization when engineering velocity halved",
      "Measured feature success using activation metrics rather than vanity signups",
      "Demonstrated clear customer empathy and user pain-point synthesis",
    ],
  },
  {
    id: "api-design",
    name: "API Design & Versioning",
    scorePercent: 20,
    confidence: "INSUFFICIENT",
    source: "Not directly probed in interview rounds",
    evidence: [
      "Insufficient direct conversational dialogue collected on public REST/gRPC versioning standards.",
      "Flagged for human recruiter or follow-up discussion — Intra AI does not guess missing data.",
    ],
  },
];

export default function EvidenceEngine() {
  const [selectedId, setSelectedId] = useState("system-design");
  const activeCompetency =
    COMPETENCY_LIST.find((c) => c.id === selectedId) || COMPETENCY_LIST[0];

  return (
    <section id="evidence" className="relative py-12 md:py-14 bg-[#F9F9F8] border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Headline */}
        <div className="text-center max-w-3xl mx-auto mb-7">
          <span className="text-xs font-mono font-semibold uppercase tracking-widest text-[#A0A09E] block mb-2">
            Evidence engine
          </span>
          <h2 className="text-2xl sm:text-3xl lg:text-[38px] font-bold tracking-tight text-[#0F0F0F] mb-2.5">
            What goes into your candidate report?
          </h2>
          <p className="text-sm sm:text-base text-[#6B6B6A] max-w-2xl mx-auto">
            You get direct evidence instead of a summary rating.
          </p>
        </div>

        {/* Interactive Evidence Report Box */}
        <div className="rounded-2xl border border-[#EBEBEA] bg-white p-4 sm:p-5 lg:p-6 shadow-[0_4px_24px_rgba(0,0,0,0.04)]">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-[#EBEBEA] pb-3.5 mb-4 gap-3">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-[#E6F7F4] border border-[#B3E8DF] flex items-center justify-center">
                <FileText className="w-4 h-4 text-[#00A88A]" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#0F0F0F] flex items-center gap-2">
                  Evaluation Report: Rahul Sharma
                  <span className="text-[10px] font-normal text-[#6B6B6A]">
                    Senior Backend Engineer
                  </span>
                </h3>
                <span className="text-[11px] text-[#A0A09E]">
                  Interviewed by Alex (Tech) & Jordan (Product) · Verified Signal
                </span>
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs">
              <span className="px-2.5 py-0.5 rounded-full bg-[#E6F7F4] text-[#007A65] border border-[#B3E8DF] font-semibold text-[11px]">
                Recommendation: Strong Hire
              </span>
            </div>
          </div>

          {/* Dual Panel */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 lg:gap-6">
            {/* Left Panel: Competency List */}
            <div className="lg:col-span-5 space-y-1.5">
              <span className="text-[11px] font-mono uppercase tracking-wider text-[#A0A09E] block mb-1">
                Competency Breakdown
              </span>
              {COMPETENCY_LIST.map((comp) => {
                const isSelected = comp.id === selectedId;
                return (
                  <button
                    key={comp.id}
                    onClick={() => setSelectedId(comp.id)}
                    className={`w-full text-left p-2.5 rounded-xl border transition-all duration-200 cursor-pointer ${
                      isSelected
                        ? "bg-white border-[#00A88A] shadow-[0_2px_10px_rgba(0,168,138,0.08)]"
                        : "bg-[#FAFAF9] border-[#EBEBEA] hover:bg-[#F5F5F4] hover:border-[#D4D4D2]"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span
                        className={`text-xs font-semibold ${
                          isSelected ? "text-[#00A88A]" : "text-[#0F0F0F]"
                        }`}
                      >
                        {comp.name}
                      </span>
                      <span
                        className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                          comp.confidence === "HIGH"
                            ? "bg-[#E6F7F4] text-[#007A65] border border-[#B3E8DF]"
                            : comp.confidence === "MEDIUM"
                            ? "bg-[#FFF8E6] text-[#92640A] border border-[#F5D87A]"
                            : "bg-[#FFF4F4] text-[#C53030] border border-[#FED7D7]"
                        }`}
                      >
                        {comp.confidence}
                      </span>
                    </div>

                    {/* Progress Bar */}
                    <div className="w-full bg-[#EBEBEA] h-1.5 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          comp.confidence === "HIGH"
                            ? "bg-[#00A88A]"
                            : comp.confidence === "MEDIUM"
                            ? "bg-[#D97706]"
                            : "bg-[#E53E3E]"
                        }`}
                        style={{ width: `${comp.scorePercent}%` }}
                      />
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Right Panel: Selected Detail */}
            <div className="lg:col-span-7 rounded-xl border border-[#EBEBEA] bg-[#FAFAF9] p-4 sm:p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-[#EBEBEA] pb-2.5 mb-2.5">
                  <div>
                    <span className="text-[10px] uppercase font-mono text-[#A0A09E]">
                      Selected Focus
                    </span>
                    <h4 className="text-base font-bold text-[#0F0F0F]">
                      {activeCompetency.name}
                    </h4>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-[#A0A09E] block">Confidence</span>
                    <span
                      className={`text-xs font-bold ${
                        activeCompetency.confidence === "HIGH"
                          ? "text-[#007A65]"
                          : activeCompetency.confidence === "MEDIUM"
                          ? "text-[#92640A]"
                          : "text-[#C53030]"
                      }`}
                    >
                      {activeCompetency.confidence}
                    </span>
                  </div>
                </div>

                <p className="text-[11px] text-[#6B6B6A] mb-3 flex items-center gap-1.5">
                  <span className="text-[#00A88A] font-medium">Source:</span> {activeCompetency.source}
                </p>

                <div className="space-y-2">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[#0F0F0F] block">
                    Synthesized Conversational Evidence:
                  </span>
                  {activeCompetency.evidence.map((bullet, idx) => (
                    <div
                      key={idx}
                      className="flex items-start gap-2 text-xs text-[#0F0F0F] leading-relaxed bg-white border border-[#EBEBEA] p-2.5 rounded-lg shadow-sm"
                    >
                      {activeCompetency.confidence === "INSUFFICIENT" ? (
                        <AlertCircle className="w-3.5 h-3.5 text-[#D97706] shrink-0 mt-0.5" />
                      ) : (
                        <CheckCircle2 className="w-3.5 h-3.5 text-[#00A88A] shrink-0 mt-0.5" />
                      )}
                      <span className="text-[#0F0F0F] text-[11px] sm:text-xs">{bullet}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Integrity Guarantee */}
              <div className="mt-4 pt-2.5 border-t border-[#EBEBEA] text-[10px] text-[#A0A09E]">
                * Untested skills are flagged as insufficient evidence rather than averaged into a false score.
              </div>
            </div>
          </div>
        </div>

        {/* Grounding Callout */}
        <div className="mt-8 max-w-2xl mx-auto p-4 sm:p-5 rounded-2xl border border-[#1A1A1A] bg-[#0F0F0F] shadow-lg">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 md:gap-6 items-center text-left relative">
            {/* Left column (Muted) */}
            <div className="opacity-75">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#A0A09E] block mb-1">
                What others give you
              </span>
              <p className="text-2xl sm:text-3xl font-mono font-bold text-[#888888] mb-1">
                87 / 100
              </p>
              <p className="text-[11px] text-[#A0A09E] leading-relaxed">
                An arbitrary score with zero context.
              </p>
            </div>

            {/* Vertical Divider for desktop */}
            <div className="hidden md:block absolute left-1/2 top-0 bottom-0 w-px bg-white/10 -translate-x-1/2" />

            {/* Horizontal Divider for mobile */}
            <div className="block md:hidden h-px w-full bg-white/10" />

            {/* Right column (Prominent Intra AI focal point) */}
            <div className="rounded-xl p-3 bg-white/[0.03] border border-[#00A88A]/30">
              <span className="text-[10px] font-mono uppercase tracking-wider text-[#00A88A] block mb-1 font-semibold">
                What Intra AI gives you
              </span>
              <p className="text-2xl sm:text-3xl font-bold text-[#00A88A] mb-1 tracking-tight">
                Verifiable Evidence
              </p>
              <p className="text-[11px] text-white leading-relaxed font-medium">
                Direct candidate quotes and transcripts your hiring manager can verify in seconds.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
