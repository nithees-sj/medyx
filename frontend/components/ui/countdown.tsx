"use client";

import { useEffect, useState } from "react";

/** mm:ss until `until`; calls onExpire once when it reaches zero. */
export function Countdown({ until, onExpire }: { until: string; onExpire?: () => void }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Date.parse(until) - now);
  useEffect(() => {
    if (left === 0) onExpire?.();
  }, [left, onExpire]);
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  return (
    <span className="font-mono tabular-nums">
      {m}:{s.toString().padStart(2, "0")}
    </span>
  );
}
