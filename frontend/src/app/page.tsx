import Nav from "@/components/landing/Nav";
import Hero from "@/components/landing/Hero";
import ProblemSection from "@/components/landing/ProblemSection";
import SignalStrip from "@/components/landing/SignalStrip";
import AdaptiveSection from "@/components/landing/AdaptiveSection";
import EvidenceEngine from "@/components/landing/EvidenceEngine";
import Agents from "@/components/landing/Agents";
import HowItWorks from "@/components/landing/HowItWorks";
import Demo from "@/components/landing/Demo";
import Comparison from "@/components/landing/Comparison";
import SignalFunnel from "@/components/landing/SignalFunnel";
import FinalCTA from "@/components/landing/FinalCTA";
import CustomCursor from "@/components/ui/CustomCursor";
import SmoothScroll from "@/components/ui/SmoothScroll";

export const metadata = {
  title: "Intra AI — Multi-Agent Adaptive Voice Interview Platform",
  description:
    "Specialized AI voice interviews with Alex and Jordan. Real-time adaptive questioning and evidence-based competency evaluation.",
};

export default function LandingPage() {
  return (
    <SmoothScroll>
      <div className="relative min-h-screen bg-white text-[#0F0F0F] selection:bg-[#E6F7F4] selection:text-[#00A88A] antialiased">
        {/* Custom Spring Cursor */}
        <CustomCursor />

        {/* Global Navigation */}
        <Nav />

        {/* Section 01: Hero with Live Interview Simulation */}
        <Hero />

        {/* Section 02: Problem Section (The Broken State of AI Interviews) */}
        <ProblemSection />

        {/* Section 03: 4-Pillar Signal Strip & Infinite Marquee */}
        <SignalStrip />

        {/* Section 04: Adaptive Inquiry Mechanics */}
        <AdaptiveSection />

        {/* Section 05: Competency Evidence Engine */}
        <EvidenceEngine />

        {/* Section 06: Meet the Interviewers (Alex & Jordan Reveal) */}
        <Agents />

        {/* Section 07: Recruiter Pipeline & Timeline */}
        <HowItWorks />

        {/* Section 08: Complete Hiring Flow (Signal Funnel) */}
        <SignalFunnel />

        {/* Section 09: Live Session Demo */}
        <Demo />

        {/* Section 10: What Makes Intra AI Different? (Architectural Comparison) */}
        <Comparison />

        {/* Section 11: Final CTA & Grounded Footer */}
        <FinalCTA />
      </div>
    </SmoothScroll>
  );
}
