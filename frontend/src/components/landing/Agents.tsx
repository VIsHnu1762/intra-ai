"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Waveform from "@/components/ui/Waveform";
import { ArrowRight } from "lucide-react";

export default function Agents() {
  const [isUnlocked, setIsUnlocked] = useState(false);

  const alexChips = [
    "System design",
    "Scalability",
    "Architecture",
    "Technical depth",
  ];

  const jordanChips = [
    "Product sense",
    "Customer impact",
    "Prioritization",
    "User empathy",
  ];

  return (
    <section id="agents" className="relative py-12 md:py-14 bg-[#F9F9F8] overflow-hidden border-t border-[#EBEBEA]">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Headline */}
        <div className="text-center max-w-3xl mx-auto mb-7">
          <span className="text-xs font-mono font-semibold uppercase tracking-widest text-[#A0A09E] block mb-2">
            Multi-agent specialization
          </span>

          <h2 className="text-2xl sm:text-3xl lg:text-[38px] font-bold text-[#0F0F0F] leading-[1.15] tracking-tight mb-2.5">
            Who interviews your candidates?
          </h2>

          <p className="text-sm sm:text-base text-[#6B6B6A] leading-relaxed max-w-[540px] mx-auto">
            Two focused agents evaluate distinct dimensions of candidate competence.
          </p>
        </div>

        {/* Reveal Area */}
        <div className="max-w-4xl mx-auto flex justify-center items-center min-h-[260px]">
          <AnimatePresence mode="wait">
            {!isUnlocked ? (
              /* STAGE A: Locked / Blurred Preview Card */
              <motion.div
                key="locked-teaser"
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.3 }}
                className="relative w-full max-w-[440px] rounded-2xl border border-[#1A1A1A] bg-[#0F0F0F] p-5 sm:p-6 shadow-2xl overflow-hidden group cursor-pointer"
                onClick={() => setIsUnlocked(true)}
              >
                {/* Obscured / Blurred Silhouettes & Preview */}
                <div
                  className="filter blur-[8px] transition-all duration-400 select-none pointer-events-none"
                  aria-hidden="true"
                >
                  <div className="flex items-center justify-between mb-4 opacity-60">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-[#00A88A]/30 border border-[#00A88A]/40 flex items-center justify-center font-bold text-white text-xs">
                        A
                      </div>
                      <div className="w-9 h-9 rounded-full bg-[#6D28D9]/30 border border-[#6D28D9]/40 flex items-center justify-center font-bold text-white text-xs">
                        J
                      </div>
                    </div>
                    <div className="opacity-40">
                      <Waveform color="teal" barCount={12} height={16} active={false} />
                    </div>
                  </div>

                  <div className="space-y-2 opacity-50">
                    <div className="h-3.5 w-40 bg-white/20 rounded" />
                    <div className="h-2.5 w-56 bg-white/10 rounded" />
                  </div>

                  <div className="mt-6 pt-3 border-t border-white/10 text-center">
                    <span className="text-[11px] font-mono text-white/50 tracking-wider uppercase">
                      2 specialized interviewers
                    </span>
                  </div>
                </div>

                {/* Frosted Overlay with Unlock Button */}
                <div className="absolute inset-0 bg-black/60 backdrop-blur-[2px] flex flex-col items-center justify-center p-5 text-center z-20">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setIsUnlocked(true);
                    }}
                    data-cursor="cta"
                    className="inline-flex items-center gap-2 rounded-full bg-black/90 border border-white/25 px-5 py-2.5 text-xs font-semibold text-white shadow-2xl hover:bg-black hover:border-white/40 hover:scale-105 transition-all duration-200 cursor-pointer"
                  >
                    <span>See the interviewers</span>
                    <ArrowRight className="w-3.5 h-3.5 text-[#00A88A]" />
                  </button>
                  <span className="text-[10px] text-[#A0A09E] mt-2 font-mono">
                    Click to unlock agent identities
                  </span>
                </div>
              </motion.div>
            ) : (
              /* STAGE B: Unlocked Dual Cards (Alex & Jordan) */
              <div key="unlocked-cards" className="w-full">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-5 md:gap-6 w-full">
                  {/* ALEX CARD (Left, Teal Identity) */}
                  <motion.div
                    initial={{ opacity: 0, x: 40 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, ease: "easeOut" }}
                    className="rounded-2xl border border-[#1A1A1A] bg-[#0F0F0F] p-5 sm:p-6 shadow-[0_4px_24px_rgba(0,0,0,0.12)] flex flex-col justify-between"
                  >
                    <div>
                      {/* Avatar & Header */}
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-[#00A88A]/20 border border-[#00A88A]/40 flex items-center justify-center font-bold text-base text-[#00A88A]">
                            A
                          </div>
                          <div>
                            <h3 className="text-xl font-semibold text-white tracking-tight">
                              Alex
                            </h3>
                            <p className="text-xs text-[#6B6B6A]">
                              Technical interviewer
                            </p>
                          </div>
                        </div>

                        {/* Animated Waveform */}
                        <div className="bg-white/[0.04] border border-white/[0.08] rounded-lg px-2.5 py-1">
                          <Waveform
                            color="teal"
                            customColor="#00A88A"
                            barCount={12}
                            height={18}
                            variant="staccato"
                            active
                          />
                        </div>
                      </div>

                      {/* Competency Chips (Delayed Fade-in) */}
                      <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.2 }}
                        className="flex flex-wrap items-center gap-1.5 pt-1"
                      >
                        {alexChips.slice(0, 3).map((chip) => (
                          <span
                            key={chip}
                            className="px-2 py-0.5 text-[11px] rounded bg-[rgba(0,168,138,0.12)] border border-[rgba(0,168,138,0.3)] text-[#00A88A]"
                          >
                            {chip}
                          </span>
                        ))}
                        <span className="px-1.5 py-0.5 text-[10px] rounded border border-white/10 text-white/40 font-mono">
                          +1 more
                        </span>
                      </motion.div>
                    </div>
                  </motion.div>

                  {/* JORDAN CARD (Right, Violet Identity) */}
                  <motion.div
                    initial={{ opacity: 0, x: -40 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.5, delay: 0.15, ease: "easeOut" }}
                    className="rounded-2xl border border-[#1A1A1A] bg-[#0F0F0F] p-5 sm:p-6 shadow-[0_4px_24px_rgba(0,0,0,0.12)] flex flex-col justify-between"
                  >
                    <div>
                      {/* Avatar & Header */}
                      <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-[#6D28D9]/20 border border-[#6D28D9]/40 flex items-center justify-center font-bold text-base text-[#7C3AED]">
                            J
                          </div>
                          <div>
                            <h3 className="text-xl font-semibold text-white tracking-tight">
                              Jordan
                            </h3>
                            <p className="text-xs text-[#6B6B6A]">
                              Product interviewer
                            </p>
                          </div>
                        </div>

                        {/* Animated Waveform */}
                        <div className="bg-white/[0.04] border border-white/[0.08] rounded-lg px-2.5 py-1">
                          <Waveform
                            color="violet"
                            customColor="#7C3AED"
                            barCount={12}
                            height={18}
                            variant="flowing"
                            active
                          />
                        </div>
                      </div>

                      {/* Competency Chips (Delayed Fade-in) */}
                      <motion.div
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.4, delay: 0.35 }}
                        className="flex flex-wrap items-center gap-1.5 pt-1"
                      >
                        {jordanChips.slice(0, 3).map((chip) => (
                          <span
                            key={chip}
                            className="px-2 py-0.5 text-[11px] rounded bg-[rgba(109,40,217,0.12)] border border-[rgba(109,40,217,0.3)] text-[#7C3AED]"
                          >
                            {chip}
                          </span>
                        ))}
                        <span className="px-1.5 py-0.5 text-[10px] rounded border border-white/10 text-white/40 font-mono">
                          +1 more
                        </span>
                      </motion.div>
                    </div>
                  </motion.div>
                </div>

                {/* STAGE C: Context line after reveal */}
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, delay: 0.3 }}
                  className="mt-5 text-center"
                >
                  <p className="text-xs sm:text-sm text-[#6B6B6A]">
                    Alex tests system architecture down to failure states. Jordan tests product judgment against real operational trade-offs.{" "}
                    <a
                      href="#demo"
                      className="text-[#00A88A] hover:underline inline-flex items-center gap-1 font-medium transition-colors"
                    >
                      Listen to a live interview →
                    </a>
                  </p>
                </motion.div>
              </div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  );
}
