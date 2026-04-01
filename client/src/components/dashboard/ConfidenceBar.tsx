import { useEffect, useState } from "react";
import type { RiskLevel } from "@/lib/types";

const barColor: Record<RiskLevel, string> = {
  low:    "bg-risk-low",
  medium: "bg-risk-medium",
  high:   "bg-risk-high",
};

interface ConfidenceBarProps {
  value: number; // 0–1
  riskLevel: RiskLevel;
}

export function ConfidenceBar({ value, riskLevel }: ConfidenceBarProps) {
  const percent = Math.round(value * 100);
  const [displayed, setDisplayed] = useState(0);
  const [count, setCount]         = useState(0);

  // Animate fill + counter on mount or value change
  useEffect(() => {
    setDisplayed(0);
    setCount(0);
    const start = performance.now();
    const duration = 900;

    const raf = (now: number) => {
      const progress = Math.min((now - start) / duration, 1);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      setDisplayed(eased * percent);
      setCount(Math.round(eased * percent));
      if (progress < 1) requestAnimationFrame(raf);
    };

    const id = requestAnimationFrame(raf);
    return () => cancelAnimationFrame(id);
  }, [percent]);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="font-mono text-muted-foreground">confidence</span>
        <span className="font-mono font-bold tabular-nums text-foreground">
          {count}<span className="text-muted-foreground/50">%</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-border">
        <div
          className={`h-full rounded-full ${barColor[riskLevel]}`}
          style={{ width: `${displayed}%`, transition: "none" }}
        />
      </div>
    </div>
  );
}
