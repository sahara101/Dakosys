"use client";

import { useEffect, useRef, useState } from "react";

interface NumberTickerProps {
  value: number;
  decimals?: number;
  duration?: number;
  className?: string;
}

export function NumberTicker({
  value,
  decimals = 0,
  duration = 1200,
  className,
}: NumberTickerProps) {
  const [display, setDisplay] = useState(0);
  const startTime = useRef<number | null>(null);
  const startValue = useRef(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    startValue.current = display;
    startTime.current = null;

    const animate = (timestamp: number) => {
      if (startTime.current === null) startTime.current = timestamp;
      const elapsed = timestamp - startTime.current;
      const progress = Math.min(elapsed / duration, 1);
      // easeOutExpo
      const ease = progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress);
      setDisplay(startValue.current + (value - startValue.current) * ease);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(animate);
      }
    };

    rafRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <span className={className}>
      {display.toLocaleString(undefined, {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
    </span>
  );
}
