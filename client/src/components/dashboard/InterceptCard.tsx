import type { Intercept, RiskLevel } from "@/lib/types";
import { RiskBadge } from "./RiskBadge";
import { StatusBadge } from "./StatusBadge";

const borderColor: Record<RiskLevel, string> = {
  high:   "border-l-risk-high",
  medium: "border-l-risk-medium",
  low:    "border-l-risk-low",
};

const dotColor: Record<RiskLevel, string> = {
  high:   "bg-risk-high",
  medium: "bg-risk-medium",
  low:    "bg-risk-low",
};

const dotPulse: Record<RiskLevel, string> = {
  high:   "animate-ping",
  medium: "animate-ping",
  low:    "",
};

export function formatLogTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  });
}

interface InterceptCardProps {
  intercept: Intercept;
  isSelected: boolean;
  onClick: () => void;
}

export function InterceptCard({ intercept, isSelected, onClick }: InterceptCardProps) {
  const { toolName, status, riskLevel, category, timestamp } = intercept;

  return (
    <button
      onClick={onClick}
      className={`
        group w-full border-l-2 text-left
        animate-slide-up-fade
        transition-colors duration-150
        ${borderColor[riskLevel]}
        ${isSelected
          ? "bg-primary/8 ring-1 ring-inset ring-primary/20"
          : "hover:bg-muted/40"
        }
      `}
    >
      <div className="px-3 py-2.5">
        {/* Line 1: dot + tool name + time */}
        <div className="flex items-center gap-2">
          {/* Risk dot with optional ping for high/medium pending */}
          <span className="relative flex h-1.5 w-1.5 shrink-0">
            {status === "pending" && riskLevel !== "low" && (
              <span className={`absolute inline-flex h-full w-full rounded-full ${dotColor[riskLevel]} opacity-60 ${dotPulse[riskLevel]}`} />
            )}
            <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${dotColor[riskLevel]}`} />
          </span>
          <span className="flex-1 truncate font-mono text-xs font-semibold text-foreground">
            {toolName}
          </span>
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-muted-foreground/40">
            {formatLogTime(timestamp)}
          </span>
        </div>

        {/* Line 2: category + risk + status */}
        <div className="mt-1 flex items-center gap-2 pl-3.5">
          <span className="flex-1 truncate font-mono text-[10px] text-muted-foreground/50">
            {category}
          </span>
          <RiskBadge level={riskLevel} compact />
          <StatusBadge status={status} />
        </div>
      </div>
    </button>
  );
}
