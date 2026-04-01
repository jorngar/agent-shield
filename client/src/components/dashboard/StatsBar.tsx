import type { Intercept } from "@/lib/types";

interface StatsBarProps {
  intercepts: Intercept[];
  isLoading: boolean;
}

export function StatsBar({ intercepts, isLoading }: StatsBarProps) {
  const total    = intercepts.length;
  const pending  = intercepts.filter((i) => i.status === "pending").length;
  const highRisk = intercepts.filter((i) => i.riskLevel === "high").length;
  const resolved = intercepts.filter((i) => i.status !== "pending").length;

  if (isLoading) {
    return (
      <div className="flex h-8 items-center border-b border-border bg-card/40 px-5">
        <span className="animate-pulse font-mono text-[10px] text-muted-foreground/30">
          // loading…
        </span>
      </div>
    );
  }

  return (
    <div className="flex h-8 items-center gap-6 border-b border-border bg-card/40 px-5">

      <div className="flex items-center gap-4 font-mono text-[11px]">
        <span className="text-muted-foreground/70">
          total{" "}
          <span className="text-foreground font-semibold">{total}</span>
        </span>

        <span className="text-muted-foreground/35">/</span>

        <span className={pending > 0 ? "text-risk-medium" : "text-muted-foreground/70"}>
          pending{" "}
          <span className={`font-bold ${pending > 0 ? "" : "text-muted-foreground/55"}`}>
            {pending}
          </span>
        </span>

        <span className="text-muted-foreground/35">/</span>

        <span className={highRisk > 0 ? "text-risk-high" : "text-muted-foreground/70"}>
          high-risk{" "}
          <span className={`font-bold ${highRisk > 0 ? "" : "text-muted-foreground/55"}`}>
            {highRisk}
          </span>
        </span>

        <span className="text-muted-foreground/35">/</span>

        <span className="text-muted-foreground/70">
          resolved{" "}
          <span className={`font-bold ${resolved > 0 ? "text-risk-low" : "text-muted-foreground/55"}`}>
            {resolved}
          </span>
        </span>
      </div>

      {/* Right: monitoring status */}
      <div className="ml-auto flex items-center gap-2 font-mono text-[10px] text-muted-foreground/60">
        <span className="h-1.5 w-1.5 rounded-full bg-risk-low animate-pulse" />
        <span>monitoring</span>
      </div>

    </div>
  );
}
