"use client";

import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";

export default function FinalCTA() {
  const footerLinks = [
    { label: "Features", href: "#features" },
    { label: "How It Works", href: "#how-it-works" },
    { label: "Agents", href: "#agents" },
    { label: "Adaptive AI", href: "#adaptive" },
    { label: "Evidence Engine", href: "#evidence" },
    { label: "Demo", href: "#demo" },
    { label: "Sign In", href: "/login" },
  ];

  return (
    <footer className="relative overflow-hidden">
      {/* Dark CTA Block (Intentional contrast exception) */}
      <div className="bg-[#0F0F0F] border-t border-[#1A1A1A] relative overflow-hidden">
        <div className="mx-auto max-w-4xl px-4 sm:px-6 lg:px-8 pt-12 pb-10 sm:pt-14 sm:pb-12 text-center relative z-10">
          <div className="inline-flex items-center gap-1.5 rounded-full border border-[#00A88A]/30 bg-[#00A88A]/10 px-3 py-1 mb-4">
            <Sparkles className="w-3 h-3 text-[#00A88A]" />
            <span className="text-[10px] font-semibold text-[#00A88A] tracking-wider uppercase">
              Live and Working Today
            </span>
          </div>

          <h2 className="text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tight text-white mb-2.5">
            How do you start?
          </h2>

          <p className="text-sm sm:text-base text-[#A0A09E] max-w-[460px] mx-auto leading-relaxed mb-6">
            Post a job, invite your candidate, and review the evidence this week.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <Link
              href="/signup"
              data-cursor="cta"
              className="group inline-flex items-center justify-center gap-2 rounded-full bg-[#00A88A] px-6 py-2.5 text-xs sm:text-sm font-semibold text-white hover:bg-[#009678] shadow-md shadow-[#00A88A]/20 transition-all duration-200 hover:scale-[1.02]"
            >
              <span>Post your first job</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
            </Link>

            <a
              href="mailto:contact@intraai.io"
              data-cursor="cta"
              className="inline-flex items-center justify-center gap-2 rounded-full border border-[#262626] bg-transparent px-6 py-2.5 text-xs sm:text-sm font-normal text-[#A0A09E] hover:text-white hover:border-[#404040] hover:bg-white/[0.03] transition-all duration-200"
            >
              Talk to the team
            </a>
          </div>

          <p className="mt-5 text-[11px] text-[#6B6B6A] font-mono">
            No credit card required. Fifteen free interview credits.
          </p>
        </div>
      </div>

      {/* Bottom Footer Bar (Pure White) */}
      <div className="border-t border-[#EBEBEA] bg-white py-5 sm:py-6">
        <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div className="w-6 h-6 rounded-md bg-[#0F0F0F] flex items-center justify-center">
              <span className="text-[#00A88A] text-[11px] font-extrabold">IA</span>
            </div>
            <span className="text-sm font-bold text-[#0F0F0F]">
              Intra <span className="text-[#00A88A]">AI</span>
            </span>
            <span className="text-[11px] text-[#A0A09E] ml-1.5 pl-2.5 border-l border-[#EBEBEA]">
              Multi-Agent Voice Platform
            </span>
          </div>

          {/* Links */}
          <div className="flex flex-wrap items-center justify-center gap-4 sm:gap-5 text-xs text-[#6B6B6A]">
            {footerLinks.map((link) => (
              <a
                key={link.label}
                href={link.href}
                className="hover:text-[#0F0F0F] transition-colors"
              >
                {link.label}
              </a>
            ))}
          </div>

          {/* Copyright & Tagline */}
          <div className="text-[11px] text-[#A0A09E] text-center md:text-right">
            <p>Built with AI. Designed for humans.</p>
            <p className="mt-0.5 text-[10px] text-[#A0A09E]">
              © {new Date().getFullYear()} Intra AI. All rights reserved.
            </p>
          </div>
        </div>
      </div>
    </footer>
  );
}
