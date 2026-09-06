"use client";

import { useEffect, useState } from "react";

interface TypewriterTextProps {
  texts: string[];
  typingSpeed?: number;
  deleteSpeed?: number;
  pauseDuration?: number;
  className?: string;
  cursorColor?: string;
}

export default function TypewriterText({
  texts,
  typingSpeed = 30,
  deleteSpeed = 15,
  pauseDuration = 3500,
  className = "",
  cursorColor = "#00C9A7",
}: TypewriterTextProps) {
  const [currentTextIndex, setCurrentTextIndex] = useState(0);
  const [displayedText, setDisplayedText] = useState(() => {
    if (typeof window !== "undefined") {
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced && texts && texts.length > 0) {
        return texts[0];
      }
    }
    return "";
  });
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    if (!texts || texts.length === 0) return;

    if (typeof window !== "undefined") {
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) return;
    }

    const currentFullText = texts[currentTextIndex];
    let timeout: NodeJS.Timeout;

    if (!isDeleting && displayedText === currentFullText) {
      // Pause at end of sentence
      timeout = setTimeout(() => {
        setIsDeleting(true);
      }, pauseDuration);
    } else if (isDeleting && displayedText === "") {
      // Finished deleting, brief 500ms pause then move to next sentence
      timeout = setTimeout(() => {
        setIsDeleting(false);
        setCurrentTextIndex((prev) => (prev + 1) % texts.length);
      }, 500);
    } else if (isDeleting) {
      // Deleting character
      timeout = setTimeout(() => {
        setDisplayedText((prev) => prev.slice(0, -1));
      }, deleteSpeed);
    } else {
      // Typing character
      timeout = setTimeout(() => {
        setDisplayedText((prev) => currentFullText.slice(0, prev.length + 1));
      }, typingSpeed);
    }

    return () => clearTimeout(timeout);
  }, [displayedText, isDeleting, currentTextIndex, texts, typingSpeed, deleteSpeed, pauseDuration]);

  return (
    <span className={`inline-block font-mono ${className}`}>
      <span>{displayedText}</span>
      <span
        className="inline-block w-[2px] h-[1em] ml-1 align-middle animate-pulse"
        style={{ backgroundColor: cursorColor }}
        aria-hidden="true"
      />
    </span>
  );
}
