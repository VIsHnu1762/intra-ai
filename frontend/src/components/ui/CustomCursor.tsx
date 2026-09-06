"use client";

import { useEffect, useState, useRef } from "react";

export default function CustomCursor() {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);

  const [cursorMode, setCursorMode] = useState<"default" | "cta" | "alex" | "jordan" | "demo">("default");
  const [isVisible, setIsVisible] = useState(false);
  const [isFinePointer, setIsFinePointer] = useState(() => {
    if (typeof window !== "undefined") {
      return window.matchMedia("(pointer: fine)").matches;
    }
    return false;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;

    const media = window.matchMedia("(pointer: fine)");
    const handleMediaChange = (e: MediaQueryListEvent) => {
      setIsFinePointer(e.matches);
    };
    media.addEventListener("change", handleMediaChange);

    if (!media.matches) {
      return () => media.removeEventListener("change", handleMediaChange);
    }

    let mouseX = -100;
    let mouseY = -100;
    let ringX = -100;
    let ringY = -100;
    let rafId: number;

    const onMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
      setIsVisible(true);

      if (dotRef.current) {
        dotRef.current.style.transform = `translate3d(${mouseX}px, ${mouseY}px, 0)`;
      }

      const target = e.target as HTMLElement | null;
      if (!target) return;

      const cursorTarget = target.closest("[data-cursor]") as HTMLElement | null;
      if (cursorTarget) {
        const mode = cursorTarget.getAttribute("data-cursor") as "cta" | "alex" | "jordan" | "demo";
        setCursorMode(mode || "default");
      } else {
        const isInteractive = target.closest("button, a, input, [role='button']");
        if (isInteractive) {
          setCursorMode("cta");
        } else {
          setCursorMode("default");
        }
      }
    };

    const onMouseLeave = () => {
      setIsVisible(false);
    };

    const onMouseEnter = () => {
      setIsVisible(true);
    };

    const animateRing = () => {
      const ease = 0.15;
      ringX += (mouseX - ringX) * ease;
      ringY += (mouseY - ringY) * ease;

      if (ringRef.current) {
        ringRef.current.style.transform = `translate3d(${ringX}px, ${ringY}px, 0)`;
      }
      rafId = requestAnimationFrame(animateRing);
    };

    window.addEventListener("mousemove", onMouseMove, { passive: true });
    document.addEventListener("mouseleave", onMouseLeave);
    document.addEventListener("mouseenter", onMouseEnter);
    rafId = requestAnimationFrame(animateRing);

    return () => {
      media.removeEventListener("change", handleMediaChange);
      window.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseleave", onMouseLeave);
      document.removeEventListener("mouseenter", onMouseEnter);
      cancelAnimationFrame(rafId);
    };
  }, []);

  if (!isFinePointer) return null;

  // Minimal white theme cursor styles
  let dotColor = "bg-[#0F0F0F]";
  let ringClass = "border border-[#0F0F0F]/20 bg-transparent";
  let ringSize = "w-8 h-8 -ml-4 -mt-4";
  let labelText = "";

  if (cursorMode === "cta") {
    ringClass = "border border-[#0F0F0F]/40 bg-[#0F0F0F]/10 scale-110";
    ringSize = "w-8 h-8 -ml-4 -mt-4";
  } else if (cursorMode === "alex") {
    dotColor = "bg-[#00A88A]";
    ringClass = "border-2 border-[#00A88A] bg-[#00A88A]/10";
    ringSize = "w-14 h-14 -ml-7 -mt-7";
    labelText = "Talk to Alex";
  } else if (cursorMode === "jordan") {
    dotColor = "bg-[#6D28D9]";
    ringClass = "border-2 border-[#6D28D9] bg-[#6D28D9]/10";
    ringSize = "w-14 h-14 -ml-7 -mt-7";
    labelText = "Talk to Jordan";
  } else if (cursorMode === "demo") {
    ringClass = "border border-[#0F0F0F] bg-[#0F0F0F] text-white font-medium shadow-md px-3 py-1 rounded-full";
    ringSize = "w-auto h-7 -ml-10 -mt-3.5";
    labelText = "PLAY ▶";
  }

  return (
    <div
      className={`fixed inset-0 pointer-events-none z-[9999] transition-opacity duration-200 ${
        isVisible ? "opacity-100" : "opacity-0"
      }`}
    >
      {/* Exact dot */}
      <div
        ref={dotRef}
        className={`fixed top-0 left-0 w-2 h-2 -ml-1 -mt-1 rounded-full ${dotColor} will-change-transform`}
      />

      {/* Lagging ring */}
      <div
        ref={ringRef}
        className={`fixed top-0 left-0 rounded-full flex items-center justify-center transition-[width,height,background-color,border-color,transform] duration-200 ease-out will-change-transform ${ringSize} ${ringClass}`}
      >
        {labelText && (
          <span
            ref={labelRef}
            className={`text-[10px] font-semibold whitespace-nowrap select-none ${
              cursorMode === "demo"
                ? "text-white px-2"
                : cursorMode === "jordan"
                ? "text-[#6D28D9]"
                : "text-[#00A88A]"
            }`}
          >
            {labelText}
          </span>
        )}
      </div>
    </div>
  );
}
