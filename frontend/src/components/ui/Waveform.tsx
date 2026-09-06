"use client";

import React from "react";

interface WaveformProps {
  color?: "teal" | "violet" | "green" | "custom";
  customColor?: string;
  barCount?: number;
  height?: number;
  variant?: "staccato" | "flowing" | "ambient";
  className?: string;
  active?: boolean;
}

export default function Waveform({
  color = "teal",
  customColor,
  barCount = 18,
  height = 24,
  variant = "staccato",
  className = "",
  active = true,
}: WaveformProps) {
  const getBarColor = () => {
    if (customColor) return customColor;
    switch (color) {
      case "teal":
        return "#00A88A";
      case "violet":
        return "#6D28D9";
      case "green":
        return "#059669";
      default:
        return "#00A88A";
    }
  };

  const barColor = getBarColor();

  return (
    <div
      className={`inline-flex items-center gap-[3px] select-none ${className}`}
      style={{ height: `${height}px` }}
      aria-hidden="true"
    >
      {Array.from({ length: barCount }).map((_, i) => {
        // Vary animation durations and min/max heights
        const duration =
          variant === "staccato"
            ? 0.5 + ((i * 7) % 5) * 0.15
            : 1.0 + ((i * 3) % 4) * 0.25;

        const delay = (i * 0.08) % 0.8;
        const initialHeight = Math.max(
          20,
          Math.sin((i / (barCount - 1)) * Math.PI) * 90
        );

        return (
          <span
            key={i}
            className="w-[2.5px] rounded-full transition-all"
            style={{
              backgroundColor: barColor,
              height: active ? `${initialHeight}%` : "15%",
              opacity: 0.65 + ((i % 3) * 0.15),
              animation: active
                ? `intraWaveBar ${duration}s ease-in-out infinite alternate ${delay}s`
                : "none",
            }}
          />
        );
      })}
    </div>
  );
}
