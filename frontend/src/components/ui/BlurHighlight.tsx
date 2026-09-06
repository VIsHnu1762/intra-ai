'use client';

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { cn } from '@/lib/utils';

interface BlurHighlightProps {
  text: string;
  highlights?: string[];
  className?: string;
  highlightClassName?: string;
  highlightBgClassName?: string;
  blurDuration?: number;
  staggerDelay?: number;
  initialDelay?: number;
}

function subscribeReducedMotion(callback: () => void) {
  const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  mediaQuery.addEventListener('change', callback);
  return () => mediaQuery.removeEventListener('change', callback);
}

function getReducedMotionSnapshot() {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function getReducedMotionServerSnapshot() {
  return false;
}

export default function BlurHighlight({
  text,
  highlights = [],
  className,
  highlightClassName,
  highlightBgClassName,
  blurDuration = 600,
  staggerDelay = 40,
  initialDelay = 0,
}: BlurHighlightProps) {
  const words = useMemo(() => text.split(' '), [text]);
  const [visible, setVisible] = useState<boolean[]>(() =>
    new Array(text.split(' ').length).fill(false)
  );
  const prefersReducedMotion = useSyncExternalStore(
    subscribeReducedMotion,
    getReducedMotionSnapshot,
    getReducedMotionServerSnapshot
  );
  const ref = useRef<HTMLParagraphElement>(null);
  const triggered = useRef(false);

  useEffect(() => {
    if (prefersReducedMotion) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !triggered.current) {
          triggered.current = true;
          words.forEach((_, i) => {
            setTimeout(() => {
              setVisible(prev => {
                const next = [...prev];
                next[i] = true;
                return next;
              });
            }, initialDelay + i * staggerDelay);
          });
        }
      },
      { threshold: 0.2 }
    );

    const currentRef = ref.current;
    if (currentRef) observer.observe(currentRef);
    return () => {
      if (currentRef) observer.unobserve(currentRef);
      observer.disconnect();
    };
  }, [words, staggerDelay, initialDelay, prefersReducedMotion]);

  const isHighlighted = (word: string) => {
    const cleanWord = word.toLowerCase().replace(/[^a-z0-9]/g, '');
    return highlights.some(h => {
      const cleanH = h.toLowerCase().replace(/[^a-z0-9]/g, '');
      return cleanWord === cleanH;
    });
  };

  return (
    <p ref={ref} className={cn('flex flex-wrap gap-x-[0.3em] gap-y-1', className)}>
      {words.map((word, i) => {
        const highlighted = isHighlighted(word);
        const isWordVisible = prefersReducedMotion || visible[i];

        return (
          <span
            key={i}
            style={{
              transition: prefersReducedMotion
                ? 'none'
                : `filter ${blurDuration}ms ease, opacity ${blurDuration}ms ease`,
              filter: isWordVisible ? 'blur(0px)' : 'blur(8px)',
              opacity: isWordVisible ? 1 : 0,
            }}
            className={cn(
              'inline-block',
              highlighted && cn('relative px-1 rounded', highlightClassName)
            )}
          >
            {highlighted && (
              <span
                className={cn('absolute inset-0 rounded', highlightBgClassName)}
                style={{
                  ...(!highlightBgClassName ? { background: 'currentColor' } : {}),
                  opacity: isWordVisible
                    ? (highlightBgClassName ? 1 : 0.12)
                    : 0,
                  transition: prefersReducedMotion
                    ? 'none'
                    : `opacity ${blurDuration * 1.5}ms ease ${initialDelay + i * staggerDelay + blurDuration}ms`,
                }}
                aria-hidden="true"
              />
            )}
            <span className="relative">{word}</span>
          </span>
        );
      })}
    </p>
  );
}
