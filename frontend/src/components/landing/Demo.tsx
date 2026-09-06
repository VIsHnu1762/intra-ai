"use client";

import { useState, useEffect } from "react";
import { Play, Pause, Volume2, Maximize2 } from "lucide-react";
import Waveform from "@/components/ui/Waveform";

export default function Demo() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeChapter, setActiveChapter] = useState(1);
  const [progress, setProgress] = useState(22);

  const chapters = [
    { time: "0:00", label: "Candidate preparation", targetProgress: 5 },
    { time: "2:30", label: "Alex begins — Technical round", targetProgress: 25 },
    { time: "9:00", label: "Jordan joins — Product round", targetProgress: 65 },
    { time: "14:00", label: "Evidence aggregated", targetProgress: 95 },
  ];

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (isPlaying) {
      interval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 100) return 0;
          return prev + 0.5;
        });
      }, 200);
    }
    return () => clearInterval(interval);
  }, [isPlaying]);

  return (
    <section id="demo" className="relative py-12 md:py-14 bg-[#F9F9F8] border-t border-[#EBEBEA] overflow-hidden">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        {/* Section Headline */}
        <div className="text-center max-w-2xl mx-auto mb-7">
          <span className="text-[11px] font-mono font-semibold uppercase tracking-widest text-[#00A88A] block mb-1.5">
            Real Session Walkthrough
          </span>
          <h2 className="text-2xl sm:text-3xl font-bold tracking-tight text-[#0F0F0F] mb-2">
            How does an adaptive interview sound?
          </h2>
          <p className="text-sm text-[#6B6B6A]">
            Listen to a live fifteen-minute voice session with Alex and Jordan.
          </p>
        </div>

        {/* Custom Video Player Container */}
        <div className="max-w-3xl mx-auto">
          <div
            data-cursor="demo"
            className="relative rounded-xl border border-[#EBEBEA] bg-white overflow-hidden shadow-[0_4px_24px_rgba(0,0,0,0.06)] aspect-[16/9] flex flex-col justify-between group"
          >
            {/* Screen Mock Video Content */}
            <div className="absolute inset-0 flex flex-col items-center justify-center p-5 sm:p-6 bg-[#FAFAF9]">
              {/* Subtle background grid */}
              <div
                className="absolute inset-0 opacity-40"
                style={{
                  backgroundImage: "radial-gradient(#D4D4D2 1px, transparent 1px)",
                  backgroundSize: "20px 20px",
                }}
              />

              {/* Speaker Indicator & Waveform in Center */}
              <div className="relative z-10 text-center space-y-2.5 max-w-md">
                <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-white border border-[#EBEBEA] text-[11px] font-mono text-[#6B6B6A] shadow-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#00A88A] animate-ping" />
                  <span>CHAPTER {activeChapter + 1} OF 4</span>
                  <span className="text-[#A0A09E]">·</span>
                  <span className="text-[#00A88A] font-semibold">{chapters[activeChapter].label}</span>
                </div>

                <div className="h-10 sm:h-12 flex items-center justify-center">
                  <Waveform
                    color={activeChapter === 2 ? "violet" : "teal"}
                    barCount={24}
                    height={36}
                    variant="staccato"
                    active={isPlaying}
                  />
                </div>

                <div className="rounded-lg bg-white border border-[#EBEBEA] p-2.5 sm:p-3 shadow-xs">
                  <p className="text-[10px] text-[#A0A09E] mb-0.5 font-mono uppercase font-semibold">
                    {activeChapter === 2 ? "Jordan (Product AI)" : "Alex (Technical AI)"} Speaking:
                  </p>
                  <p className="text-xs font-mono text-[#0F0F0F] leading-snug">
                    {activeChapter === 0 && "Checking audio latency and microphone gain with candidate..."}
                    {activeChapter === 1 && "“You mentioned horizontal scaling earlier. Walk me through database partitioning at 10M users.”"}
                    {activeChapter === 2 && "“How would you prioritize backlog items when engineering bandwidth drops unexpectedly?”"}
                    {activeChapter === 3 && "“Synthesizing competency signals across technical architecture and communication depth.”"}
                  </p>
                </div>
              </div>

              {/* Central Play/Pause button trigger */}
              {!isPlaying && (
                <button
                  onClick={() => setIsPlaying(true)}
                  className="absolute z-20 w-12 h-12 rounded-full bg-[#0F0F0F] hover:bg-[#00A88A] text-white flex items-center justify-center shadow-lg shadow-black/10 hover:scale-105 transition-all duration-200 cursor-pointer"
                  aria-label="Play demo video"
                >
                  <Play className="w-5 h-5 fill-white ml-0.5" />
                </button>
              )}
            </div>

            {/* Top Bar Chrome */}
            <div className="relative z-20 px-3.5 py-2 flex items-center justify-between bg-white/95 backdrop-blur-xs border-b border-[#EBEBEA]">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-[#0F0F0F] tracking-tight">
                  Session #8412
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#F0F0F0] text-[#6B6B6A] border border-[#EBEBEA]">
                  Rahul Sharma
                </span>
              </div>
              <div className="flex items-center gap-2.5 text-xs text-[#6B6B6A]">
                <Volume2 className="w-3.5 h-3.5 cursor-pointer hover:text-[#0F0F0F] transition-colors" />
                <Maximize2 className="w-3.5 h-3.5 cursor-pointer hover:text-[#0F0F0F] transition-colors" />
              </div>
            </div>

            {/* Bottom Controls Chrome */}
            <div className="relative z-20 p-2.5 sm:p-3 bg-white/95 backdrop-blur-xs border-t border-[#EBEBEA] space-y-2">
              {/* Timeline with Chapters */}
              <div className="relative w-full">
                {/* Progress bar container */}
                <div
                  onClick={(e) => {
                    const rect = e.currentTarget.getBoundingClientRect();
                    const clickX = e.clientX - rect.left;
                    const percent = Math.min(100, Math.max(0, (clickX / rect.width) * 100));
                    setProgress(percent);
                  }}
                  className="h-1 w-full bg-[#EBEBEA] hover:h-1.5 rounded-full cursor-pointer relative transition-all"
                >
                  <div
                    className="h-full bg-[#00A88A] rounded-full relative"
                    style={{ width: `${progress}%` }}
                  >
                    <span className="absolute right-0 top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-[#0F0F0F] shadow-xs" />
                  </div>
                </div>

                {/* Chapter Marker Buttons */}
                <div className="flex justify-between mt-1.5 text-[9px] sm:text-[10px] font-mono text-[#6B6B6A]">
                  {chapters.map((ch, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setActiveChapter(idx);
                        setProgress(ch.targetProgress);
                      }}
                      className={`hover:text-[#00A88A] transition-colors cursor-pointer ${
                        activeChapter === idx ? "text-[#00A88A] font-medium" : ""
                      }`}
                    >
                      {ch.time} · {ch.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Play / Pause Toggle Bar */}
              <div className="flex items-center justify-between text-[11px] text-[#6B6B6A]">
                <button
                  onClick={() => setIsPlaying(!isPlaying)}
                  className="flex items-center gap-1.5 text-[#0F0F0F] font-semibold hover:text-[#00A88A] transition-colors cursor-pointer"
                >
                  {isPlaying ? (
                    <>
                      <Pause className="w-3.5 h-3.5 fill-current" />
                      <span>Pause Session</span>
                    </>
                  ) : (
                    <>
                      <Play className="w-3.5 h-3.5 fill-current" />
                      <span>Play Session (15:00)</span>
                    </>
                  )}
                </button>
                <span className="font-mono text-[10px] text-[#A0A09E]">HD 1080p · Opus Voice Audio</span>
              </div>
            </div>
          </div>

          {/* 3 Callout Badges Below Video */}
          <div className="mt-4 grid grid-cols-3 gap-2 text-center">
            <div className="py-2 px-2.5 rounded-lg border border-[#EBEBEA] bg-white shadow-xs">
              <span className="text-[11px] font-medium text-[#6B6B6A]">
                Real Voice Interaction
              </span>
            </div>

            <div className="py-2 px-2.5 rounded-lg border border-[#EBEBEA] bg-white shadow-xs">
              <span className="text-[11px] font-medium text-[#6B6B6A]">
                Live Adaptive Reasoning
              </span>
            </div>

            <div className="py-2 px-2.5 rounded-lg border border-[#EBEBEA] bg-white shadow-xs">
              <span className="text-[11px] font-medium text-[#6B6B6A]">
                Evidence-Grounded Output
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
