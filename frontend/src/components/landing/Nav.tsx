"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { ArrowRight, Menu, X } from "lucide-react";

const NAV_ITEMS = [
  { label: "How It Works", href: "#how-it-works" },
  { label: "Agents", href: "#agents" },
  { label: "For Recruiters", href: "#evidence" },
  { label: "Demo", href: "#demo" },
];

export default function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      if (window.scrollY > 20) {
        setScrolled(true);
      } else {
        setScrolled(false);
      }
    };
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleScrollTo = (e: React.MouseEvent<HTMLAnchorElement>, href: string) => {
    if (href.startsWith("#")) {
      e.preventDefault();
      setMobileOpen(false);
      const target = document.querySelector(href);
      if (target) {
        target.scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  return (
    <header
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-200 ${
        scrolled
          ? "bg-white/95 backdrop-blur-sm border-b border-[#EBEBEA] shadow-[0_1px_3px_rgba(0,0,0,0.02)]"
          : "bg-white/80 backdrop-blur-sm border-b-0"
      }`}
    >
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-12 flex items-center justify-between">
        {/* Left: Brand Wordmark */}
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-[#0F0F0F] flex items-center justify-center text-white text-xs font-bold tracking-tight">
            IA
          </div>
          <span className="text-lg font-bold tracking-tight text-[#0F0F0F]">
            Intra <span className="text-[#00A88A]">AI</span>
          </span>
        </Link>

        {/* Center: Desktop Nav Links (Clean, muted, single hover color) */}
        <div className="hidden md:flex items-center gap-6">
          {NAV_ITEMS.map((item) => (
            <a
              key={item.label}
              href={item.href}
              onClick={(e) => handleScrollTo(e, item.href)}
              className="text-xs font-medium text-[#6B6B6A] hover:text-[#0F0F0F] transition-colors"
            >
              {item.label}
            </a>
          ))}
        </div>

        {/* Right: Actions */}
        <div className="hidden md:flex items-center gap-5">
          <Link
            href="/login"
            className="text-xs font-medium text-[#6B6B6A] hover:text-[#0F0F0F] transition-colors"
          >
            Sign In
          </Link>
          <Link
            href="/signup"
            data-cursor="cta"
            className="inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-xs font-medium text-white bg-[#0F0F0F] hover:bg-[#1A1A1A] transition-colors shadow-sm"
          >
            <span>Get Started</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {/* Mobile Hamburger Toggle */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden p-2 rounded-lg text-[#6B6B6A] hover:text-[#0F0F0F] hover:bg-[#F9F9F8] transition-colors"
          aria-label="Toggle navigation"
        >
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </nav>

      {/* Mobile Drawer */}
      {mobileOpen && (
        <div className="md:hidden bg-white border-b border-[#EBEBEA] px-6 py-6 space-y-4 shadow-lg">
          <div className="flex flex-col space-y-2">
            {NAV_ITEMS.map((item) => (
              <a
                key={item.label}
                href={item.href}
                onClick={(e) => handleScrollTo(e, item.href)}
                className="px-3 py-2 text-sm font-medium text-[#6B6B6A] hover:text-[#0F0F0F] hover:bg-[#F9F9F8] rounded-lg transition-colors"
              >
                {item.label}
              </a>
            ))}
          </div>
          <div className="pt-4 border-t border-[#EBEBEA] flex flex-col gap-3">
            <Link
              href="/login"
              className="w-full text-center py-2 text-sm font-medium text-[#6B6B6A] hover:text-[#0F0F0F]"
            >
              Sign In
            </Link>
            <Link
              href="/signup"
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg py-2.5 text-sm font-medium text-white bg-[#0F0F0F]"
            >
              <span>Get Started</span>
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      )}
    </header>
  );
}
