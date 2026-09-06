"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import { ArrowRight, CheckCircle2, Cpu } from "lucide-react";
import Waveform from "@/components/ui/Waveform";

export default function Hero() {
  const [typedQuestion, setTypedQuestion] = useState("");
  const [showEvidence, setShowEvidence] = useState(false);

  const fullQuestion =
    "You mentioned horizontal scaling earlier. Walk me through how you'd handle database bottlenecks at 10M users.";

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    let charIndex = 0;
    let isCancelled = false;

    const runSequence = () => {
      charIndex = 0;
      setTypedQuestion("");
      setShowEvidence(false);

      const typeInterval = setInterval(() => {
        if (isCancelled) {
          clearInterval(typeInterval);
          return;
        }
        if (charIndex <= fullQuestion.length) {
          setTypedQuestion(fullQuestion.slice(0, charIndex));
          charIndex++;
        } else {
          clearInterval(typeInterval);
          timeout = setTimeout(() => {
            if (!isCancelled) {
              setShowEvidence(true);
              timeout = setTimeout(() => {
                if (!isCancelled) {
                  runSequence();
                }
              }, 5000);
            }
          }, 800);
        }
      }, 35);
    };

    runSequence();

    return () => {
      isCancelled = true;
      clearTimeout(timeout);
    };
  }, []);

  return (
    <section className="relative pt-18 pb-10 sm:pt-20 sm:pb-12 flex items-center justify-center bg-white overflow-hidden">
      <div className="relative mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 w-full z-10">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-8 items-center">
          {/* Left Column: Headlines and CTAs */}
          <div className="lg:col-span-7 flex flex-col items-start text-left">
            {/* Eyebrow Pill */}
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5 }}
              className="inline-flex items-center rounded-full border border-[#B3E8DF] bg-[#E6F7F4] px-3 py-0.5 mb-3.5"
            >
              <span className="text-xs font-semibold text-[#00A88A] tracking-wide uppercase">
                Adaptive voice interviews
              </span>
            </motion.div>

            {/* Headline (Under 12 words: Answers 'What does Intra AI do?') */}
            <div className="mb-3.5">
              <motion.h1
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="text-3xl sm:text-4xl lg:text-[46px] font-bold tracking-[-0.025em] leading-[1.14] text-[#0F0F0F]"
              >
                Intra AI interviews your candidates and gives you verifiable evidence.
              </motion.h1>
            </div>

            {/* Subheadline (One sentence maximum) */}
            <motion.p
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.25 }}
              className="text-sm sm:text-base leading-relaxed text-[#6B6B6A] mb-6 max-w-[500px]"
            >
              Alex tests technical depth, Jordan tests product judgment, and you decide who gets hired.
            </motion.p>

            {/* Footnote Cluster: CTAs & Reassurance */}
            <motion.div
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.35 }}
              className="space-y-2.5 w-full sm:w-auto"
            >
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5">
                <a
                  href="#demo"
                  data-cursor="demo"
                  className="group inline-flex items-center justify-center gap-2 rounded-lg bg-[#0F0F0F] px-4.5 py-2.5 text-xs sm:text-sm font-medium text-white hover:bg-[#1F1F1F] transition-colors shadow-sm"
                >
                  <span>Listen to a live interview</span>
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                </a>

                <a
                  href="#evidence"
                  data-cursor="cta"
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-[#D4D4D2] bg-white px-4.5 py-2.5 text-xs sm:text-sm font-medium text-[#0F0F0F] hover:bg-[#F5F5F4] transition-colors"
                >
                  View a sample report
                </a>
              </div>

              {/* Reassurance */}
              <p className="text-[11px] text-[#A0A09E] flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#00A88A]" />
                No account required. Two-minute audio sample.
              </p>
            </motion.div>
          </div>

          {/* Right Column: Clean White Ghost Interview Mock Card */}
          <motion.div
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 0.25 }}
            className="lg:col-span-5 hidden lg:block"
          >
            <div className="relative rounded-2xl border border-[#EBEBEA] bg-white/90 p-4 sm:p-5 shadow-[0_2px_12px_rgba(0,0,0,0.03)] opacity-95 hover:opacity-100 transition-opacity">
              {/* Top Bar */}
              <div className="flex items-center justify-between border-b border-[#EBEBEA] pb-3 mb-3.5">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse" />
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-[#0F0F0F]">
                    LIVE INTERVIEW
                  </span>
                </div>
                <span className="text-xs text-[#6B6B6A]">
                  Rahul Sharma · Backend Engineer
                </span>
              </div>

              {/* Agent Indicator */}
              <div className="flex items-center justify-between rounded-xl bg-[#F9F9F8] border border-[#EBEBEA] p-2.5 mb-3.5">
                <div className="flex items-center gap-2.5">
                  <div className="relative w-8 h-8 rounded-full bg-[#E6F7F4] border border-[#00A88A] flex items-center justify-center font-bold text-[#00A88A] text-xs">
                    A
                    <span className="absolute bottom-0 right-0 w-1.5 h-1.5 rounded-full bg-[#22C55E] border border-white" />
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-xs font-semibold text-[#0F0F0F]">Alex</span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-medium bg-[#E6F7F4] text-[#00A88A] border border-[#B3E8DF]">
                        Technical Round
                      </span>
                    </div>
                    <span className="text-[10px] text-[#6B6B6A]">Voice AI</span>
                  </div>
                </div>

                {/* Animated Voice Waveform */}
                <Waveform color="teal" customColor="#00A88A" barCount={12} height={18} variant="staccato" active />
              </div>

              {/* Question Box */}
              <div className="rounded-xl border border-[#EBEBEA] bg-[#F9F9F8] p-3 mb-3 min-h-[72px]">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[10px] font-semibold text-[#00A88A] uppercase tracking-wider">
                    Adaptive Inquiry
                  </span>
                  <span className="text-[10px] text-[#A0A09E]">Turn 4 of 12</span>
                </div>
                <p className="text-xs font-mono text-[#0F0F0F] leading-relaxed">
                  &ldquo;{typedQuestion}&rdquo;
                  <span className="inline-block w-1 h-3.5 ml-1 bg-[#00A88A] animate-pulse align-middle" />
                </p>
              </div>

              {/* Competency Evidence Mini-Card */}
              <div
                className={`transition-all duration-400 rounded-xl border border-[#B3E8DF] bg-[#E6F7F4] p-3 ${
                  showEvidence
                    ? "opacity-100 translate-y-0"
                    : "opacity-0 translate-y-2 pointer-events-none"
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-[#00A88A]" />
                    <span className="text-xs font-semibold text-[#0F0F0F]">
                      System Design → Strong
                    </span>
                  </div>
                  <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-[#0F0F0F] text-white">
                    Confidence: HIGH
                  </span>
                </div>
                <ul className="text-[10px] text-[#6B6B6A] space-y-0.5 pl-1">
                  <li className="flex items-center gap-1">
                    <span className="text-[#00A88A]">✓</span> Identified horizontal partitioning correctly
                  </li>
                  <li className="flex items-center gap-1">
                    <span className="text-[#00A88A]">✓</span> Proposed multi-tiered Redis caching layer
                  </li>
                </ul>
              </div>

              {/* Footer Latency Bar */}
              <div className="mt-3.5 pt-2.5 border-t border-[#EBEBEA] flex items-center justify-between text-[10px] text-[#6B6B6A]">
                <span className="flex items-center gap-1.5">
                  <Cpu className="w-3 h-3 text-[#00A88A]" />
                  Voice Latency: 240ms
                </span>
                <span className="font-mono text-[#00A88A]">Active Stream</span>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
