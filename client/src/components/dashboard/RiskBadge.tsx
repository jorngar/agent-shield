import type { RiskLevel } from "@/lib/types";

const config: Record<RiskLevel, { label: string; compactLabel: string; className: string }> = {
  low: {
    label:        "Low Risk",
    compactLabel: "Low",
    className:    "bg-risk-low text-risk-low-foreground",
  },
  medium: {
    label:        "Medium Risk",
    compactLabel: "Med",
    className:    "bg-risk-medium text-risk-medium-foreground",
  },
  high: {
    label:        "High Risk",
    compactLabel: "High",
    className:    "bg-risk-high text-risk-high-foreground",
  },
};

interface RiskBadgeProps {
  level: RiskLevel;
  compact?: boolean;
  className?: string;
}

export function RiskBadge({ level, compact = false, className = "" }: RiskBadgeProps) {
  const { label, compactLabel, className: colorClass } = config[level];
  return (
    <span
      className={`
        inline-flex items-center rounded-full px-2 py-0.5 font-semibold uppercase tracking-wide
        ${compact ? "text-[10px]" : "text-xs px-2.5"}
        ${colorClass} ${className}
      `}
    >
      {compact ? compactLabel : label}
    </span>
  );
}
