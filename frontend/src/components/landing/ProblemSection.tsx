"use client";

import { motion } from "framer-motion";
import BlurHighlight from "@/components/ui/BlurHighlight";

export default function ProblemSection() {
  const columns = [
    {
      label: "Static questioning",
      body: "A candidate gives a surface-level answer, and the tool moves to the next question. You still do not know if they know the architecture.",
    },
    {
      label: "One generic voice",
      body: "A single prompt evaluates systems design and product intuition. It has no depth in either domain.",
    },
    {
      label: "Opaque scores",
      body: "The tool assigns an 82 out of 100 without explanation. You cannot defend that number to a hiring manager, so you repeat the interview yourself.",
    },
  ];

  return (
    <section className="relative bg-white py-12 md:py-14 border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-[760px] px-4 sm:px-6 lg:px-8">
        {/* Editorial Text Block */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.6 }}
        >
          <span className="text-xs font-mono font-semibold uppercase tracking-widest text-[#A0A09E] block mb-2.5">
            The problem with AI hiring
          </span>

          <div className="mb-3.5">
            <BlurHighlight
              text="Why do traditional AI interview tools leave you re-interviewing candidates?"
              highlights={["re-interviewing"]}
              className="text-2xl sm:text-3xl lg:text-[36px] font-bold text-[#0F0F0F] leading-[1.2] tracking-tight"
              highlightClassName="text-[#0F0F0F]"
              highlightBgClassName="bg-[#EBEBEA]"
              blurDuration={500}
              staggerDelay={50}
            />
          </div>

          <p className="text-sm sm:text-base text-[#6B6B6A] leading-[1.6] max-w-[580px] mb-8">
            Most tools ask scripted questions, ignore evasive answers, and hand you an arbitrary score.
          </p>
        </motion.div>

        {/* 3-Column Contrast Row (Describing their experience accurately) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 md:gap-6">
          {columns.map((col, idx) => (
            <motion.div
              key={col.label}
              initial={{ opacity: 0, y: 12 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: 0.15 + idx * 0.04 }}
              className="border-t border-[#EBEBEA] pt-3"
            >
              <h3 className="text-xs font-semibold uppercase tracking-wider text-[#A0A09E] mb-1.5">
                {col.label}
              </h3>
              <p className="text-xs sm:text-[13px] text-[#6B6B6A] leading-relaxed">
                {col.body}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
